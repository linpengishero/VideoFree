# 剪辑插件安装说明

## 模型

自动字幕默认使用 `openai/whisper-large-v3-turbo`（界面值 `large-v3-turbo`）：[Hugging Face](https://huggingface.co/openai/whisper-large-v3-turbo)。Whisper 节点可在首次使用时下载到自己的模型缓存；其具体缓存位置由该节点包管理，不要把模型放进 VideoFree Studio 插件目录。

## ComfyUI 节点

- [ComfyUI-Whisper](https://github.com/yuvraj108c/ComfyUI-Whisper)：安装到 `custom_nodes/ComfyUI-Whisper`，本插件使用 `Apply Whisper`。也可通过 ComfyUI Manager 搜索同名包并核对节点类；不同实现若不提供该类则不兼容。
- [rgthree-comfy](https://github.com/rgthree/rgthree-comfy)：安装到 `custom_nodes/rgthree-comfy`，使用 `Display Any (rgthree)`。
- `LoadAudio` 来自 ComfyUI 核心。

## 其他依赖与验证

VideoFree API 使用 `zh`/`en` 等稳定语言值；插件提交给 ComfyUI-Whisper 时会转换为其要求的 `Chinese`/`English` 枚举。

中文自动字幕必须安装 `opencc-python-reimplemented`，用于将 Whisper 输出统一转换为简体中文。在 VideoFree Studio 使用的 Python 环境中安装插件依赖：

```powershell
python -m pip install --target "runtime/python/Lib/site-packages" -r plugins/film-studio/requirements.txt
```

未安装时中文识别任务会明确失败并提示安装依赖；英文识别不需要 OpenCC。

FFmpeg 与 ffprobe 是必需的系统依赖，不随 VideoFree Studio 或本插件提交、下载或分发：

- 官方下载入口：[ffmpeg.org/download.html](https://ffmpeg.org/download.html)。
- Windows 可使用官方页面列出的构建，解压后把包含 `ffmpeg.exe` 和 `ffprobe.exe` 的 `bin` 目录加入系统 `PATH`。
- Debian/Ubuntu：`sudo apt install ffmpeg`。
- macOS（Homebrew）：`brew install ffmpeg`。

安装后在**启动 VideoFree Studio 的同一终端环境**执行 `ffmpeg -version` 和 `ffprobe -version`，两条命令都成功才算完成。随后重启 VideoFree Studio。剪辑、预览、代理图、波形和自动字幕的时间线混音都会使用这两个命令；缺失时只影响剪辑插件，不影响其他生成插件。

重启 ComfyUI 后还应验证 `Apply Whisper` 和 `Display Any (rgthree)`，再在剪辑页执行一次短音频自动字幕。
