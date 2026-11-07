# simplicio-videos

> 由智能体驱动的确定性视频引擎：输入一份 YAML 合约，输出一个 MP4，并围绕它提供音频、视频、语音、角色替换、社交排期、素材授权与网络检索等工具箱。

[英文及所有语言：规范版 README](../README.md) · [葡萄牙语](../README.pt-BR.md)

## 功能概览

- **合约到 MP4：** 校验 YAML 合约、生成旁白，用 HyperFrames 确定性渲染，混音为 -14 LUFS，并写出清单（manifest）。渲染路径中不运行任何 LLM。
- **语音：** 提供方 `file`、`local`（Kokoro-82M）、`gemini`、`voxcpm`、`openvoice` 和 `voicestudio`（本地应用）。`elevenlabs` 和 `xai` 为占位实现（stub）。
- **音视频（`media`）：** 探测、提取音轨、帧表、字幕、框选遮罩、配音，以及下载单个公开视频并附带来源记录（provenance）。
- **竖版剪辑（`shorts`）：** 依据逐词转录，用固定规则为长视频中的片段打分，切出 9:16 片段。
- **EDL 剪辑（`edit`）：** 由智能体编写 EDL，固定版本的 video-use 辅助工具调用 ffmpeg 执行。
- **模板、动效、格式与角度：** 14 个行业模板（8 个可直接渲染）、55 个动效目录条目、50 种广告格式、50 个角度。
- **角色替换与后台任务（`swap`、`jobs`）：** 通过六个适配器进行付费替换，附成本估算和美元上限，仅可在终端中运行；swap 与本地语音可作为后台任务运行。
- **外部制作轨道：** Hypit、OpenMontage、OpenCut、Toonflow、MoneyPrinterTurbo，均已固定版本，作为独立程序运行，从不被导入。
- **社交排期（`social`）：** 按各网络的限制检查视频并生成计划。**从不发布。**
- **授权素材库（`openverse`）：** 搜索、安全下载、按请求审核、带署名导出。
- **网络检索（`busca`）：** 通过 TinyFish 进行查询和页面读取，每条结果附来源和日期，并有每日调用上限。
- **UGC 轨道：** 合成人物的提示词文件和手动流程，不参与渲染。
- **智能体集成：** MCP 服务器（28 个 `video.*` 工具）、6 个 skills，以及可安装到 11 个智能体宿主的 `install`。
- **运维：** 状态、已固定的工具、诊断、工作区、更新，以及共享的 Simplicio 登录。

## 快速开始

```bash
gh repo clone simpletibr/simplicio-videos && cd simplicio-videos
pip install -e .                      # `simplicio-video` command (Python >= 3.10); rendering needs Node >= 22 and ffmpeg
simplicio-video setup                 # first run
simplicio-video install               # copy the skills into your agent host (project; --global for the home folder)
simplicio-video doctor                # check what is missing

cd clients/<cliente>/<campanha>       # a client project with a contract.yaml
simplicio-video validate contract.yaml
simplicio-video voice contract.yaml   # narration; local draft voice or --provider file|gemini|voxcpm|openvoice|voicestudio
simplicio-video render contract.yaml  # out/<cliente>-<campanha>.mp4 + render.manifest.json
```

## 限制

- **未验证的替换适配器：** `fal`、`wavespeed`、`kie` 和 `alibaba` 依据公开文档编写，尚未在真实 API 上验证。
- **不发布：** 引擎从不向社交网络发布或上传内容。
- **平台：** 该软件包被归类为 Linux；macOS 和 Windows 尚未在实机上确认。

本摘要比[规范版 README](../README.md) 简短，可能落后于它。
