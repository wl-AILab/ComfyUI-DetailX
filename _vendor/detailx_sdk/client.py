import hashlib
import json
import math
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit

import httpx

from .errors import BudgetExceeded, DetailXError, OperationStopped
from .models import GenerationOptions, PreparedGeneration, source_params
from .store import RequestStore

DEFAULT_BASE = "https://www.detail-x.ai/api/v1"


def segment(value: str) -> str:
    if not value:
        raise ValueError("ID cannot be empty")
    return quote(str(value), safe="")


class DetailXClient:
    def __init__(self, api_key: str | None = None, *, base_url: str | None = None, state_dir: str | Path | None = None, store: RequestStore | None = None, transport: httpx.BaseTransport | None = None, retries: int = 3, timeout: float = 30, allow_private_media: bool = False, sleep: Callable[[float], None] = time.sleep):
        self.api_key = api_key or os.environ.get("DETAILX_API_KEY", "")
        self.base_url = (base_url or os.environ.get("DETAILX_BASE", DEFAULT_BASE)).rstrip("/")
        parsed = urlsplit(self.base_url)
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or (parsed.scheme != "https" and not (allow_private_media and parsed.scheme == "http")):
            raise ValueError("API base must use HTTPS (HTTP is allowed only for explicit local testing)")
        if not self.api_key or not self.api_key.startswith("dxk_") or self.api_key == "dxk_REPLACE_ME":
            raise DetailXError("A valid DetailX API key is required", code="missing_api_key")
        self.scope = hashlib.sha256((self.base_url + "\0" + self.api_key).encode()).hexdigest()
        self.state_dir = Path(state_dir or os.environ.get("DETAILX_STATE_DIR", ".detailx-state"))
        self.store = store or RequestStore(self.state_dir / "requests.sqlite3")
        self.retries = retries
        self.sleep = sleep
        self.allow_private_media = allow_private_media
        self.http = httpx.Client(timeout=timeout, transport=transport, follow_redirects=False, trust_env=False)
        self._lock = threading.Lock()
        self._last_request = 0.0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.http.close()

    def request(self, method: str, path: str, *, body: dict | None = None, idempotency_key: str | None = None) -> dict:
        if not path.startswith("/") or "://" in path or path.startswith("//"):
            raise ValueError("Use an API-relative path")
        headers = {"Authorization": "Bearer " + self.api_key, "Accept": "application/json", "User-Agent": "detailx-python/0.1.0"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        retryable = method == "GET" or bool(idempotency_key) or path in ("/generation-estimates", "/generation-batch-estimates")
        for attempt in range(self.retries + 1):
            # Leave room below the server's 120/minute per-key quota.
            with self._lock:
                delay = 0.65 - (time.monotonic() - self._last_request)
                if delay > 0:
                    self.sleep(delay)
                self._last_request = time.monotonic()
            try:
                response = self.http.request(method, self.base_url + path, headers=headers, json=body)
            except httpx.TransportError as exc:
                if retryable and attempt < self.retries:
                    self.sleep(min(2 ** attempt, 10))
                    continue
                raise DetailXError("API transport failed; reuse the saved request ID to recover", code="transport_error") from exc
            if response.status_code in (429, 502, 503, 504) and retryable and attempt < self.retries:
                try:
                    delay = min(float(response.headers.get("Retry-After", 2 ** attempt)), 120)
                except ValueError:
                    delay = 2 ** attempt
                self.sleep(max(delay, 0))
                continue
            try:
                data = response.json()
            except ValueError:
                data = {}
            if not response.is_success:
                detail = data.get("detail", {}) if isinstance(data, dict) else {}
                code = detail.get("code", f"http_{response.status_code}") if isinstance(detail, dict) else f"http_{response.status_code}"
                # Do not include raw server errors, which may contain signed URLs or credentials.
                raise DetailXError(f"DetailX returned {response.status_code} ({code})", code=code, status=response.status_code)
            if not isinstance(data, dict):
                raise DetailXError("Unexpected API response", code="invalid_response")
            return data
        raise AssertionError("Unreachable")

    def account(self):
        return self.request("GET", "/auth/me")

    def capabilities(self):
        return self.request("GET", "/generation-capabilities")

    def capacity(self):
        return self.request("GET", "/generation-capacity")

    def upload_policy(self):
        return self.request("GET", "/upload-policy")

    def get_generation(self, generation_id: str):
        return self.request("GET", "/generations/" + segment(generation_id))

    def list_uploads(self, *, offset: int = 0, limit: int = 100):
        return self.request("GET", f"/uploads?offset={offset}&limit={limit}")

    def list_generations(self, *, offset: int = 0, limit: int = 100):
        return self.request("GET", f"/generations?offset={offset}&limit={limit}")

    def transactions(self, *, offset: int = 0, limit: int = 100):
        return self.request("GET", f"/billing/transactions?offset={offset}&limit={limit}")

    def estimate(self, options: GenerationOptions = GenerationOptions(), *, upload_id: str | None = None, source_result_id: str | None = None):
        return self.request("POST", "/generation-estimates", body=source_params(options, upload_id, source_result_id))

    def prepare_generation(self, options: GenerationOptions = GenerationOptions(), *, upload_id: str | None = None, source_result_id: str | None = None, request_id: str | None = None, max_precharge_credits: int) -> PreparedGeneration:
        if type(max_precharge_credits) is not int or max_precharge_credits < 0:
            raise ValueError("max_precharge_credits must be a nonnegative integer")
        request_id = request_id or str(uuid.uuid4())
        params = source_params(options, upload_id, source_result_id)
        existing = self.store.get(self.scope, "generation", request_id)
        if existing is None:
            quote_data = self.request("POST", "/generation-estimates", body=params)
            credits = quote_data.get("credits")
            revision = quote_data.get("pricing_revision_id")
            if type(credits) is not int or credits < 0 or type(revision) is not int or revision < 1:
                raise DetailXError("Invalid quote response", code="invalid_response")
            if credits > max_precharge_credits:
                raise BudgetExceeded(credits, max_precharge_credits)
            prepared = PreparedGeneration(request_id, self.scope, "dx-gen-" + hashlib.sha256((self.scope + request_id).encode()).hexdigest()[:48], {**params, "expected_credits": credits, "pricing_revision_id": revision}, quote_data)
            existing = self.store.put_once(self.scope, "generation", request_id, {"params": params, "prepared": prepared.to_dict()})
        self.store.require_same(existing["params"], params)
        prepared = PreparedGeneration.from_dict(existing["prepared"])
        if prepared.credits > max_precharge_credits:
            raise BudgetExceeded(prepared.credits, max_precharge_credits)
        return prepared

    def submit(self, prepared: PreparedGeneration):
        if prepared.scope != self.scope:
            raise DetailXError("Prepared request belongs to another credential", code="credential_mismatch")
        stored = self.store.get(self.scope, "generation", prepared.request_id)
        if not stored:
            raise DetailXError("Prepared request is absent from this durable store", code="missing_prepared_request")
        self.store.require_same(stored["prepared"], prepared.to_dict())
        if stored.get("generation_id"):
            return self.get_generation(stored["generation_id"])
        job = self.request("POST", "/generations", body=prepared.body, idempotency_key=prepared.idempotency_key)
        if not job.get("id"):
            raise DetailXError("Accepted response is missing generation ID", code="invalid_response")
        self.store.update(self.scope, "generation", prepared.request_id, {**stored, "generation_id": job["id"]})
        return job

    def wait(self, generation_id: str, *, timeout: float = 1800, poll_interval: float = 10, stop: threading.Event | None = None, on_progress: Callable[[dict], None] | None = None):
        if not math.isfinite(timeout) or timeout <= 0 or not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError("Wait timeout and poll interval must be positive finite numbers")
        deadline = time.monotonic() + timeout
        while True:
            if stop and stop.is_set():
                raise OperationStopped()
            job = self.get_generation(generation_id)
            if on_progress:
                on_progress(job)
            if job.get("status") == "completed":
                return job
            if job.get("status") == "failed":
                raise DetailXError(f"Generation failed; refund state: {job.get('refund_status', 'unknown')}", code="generation_failed")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DetailXError(f"Local wait timed out. Recover generation {generation_id}; server billing is unchanged.", code="wait_timeout")
            delay = min(max(poll_interval, 1), remaining)
            if stop:
                if stop.wait(delay):
                    raise OperationStopped()
            else:
                self.sleep(delay)

    def upload_video(self, path: str | Path, *, request_id: str | None = None, on_progress: Callable[[dict], None] | None = None, stop: threading.Event | None = None, max_duration: float | None = None):
        from .uploads import upload_video
        return upload_video(self, Path(path), request_id=request_id or str(uuid.uuid4()), on_progress=on_progress, stop=stop, max_duration=max_duration)

    def cancel_upload(self, session_id: str):
        return self.request("POST", f"/upload-sessions/{segment(session_id)}/cancel", body={"reason": "user"})

    def download_result(self, generation_id: str, output: str | Path, *, index: int = 0, max_bytes: int = 8 * 1024 ** 3):
        from .media import download_url
        if type(index) is not int or index < 0:
            raise ValueError("Result index must be a nonnegative integer")
        job = self.get_generation(generation_id)
        if job.get("status") != "completed" or len(job.get("results", [])) <= index:
            raise DetailXError("Generation has no completed result", code="result_unavailable")
        media = job["results"][index]
        errors = []
        for url in (media.get("url"), media.get("fallback_url")):
            if url:
                try:
                    return download_url(url, output, max_bytes=max_bytes, allow_private=self.allow_private_media)
                except (DetailXError, httpx.HTTPError) as exc:
                    errors.append(type(exc).__name__)
        raise DetailXError("Result download failed; query the generation again to refresh links", code="download_failed")
