# 剪辑插件安装说明

## 模型

自动字幕默认使用 `openai/whisper-large-v3-turbo`（界面值 `large-v3-turbo`）：[Hugging Face](https://huggingface.co/openai/whisper-large-v3-turbo)。Whisper 节点可在首次使用时下载到自己的模型缓存；其具体缓存位置由该节点包管理，不要把模型放进 VideoFree 插件目录。

## ComfyUI 节点

- [ComfyUI-Whisper](https://github.com/yuvraj108c/ComfyUI-Whisper)：安装到 `custom_nodes/ComfyUI-Whisper`，本插件使用 `Apply Whisper`。也可通过 ComfyUI Manager 搜索同名包并核对节点类；不同实现若不提供该类则不兼容。
- [rgthree-comfy](https://github.com/rgthree/rgthree-comfy)：安装到 `custom_nodes/rgthree-comfy`，使用 `Display Any (rgthree)`。
- `LoadAudio` 来自 ComfyUI 核心。

## 其他依赖与验证

Windows x64 的 FFmpeg/ffprobe 已随插件放在 `binaries/windows-x64/`，来源和许可证见 `licenses/`。其他平台需从 [FFmpeg 官方下载页](https://ffmpeg.org/download.html) 安装可执行文件并确保进程可访问。重启 ComfyUI 后先验证 `Apply Whisper` 和 `Display Any (rgthree)`，再在剪辑页执行一次短音频自动字幕。
