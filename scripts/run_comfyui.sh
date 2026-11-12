#!/usr/bin/env bash
set -eu

# Use the Python environment that already contains ComfyUI's requirements.
: "${COMFYUI_DIR:?Set COMFYUI_DIR to your ComfyUI checkout}"
: "${DETAILX_API_KEY:?Set DETAILX_API_KEY before starting ComfyUI}"
COMFYUI_PYTHON="${COMFYUI_PYTHON:-python}"
cd "$COMFYUI_DIR"
exec "$COMFYUI_PYTHON" main.py "$@"
