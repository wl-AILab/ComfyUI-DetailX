# Release acceptance: 0.1.0

Verified on 2026-11-12 with ComfyUI **0.45.0**, frontend **1.58.5**, Python **3.12.3**, PyAV **17.1.0**, Linux and CPU-only PyTorch. Inference ran on the real DetailX service; this integration needs no local GPU.

## Real ComfyUI queue and real API

- Generated an original two-second H.264/AAC test pattern: 640 x 360, 24 fps, mono audio. No customer video was used.
- Queued native LoadVideo -> DetailX Upload Video -> DetailX Quote, displaying the result with native PreviewAny. Quoted precharge: **2 credits**, 720p, preserved frame rate.
- Queued the complete chain with confirmation disabled and then with an insufficient budget. Both were rejected by DetailX Submit before creating a paid generation.
- Enabled confirmation with a precharge budget of 10 credits and submitted **one** generation. Interrupted local waiting after the generation ID was durably saved.
- Restarted the actual ComfyUI server. Retrieved the same generation directly through DetailX Fetch Video and native SaveVideo, then re-ran the complete upload/quote/submit/fetch/save chain using the same request IDs.
- Both recovery paths succeeded and reused the original generation ID. The account contained **one** corresponding billing transaction. Final settled charge: **2 credits**.
- Decoded the saved MP4: **1280 x 720**, **24 fps**, **48 frames**, **2.0 seconds**, one decodable audio stream. Audio decoding yielded 96,256 samples including AAC padding.

The API-format SaveVideo example uses flattened dynamic-combo fields (`format` and `format.codec`), as required by this ComfyUI version. Nested dictionaries are the normalized node-call representation, not the queue prompt representation.

## Automated checks

Four standalone package tests cover confirmation, budget enforcement, immutable parameters and generation reuse across recreated clients. The release checker validates required files, visual-workflow links, safe billing defaults, publisher metadata, accidental credentials and prohibited Python eval/exec calls. Runtime `pip check` passed.

Both visual examples were loaded in the actual ComfyUI frontend using headless Chrome and converted back to API prompts. All nodes and links resolved, SaveVideo's dynamic format/codec serialized correctly, billing confirmation remained disabled with a zero budget, and the browser reported no page errors. No paid prompt was submitted by this browser check.

## Limits

This acceptance verifies integration behavior and decodable output, not general perceptual quality. It does not benchmark GPU inference, every resolution and frame rate, very large media, or every operating system. Mocked tests cover API guards; they cannot replace real billing checks. The configured budget limits precharge, not possible final settlement adjustments. Registry review and indexing are separate from these runtime checks.

Private task IDs, account data, signed media URLs, credentials and runtime state are excluded from the repository and registry package.
