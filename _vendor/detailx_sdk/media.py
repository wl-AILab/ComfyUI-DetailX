import ipaddress
import math
import os
import socket
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from .errors import DetailXError


def validate_public_url(url: str, *, allow_private: bool = False):
    parsed = urlsplit(url)
    if parsed.scheme != "https" and not (allow_private and parsed.scheme == "http"):
        raise DetailXError("Media URLs must use HTTPS", code="unsafe_url")
    if not parsed.hostname or parsed.username or parsed.password:
        raise DetailXError("Invalid media URL", code="unsafe_url")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise DetailXError("Media hostname could not be resolved", code="invalid_media") from exc
    if not allow_private and any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise DetailXError("Private or reserved media addresses are not allowed", code="unsafe_url")
    if not addresses:
        raise DetailXError("Media hostname has no addresses", code="unsafe_url")
    return sorted({item[4][0] for item in addresses}, key=lambda ip: (":" in ip, ip))


def download_url(url: str, target: str | Path, *, max_bytes: int, allow_private: bool = False, timeout: float = 120, client: httpx.Client | None = None) -> Path:
    """No API Authorization. Pin validated DNS results while preserving HTTPS SNI and Host."""
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    transport = client or httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False)
    owns = client is None
    temporary = None
    try:
        for _ in range(6):
            addresses = validate_public_url(url, allow_private=allow_private)
            original = httpx.URL(url)
            pinned = original.copy_with(host=addresses[0])
            headers = {"Accept-Encoding": "identity", "Host": original.netloc.decode("ascii")}
            with transport.stream("GET", pinned, headers=headers, extensions={"sni_hostname": original.host}, follow_redirects=False) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    if not response.headers.get("location"):
                        raise DetailXError("Media redirect has no location", code="download_failed")
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                length = response.headers.get("content-length")
                if length and int(length) > max_bytes:
                    raise DetailXError("Media exceeds download size limit", code="media_too_large")
                handle, temporary = tempfile.mkstemp(prefix=".detailx-", dir=target.parent)
                count = 0
                with os.fdopen(handle, "wb") as output:
                    for block in response.iter_bytes(1024 * 1024):
                        count += len(block)
                        if count > max_bytes:
                            raise DetailXError("Media exceeds download size limit", code="media_too_large")
                        output.write(block)
                if count == 0:
                    raise DetailXError("Media download is empty", code="download_failed")
                os.replace(temporary, target)
                temporary = None
                return target
        raise DetailXError("Too many media redirects", code="download_failed")
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
        if owns:
            transport.close()


def inspect_video(path: str | Path) -> dict:
    try:
        import av
    except ImportError as exc:
        raise DetailXError("Install detailx-sdk[media] for local video processing", code="missing_media_dependency") from exc
    try:
        with av.open(str(path)) as container:
            stream = next((s for s in container.streams.video if not (s.disposition & av.stream.Disposition.attached_pic)), None)
            if stream is None:
                raise DetailXError("No video stream found", code="invalid_media")
            duration = float(stream.duration * stream.time_base) if stream.duration is not None else float(container.duration or 0) / av.time_base
            if not math.isfinite(duration) or duration <= 0:
                raise DetailXError("Video must have a positive finite duration", code="invalid_media")
            return {"width": stream.width, "height": stream.height, "duration": duration, "fps": float(stream.average_rate or 0), "codec": stream.codec_context.name, "containers": container.format.name.split(","), "video_streams": len(container.streams.video)}
    except DetailXError:
        raise
    except Exception as exc:
        raise DetailXError("Video could not be decoded", code="invalid_media") from exc


def create_thumbnail(path: str | Path, target: str | Path, requirements: dict) -> Path:
    import av
    with av.open(str(path)) as container:
        stream = next(s for s in container.streams.video if not (s.disposition & av.stream.Disposition.attached_pic))
        image = next(container.decode(stream)).to_image().convert("RGB")
    edge = int(requirements["max_edge"])
    image.thumbnail((edge, edge))
    for quality in (85, 65, 45, 25, 10):
        image.save(target, format="JPEG", quality=quality)
        if Path(target).stat().st_size <= int(requirements["max_bytes"]):
            return Path(target)
    raise DetailXError("Thumbnail cannot satisfy server size policy", code="thumbnail_too_large")
