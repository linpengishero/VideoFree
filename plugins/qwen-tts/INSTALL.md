# Qwen3-TTS 安装说明

## 模型

工作流使用以下仓库：

- [`Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign)
- [`Qwen/Qwen3-TTS-12Hz-1.7B-Base`](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base)
- [`Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice)

`Qwen3Loader` 从 Hugging Face/ModelScope 自动下载到节点自己的模型缓存，因此没有固定的 ComfyUI `models/` 目录。离线部署必须遵循 [ComfyUI-Qwen3-TTS](https://github.com/DarioFT/ComfyUI-Qwen3-TTS) 的当前本地路径配置，不能放入插件源码目录。

## ComfyUI 节点

安装 [ComfyUI-Qwen3-TTS](https://github.com/DarioFT/ComfyUI-Qwen3-TTS) 到 `custom_nodes/ComfyUI-Qwen3-TTS`。本插件使用 `Qwen3Loader`、`Qwen3VoiceDesign`、`Qwen3VoiceClone`；音频加载和保存来自 ComfyUI 核心。

## 验证

首次模型下载需要网络。重启 ComfyUI 后分别加载 VoiceDesign、Base 和 CustomVoice 仓库并生成短音频。
