# Comfy Registry 上架与维护

| 项目 | 配置 |
| --- | --- |
| GitHub | https://github.com/wl-AILab/ComfyUI-DetailX |
| Registry PublisherId | `wlailab`，页面显示为 `@wlailab` |
| 包名 / 首版 | `comfyui-detailx` / `0.1.0` |
| Registry 页面 | https://registry.comfy.org/publishers/wlailab/nodes/comfyui-detailx |
| GitHub Actions Secret | `REGISTRY_ACCESS_TOKEN`，仅存 Registry 发布 Key |

GitHub 账号是 `wl-AILab`，与 Registry PublisherId 分别配置。DetailX 调用 Key 只用于用户运行节点，不上传 GitHub Secret 或公开包。Registry Key 用于发布，不作为 DetailX 服务凭据。

## 首版状态（2026-11-12）

- [GitHub Release v0.1.0](https://github.com/wl-AILab/ComfyUI-DetailX/releases/tag/v0.1.0) 已发布；[Python 3.10 / 3.12 CI](https://github.com/wl-AILab/ComfyUI-DetailX/actions/runs/43177514616) 通过。
- [官方 Registry 发布 Action](https://github.com/wl-AILab/ComfyUI-DetailX/actions/runs/43177660863) 成功。Registry 节点为 `NodeStatusActive`，版本 `0.1.0` 为 `NodeVersionStatusPending`，仍需平台审核和索引；不能将其视为已经审核通过。
- 已使用 comfy-cli 1.26.0 的 `node registry-install comfyui-detailx --version 0.1.0`，在另一份 ComfyUI 0.45.0 源码目录从实际 Registry CDN 包安装。两个目录共用已验收的 CPU Python 环境。
- 实包含 26 个文件，必要源码、内置 SDK 与可视化工作流均与发布源码相同，不含测试、CI、开发脚本、密钥或状态库。四个节点成功加载，Fetch → 原生 SaveVideo 对已有任务验收通过，输出 1280×720、48 帧、含音轨，没有新建收费任务。
- 官方 `node.zip` SHA256：`56a70c3ebfbe1ba197a9f9f641cbdef06b5d82a2183602380b563f1d281b5469`。

当前无需补充发布凭据。版本审核状态可通过 [Registry API](https://api.comfy.org/nodes/comfyui-detailx/versions/0.1.0) 查询；Manager 未显示时，可按 README 从 GitHub 安装使用。未来发布继续沿用下面流程。

## 发布前

使用本目录作为独立仓库根目录，保留 `_vendor/detailx_sdk`。依赖与当前 ComfyUI 自己的 Python 环境安装在一起：

```bash
python -m pip install -r requirements-test.txt
python -m pytest tests -q
python scripts/check_release.py
```

`scripts/build_workflows.py` 可重新生成可拖入编辑器的工作流。示例确认默认关闭、预扣预算默认 0。真实运行与账单验收见 [VERIFICATION.md](VERIFICATION.md)。

`.gitignore` 排除密钥、SQLite 状态、日志与工作目录；`.comfyignore` 进一步从 Registry 包排除 CI、测试和开发脚本。发布器只打包 git 跟踪文件，并强制包含 `_vendor`。

## 发布流程

1. 修改 `pyproject.toml` 版本与 `CHANGELOG.md`。版本使用 `X.Y.Z`，已发布版本不可当作覆盖更新使用。
2. 推送代码，等待 **Check custom nodes** 的 Python 3.10、3.12 检查通过。
3. 创建并发布与版本一致的 GitHub Release，例如 `v0.1.1`。随附 **Publish Comfy Registry package** 工作流会先测试，再通过官方 `Comfy-Org/publish-node-action` 发布。也可在 Actions 页面手动运行一次该工作流；同一版本选择一种方式发布，避免重复。
4. 核对 Registry API 版本状态和页面。上传成功、安全审核通过、Manager 可搜索是不同状态，不能混为一谈。
5. 在干净的 ComfyUI 环境从 Registry/Manager 安装对应版本，检查依赖、四个节点和样例。等待审核时可按 README 从 GitHub 手动安装。

CLI 备用流程，在本仓库运行 `comfy node publish`，按隐藏提示输入发布 Key。不要把发布 Key 写入命令行脚本、工作流 JSON 或仓库。

## 运行环境

`scripts/run_comfyui.sh` 使用已安装的 ComfyUI 环境：

```bash
export COMFYUI_DIR=/path/to/ComfyUI
export COMFYUI_PYTHON=/path/to/venv/bin/python
export DETAILX_API_KEY="dxk_YOUR_KEY"
export DETAILX_STATE_DIR=/persistent/detailx
bash scripts/run_comfyui.sh --cpu --listen 127.0.0.1 --port 8189
```

本插件是云 API 节点，CPU 环境可完整验收，不需要占用本地 GPU。长期运行应保留 `DETAILX_STATE_DIR`；停止等待后通过已有 generation ID 恢复，不要新建任务替代重试。

官方：[Publishing](https://docs.comfy.org/registry/publishing)、[Standards](https://docs.comfy.org/registry/standards)、[Metadata](https://docs.comfy.org/registry/specifications)。
