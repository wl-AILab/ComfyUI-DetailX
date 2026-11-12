from dataclasses import asdict, dataclass
from typing import Any

from .errors import DetailXError


@dataclass(frozen=True)
class GenerationOptions:
    resolution: str = "4K"
    fps: int = -1
    detail: str | None = None
    light_correct: bool | None = None
    flow_smooth: bool | None = None
    keep_color: bool | None = None
    trajectory_smooth: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        if self.resolution not in ("720p", "1080p", "2K", "4K"):
            raise DetailXError("resolution must be 720p, 1080p, 2K or 4K", code="invalid_options")
        if type(self.fps) is not int or self.fps not in (-1, 24, 30, 60):
            raise DetailXError("fps must be -1, 24, 30 or 60", code="invalid_options")
        if self.detail is not None and self.detail not in ("1", "2", "3"):
            raise DetailXError("detail must be a string: 1, 2 or 3", code="invalid_options")
        result = {k: v for k, v in asdict(self).items() if v is not None}
        for key in ("light_correct", "flow_smooth", "keep_color", "trajectory_smooth"):
            if key in result and type(result[key]) is not bool:
                raise DetailXError(f"{key} must be boolean", code="invalid_options")
        return result


def source_params(options: GenerationOptions, upload_id: str | None, source_result_id: str | None) -> dict[str, Any]:
    if bool(upload_id) == bool(source_result_id):
        raise DetailXError("Exactly one upload_id or source_result_id is required", code="invalid_source")
    return {**options.to_dict(), **({"upload_id": upload_id} if upload_id else {"source_result_id": source_result_id})}


@dataclass(frozen=True)
class PreparedGeneration:
    request_id: str
    scope: str
    idempotency_key: str
    body: dict[str, Any]
    quote: dict[str, Any]

    @property
    def credits(self) -> int:
        return int(self.body["expected_credits"])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PreparedGeneration":
        return cls(**{k: value[k] for k in ("request_id", "scope", "idempotency_key", "body", "quote")})
