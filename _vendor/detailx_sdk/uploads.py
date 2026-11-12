import base64
import hashlib
import math
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from .client import segment
from .errors import DetailXError, OperationStopped
from .media import create_thumbnail, inspect_video, validate_public_url

TERMINAL = {"failed", "rejected", "cancelled", "expired"}


def md5(data: bytes) -> str:
    return base64.b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode("ascii")


def validate_media(path: Path, policy: dict, metadata: dict, max_duration: float | None):
    size = path.stat().st_size
    if not policy["min_bytes"] <= size <= policy["effective_max_bytes"]:
        raise DetailXError("Video size is outside current upload policy", code="invalid_media")
    if len(path.name) > min(policy["max_filename_length"], 255):
        raise DetailXError("Video filename is too long", code="invalid_media")
    requirements = policy["video"]
    aliases = {"h265": "hevc", "avc": "h264", "avc1": "h264", "hev1": "hevc", "hvc1": "hevc"}
    codecs = {aliases.get(c.lower(), c.lower()) for c in requirements["codecs"]}
    containers = {c.lower().lstrip(".") for c in requirements["containers"]}
    if metadata["codec"] not in codecs:
        raise DetailXError("Video codec is outside current upload policy", code="invalid_media")
    if not (set(metadata["containers"]) & containers or path.suffix.lower().lstrip(".") in containers):
        raise DetailXError("Video container is outside current upload policy", code="invalid_media")
    if max(metadata["width"], metadata["height"]) > requirements["max_edge"] or metadata["width"] * metadata["height"] > requirements["max_pixels"] or metadata["video_streams"] > requirements["max_streams"]:
        raise DetailXError("Video dimensions or stream count exceed upload policy", code="invalid_media")
    limits = [x for x in (requirements.get("max_duration_seconds"), max_duration) if x is not None]
    if limits and metadata["duration"] > min(limits):
        raise DetailXError("Video duration exceeds the configured limit", code="invalid_media")


