import json
import os
import tempfile
from pathlib import Path

try:
    from ._vendor.detailx_sdk import DetailXClient, GenerationOptions, PreparedGeneration
    from ._vendor.detailx_sdk.errors import DetailXError
except ModuleNotFoundError:
    from detailx_sdk import DetailXClient, GenerationOptions, PreparedGeneration
    from detailx_sdk.errors import DetailXError


def client():
    import folder_paths
    return DetailXClient(state_dir=os.environ.get("DETAILX_STATE_DIR", str(Path(folder_paths.get_user_directory()) / "detailx")))


def progress(_):
    from comfy.model_management import throw_exception_if_processing_interrupted
    throw_exception_if_processing_interrupted()


def source(upload_id, source_result_id):
    return {"upload_id": upload_id.strip() or None, "source_result_id": source_result_id.strip() or None}


class DetailXUploadVideo:
    CATEGORY = "DetailX"
    FUNCTION = "run"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("upload_id", "upload_session_json")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"video": ("VIDEO",), "request_id": ("STRING", {"default": "upload-001"})}}

    def run(self, video, request_id):
        if not request_id.strip():
            raise ValueError("request_id is required")
        with tempfile.TemporaryDirectory(prefix="detailx-comfy-") as temporary:
            path = Path(temporary) / "source.mp4"
            video.save_to(str(path))
            with client() as api:
                session = api.upload_video(path, request_id=request_id, on_progress=progress)
        return (session["asset_id"], json.dumps({k: session[k] for k in ("id", "asset_id", "status")}))


class DetailXQuote:
    CATEGORY = "DetailX"
    FUNCTION = "run"
    RETURN_TYPES = ("DETAILX_PREPARED", "INT", "STRING")
    RETURN_NAMES = ("prepared", "estimated_credits", "quote_json")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "upload_id": ("STRING", {"default": ""}), "source_result_id": ("STRING", {"default": ""}),
            "request_id": ("STRING", {"default": "generation-001"}),
            "resolution": (["720p", "1080p", "2K", "4K"], {"default": "4K"}),
            "fps": (["preserve", "24", "30", "60"], {"default": "preserve"}),
            "detail": (["default", "1", "2", "3"],),
            "light_correct": (["default", "on", "off"],), "flow_smooth": (["default", "on", "off"],),
            "keep_color": (["default", "on", "off"],), "trajectory_smooth": (["default", "on", "off"],),
        }}

    @classmethod
    def IS_CHANGED(cls, **_):
        return float("nan")

    def run(self, upload_id, source_result_id, request_id, resolution, fps, detail="default", **toggles):
        if not request_id.strip():
            raise ValueError("request_id is required")
        options = GenerationOptions(resolution, -1 if fps == "preserve" else int(fps), None if detail == "default" else detail,
                                    **{k: None if v == "default" else v == "on" for k, v in toggles.items()})
        with client() as api:
            prepared = api.prepare_generation(options, **source(upload_id, source_result_id), request_id=request_id, max_precharge_credits=2**53 - 1)
        report = json.dumps({"request_id": request_id, **prepared.quote}, indent=2)
        return {"ui": {"text": [report]}, "result": (prepared.to_dict(), prepared.credits, report)}


class DetailXSubmit:
    CATEGORY = "DetailX"
    FUNCTION = "run"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("generation_id", "generation_json")
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"prepared": ("DETAILX_PREPARED",), "confirm_charge": ("BOOLEAN", {"default": False}),
                             "max_precharge_credits": ("INT", {"default": 0, "min": 0, "max": 2147483647})}}

    def run(self, prepared, confirm_charge, max_precharge_credits):
        value = PreparedGeneration.from_dict(prepared)
        if not confirm_charge:
            raise DetailXError("Enable confirm_charge after reviewing the quote", code="confirmation_required")
        if value.credits > max_precharge_credits:
            raise DetailXError("Quote exceeds max_precharge_credits", code="budget_exceeded")
        progress({})
        with client() as api:
            job = api.submit(value)
        report = json.dumps({"id": job["id"], "status": job["status"]})
        return {"ui": {"text": [report]}, "result": (job["id"], report)}


class DetailXFetchVideo:
    CATEGORY = "DetailX"
    FUNCTION = "run"
    RETURN_TYPES = ("VIDEO", "STRING")
    RETURN_NAMES = ("video", "result_json")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"generation_id": ("STRING", {"default": ""}),
                             "timeout_seconds": ("INT", {"default": 1800, "min": 1, "max": 86400})}}

    @classmethod
    def IS_CHANGED(cls, **_):
        return float("nan")

    def run(self, generation_id, timeout_seconds):
        import folder_paths
        from comfy_api.latest import InputImpl
        from hashlib import sha256
        with client() as api:
            job = api.wait(generation_id, timeout=timeout_seconds, on_progress=progress)
            destination = Path(folder_paths.get_output_directory()) / "DetailX" / (sha256(generation_id.encode()).hexdigest()[:24] + ".mp4")
            api.download_result(generation_id, destination)
        report = json.dumps({"id": job["id"], "credits": job.get("credits"), "results": [
            {k: r.get(k) for k in ("id", "width", "height", "duration", "expires_at")} for r in job.get("results", [])]})
        return (InputImpl.VideoFromFile(str(destination)), report)


NODE_CLASS_MAPPINGS = {"DetailXUploadVideo": DetailXUploadVideo, "DetailXQuote": DetailXQuote, "DetailXSubmit": DetailXSubmit, "DetailXFetchVideo": DetailXFetchVideo}
NODE_DISPLAY_NAME_MAPPINGS = {"DetailXUploadVideo": "DetailX Upload Video", "DetailXQuote": "DetailX Quote", "DetailXSubmit": "DetailX Submit", "DetailXFetchVideo": "DetailX Fetch Video"}
