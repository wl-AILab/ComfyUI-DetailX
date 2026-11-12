# ComfyUI DetailX

通过 [DetailX](https://www.detail-x.ai) 云 API 为原生 `VIDEO` 工作流增加视频超分和可选补帧。包含 Upload Video、Quote、Submit、Fetch Video 四个节点，无需本地 GPU 或模型权重。

## 安装与配置

需要 ComfyUI **0.45.0+**、Python **3.10+**，以及具备 `read upload generate` 权限的 DetailX API Key 和积分。

在 ComfyUI-Manager 搜索 **DetailX Video Upscale**（包名 `comfyui-detailx`）安装并重启。也可以在 ComfyUI 目录手动安装：

```bash
git clone https://github.com/wl-AILab/ComfyUI-DetailX custom_nodes/ComfyUI-DetailX
python -m pip install -r custom_nodes/ComfyUI-DetailX/requirements.txt
```

必须使用 ComfyUI 自己的 Python 环境，并在启动进程中设置 `DETAILX_API_KEY`。Key 不写进节点输入和工作流 JSON；`.env.example` 不会自动加载。Linux 示例：

```bash
export DETAILX_API_KEY="dxk_YOUR_KEY"
python main.py
```

PowerShell：先执行 `$env:DETAILX_API_KEY = "dxk_YOUR_KEY"` 再启动 ComfyUI。公共 SDK 已内置在 `_vendor/detailx_sdk`，不需要额外发布或安装 PyPI 包。旧版 VHS 专有视频对象需先转换为原生 `VIDEO`。

## 使用

1. 拖入 `workflows/quote.json`，选择视频，为上传和生成分别设置唯一的 `request_id`，运行后在 **Preview as Text** 查看报价。这个工作流不提交付费生成。
2. 拖入 `workflows/upscale.json`，使用相同视频、ID 和参数复用报价。检查预扣积分后，在 Submit 中设置 `max_precharge_credits` 并开启 `confirm_charge`，再运行。
3. 下载结果以原生 `VIDEO` 返回并保存到 `output/DetailX`。`example_api_workflow.json` 是 `/prompt` 用的 API 格式，不用于拖入编辑器。

所有发布示例的确认默认关闭、预算默认 0。支持 720p、1080p、2K、4K，保留帧率或选择 24/30/60fps。Detail、灯光、色彩和运动选项默认沿用服务端设置。

## 收费与恢复

同一操作中断后保留原 request ID，新素材或参数必须使用新 ID。来源、参数、报价、幂等键和任务 ID 持久保存在 ComfyUI user 目录的 `detailx` 子目录，可用 `DETAILX_STATE_DIR` 指定持久目录。重启后复用相同 ID 可恢复任务；节点缓存失效不会创建第二个付费任务。保留此目录，不要通过删除状态重试收费操作。

Fetch 支持直接输入已有 generation ID 恢复。停止队列只停止本地等待，已受理任务仍会处理和结算，不代表取消或退款。预扣预算不是最终补扣的硬上限，实际结算与退款应以 DetailX 账户流水为准。报价或价格版本失效时，换新的生成 request ID 重新报价并确认。

输入视频会发送给 DetailX 及其媒体存储服务；结果链接会过期，请及时下载，并在上传敏感素材前核对服务条款与保留期限。这是第三方 API custom nodes，需要用户自己的账号和积分，不是 Comfy 官方 Partner Node。MIT 许可仅涵盖代码。

真实运行验收记录见 [VERIFICATION.md](VERIFICATION.md)，发布维护步骤见 [PUBLISHING.md](PUBLISHING.md)。反馈问题请使用 [GitHub Issues](https://github.com/wl-AILab/ComfyUI-DetailX/issues)，不要提交密钥、签名链接或私密素材。