def upload_video(client, path: Path, *, request_id: str, on_progress=None, stop=None, max_duration=None):
    if not path.is_file():
        raise DetailXError("Video file does not exist", code="invalid_media")
    policy = client.upload_policy()
    # Reject oversized files before hashing or decoding them.
    if not policy["min_bytes"] <= path.stat().st_size <= policy["effective_max_bytes"]:
        raise DetailXError("Video size is outside current upload policy", code="invalid_media")
    metadata = inspect_video(path)
    validate_media(path, policy, metadata, max_duration)
    initial_stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            if stop and stop.is_set():
                raise OperationStopped()
            digest.update(block)
    fingerprint = digest.hexdigest()
    body = {"filename": path.name, "size_bytes": initial_stat.st_size, "fingerprint": fingerprint,
            **{k: metadata[k] for k in ("duration", "width", "height")}}
    saved = client.store.put_once(client.scope, "upload", request_id, {"body": body})
    client.store.require_same(saved["body"], body)
    resumed = bool(saved.get("session_id"))
    prefix = "/upload-sessions"
    if resumed:
        session = client.request("GET", prefix + "/" + segment(saved["session_id"]))
    else:
        key = "dx-up-" + hashlib.sha256((client.scope + request_id).encode()).hexdigest()[:48]
        session = client.request("POST", prefix, body=body, idempotency_key=key)
        if not session.get("id"):
            raise DetailXError("Upload response has no session ID", code="invalid_response")
        client.store.update(client.scope, "upload", request_id, {**saved, "session_id": session["id"]})
    prefix += "/" + segment(session["id"])
    try:
        expires = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        deadline = time.monotonic() + max(0, (expires - datetime.now(timezone.utc)).total_seconds())
    except (KeyError, ValueError):
        raise DetailXError("Upload response has no valid expiry", code="invalid_response")
    poll = max(1, policy.get("poll_interval_seconds", 3))

    def check():
        if stop and stop.is_set():
            raise OperationStopped()
        if time.monotonic() >= deadline:
            raise DetailXError("Upload session deadline reached; recover with the same request ID", code="upload_timeout")

    def wait_for(predicate):
        nonlocal session
        while True:
            if on_progress:
                on_progress({"phase": "upload", **session})
            if session.get("status") in TERMINAL:
                raise DetailXError("Upload session is " + session["status"], code="upload_failed")
            if predicate(session) or session.get("status") == "ready":
                return
            check()
            client.sleep(min(poll, max(0, deadline - time.monotonic())))
            session = client.request("GET", prefix)

    wait_for(lambda s: s.get("status") == "uploading")
    if session.get("status") == "ready":
        return session
    confirmed: set[int] = set()
    if resumed:
        session = client.request("POST", prefix + "/resume", body={"fingerprint": fingerprint})
        revision = session.get("resume_revision")
        if revision is None:
            raise DetailXError("Resume response missing revision; refusing unconfirmed part state", code="invalid_response")
        wait_for(lambda s: s.get("parts_revision", -1) >= revision)
        if session.get("status") == "ready":
            return session
        # The API's generic session schema may evolve: unknown formats safely re-PUT all parts.
        for part in session.get("parts", []):
            if isinstance(part, dict) and part.get("status") in ("uploaded", "completed", "confirmed"):
                confirmed.add(int(part["number"]))
        for number in session.get("uploaded_parts", []):
            if isinstance(number, int):
                confirmed.add(number)
    part_bytes = int(session["part_bytes"])
    part_count = int(session["part_count"])
    if part_bytes <= 0 or part_count != math.ceil(initial_stat.st_size / part_bytes) or part_count > policy["max_parts"]:
        raise DetailXError("Invalid upload part layout", code="invalid_response")

    def put(signed, data):
        check()
        validate_public_url(signed["url"], allow_private=client.allow_private_media)
        headers = dict(signed.get("headers", {}))
        if any(k.lower() in ("authorization", "proxy-authorization", "cookie") for k in headers):
            raise DetailXError("Unexpected credential header in upload signature", code="unsafe_signature")
        headers["Content-Length"] = str(len(data))
        # Separate unauthenticated transport, no redirects. A failed PUT is retried via resume.
        with httpx.Client(timeout=min(300, max(1, deadline - time.monotonic())), trust_env=False, follow_redirects=False) as media:
            response = media.put(signed["url"], content=data, headers=headers)
            if not response.is_success:
                raise DetailXError("Signed upload failed; retry with the same upload request ID", code="upload_put_failed")

    with tempfile.TemporaryDirectory(prefix="detailx-cover-") as temporary:
        cover = create_thumbnail(path, Path(temporary) / "cover.jpg", policy["thumbnail"]).read_bytes()
        signed = client.request("POST", prefix + "/thumbnail", body={"size_bytes": len(cover), "md5": md5(cover)})
        put(signed, cover)
    missing = [number for number in range(1, part_count + 1) if number not in confirmed]
    batch_size = max(1, min(16, int(policy["sign_batch_size"])))
    with path.open("rb") as source:
        for start in range(0, len(missing), batch_size):
            batch = missing[start:start + batch_size]
            checksums = []
            for number in batch:
                check()
                source.seek((number - 1) * part_bytes)
                checksums.append({"number": number, "md5": md5(source.read(part_bytes))})
            signed = client.request("POST", prefix + "/parts", body={"parts": checksums})
            signatures = {p["number"]: p for p in signed["parts"]}
            for number in batch:
                current_stat = path.stat()
                if current_stat.st_size != initial_stat.st_size or current_stat.st_mtime_ns != initial_stat.st_mtime_ns:
                    raise DetailXError("Source file changed during upload", code="file_changed")
                source.seek((number - 1) * part_bytes)
                data = source.read(part_bytes)
                put(signatures[number], data)
                if on_progress:
                    on_progress({"phase": "uploading_parts", "part": number, "part_count": part_count, "id": session["id"]})
    session = client.request("POST", prefix + "/complete")
    wait_for(lambda s: s.get("status") == "ready")
    return session
