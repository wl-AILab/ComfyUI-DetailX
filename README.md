# ComfyUI DetailX

Video super-resolution and optional frame interpolation through the [DetailX](https://www.detail-x.ai) cloud API, using native ComfyUI `VIDEO` inputs and outputs.

[中文说明](README.zh-CN.md) | [Release instructions](PUBLISHING.md) | [Changelog](CHANGELOG.md)

## Requirements

- ComfyUI **0.45.0 or newer**, Python **3.10+**. Tested on Linux with Python 3.12 and ComfyUI 0.45.0 in CPU mode; no local model or GPU is required for these API nodes.
- A DetailX account, credits, and an API key with `read`, `upload`, and `generate` permissions.
- Outbound HTTPS access to DetailX and its signed media storage URLs.

This is an independent third-party API integration. It is not an official Comfy Partner Node. The MIT license covers this code; the cloud service has its own terms and usage charges. No model weights are distributed.

## Install

Search for **DetailX Video Upscale** (`comfyui-detailx`) in ComfyUI-Manager and install. Restart ComfyUI after installation.

For a manual installation, run the following from your ComfyUI directory, using **ComfyUI's own Python environment**:

```bash
git clone https://github.com/wl-AILab/ComfyUI-DetailX custom_nodes/ComfyUI-DetailX
python -m pip install -r custom_nodes/ComfyUI-DetailX/requirements.txt
```

Set the API key in the environment of the process that starts ComfyUI:

```bash
export DETAILX_API_KEY="dxk_YOUR_KEY"
python main.py
```

On PowerShell, use `$env:DETAILX_API_KEY = "dxk_YOUR_KEY"` before launching ComfyUI. The key is never a node widget and must not be added to workflow JSON. `.env.example` documents the variables; ComfyUI does not load this file automatically. `DETAILX_STATE_DIR` optionally selects a persistent state directory, defaulting to `<ComfyUI user directory>/detailx`.

The Python client is bundled in `_vendor/detailx_sdk`; there is no separate SDK package to install. Legacy VideoHelperSuite-specific video objects must first be converted to native `VIDEO`.

## Workflow

```text
Load Video -> DetailX Upload Video -> DetailX Quote -> DetailX Submit
             -> DetailX Fetch Video -> Save Video
```

1. Drag `workflows/quote.json` into ComfyUI. Choose your input video and set unique upload and generation `request_id` values. Queue it and read the quote in **Preview as Text**. This workflow never submits a paid generation.
2. Drag `workflows/upscale.json` into ComfyUI. Use the same file, request IDs and options to reuse that quote. Review the quoted credits, set `max_precharge_credits`, and enable `confirm_charge` in **DetailX Submit** before queuing.
3. The result is saved under `output/DetailX`. `example_api_workflow.json` is the equivalent API-format prompt for `/prompt`; it cannot be dragged into the editor. All shipped submit nodes default to confirmation **off** and a budget of **0**.

Resolutions: `720p`, `1080p`, `2K`, `4K`. Frame rate: preserve, 24, 30 or 60. Detail, lighting, smoothing and color options default to the service defaults.

| Node | Purpose |
| --- | --- |
| DetailX Upload Video | Serialize native VIDEO, upload in resumable parts and return an upload ID. |
| DetailX Quote | Prepare an immutable quote, returning the estimated precharge and JSON. May also use `source_result_id` instead of `upload_id`. |
| DetailX Submit | Require explicit confirmation and a sufficient precharge budget, then submit or recover the same generation. |
| DetailX Fetch Video | Wait for a generation ID, download its result and return native VIDEO plus result metadata. |

## Billing and recovery

- Use a **new request ID for a new video or changed parameters**. Keep the same ID when recovering the same operation. Reusing an ID with changed inputs is rejected.
- Quotes, immutable request parameters, idempotency keys and generation IDs persist in SQLite. Keep the state directory across restarts. Re-running with the same IDs recovers the same generation; an expired quote or pricing change is rejected rather than silently accepted.
- To recover a submitted job, enter its generation ID directly in **DetailX Fetch Video**. Stopping a ComfyUI queue stops local waiting, not the server task or its billing.
- The budget caps the **quoted precharge**, not any final settlement adjustment. Review your DetailX account's transactions for the actual charge or refund.
- Input videos and generated media are sent to DetailX and its media storage. Result links may expire. Download important outputs promptly and review DetailX's service and retention terms before sending sensitive material.

If authentication fails, check the process environment and API key permissions. If a quote is stale, create a new generation request ID and review a new quote. Do not delete state merely to retry a paid request.

## Development

```bash
python -m pip install -r requirements-test.txt
python -m pytest tests -q
python scripts/check_release.py
```

Tests cover explicit confirmation, budget enforcement and durable generation reuse. See [VERIFICATION.md](VERIFICATION.md) for the real-runtime release acceptance and its limits. Report reproducible issues through [GitHub Issues](https://github.com/wl-AILab/ComfyUI-DetailX/issues), without API keys, signed media URLs or private videos.
