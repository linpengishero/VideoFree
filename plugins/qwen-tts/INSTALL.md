# Qwen3-TTS 安装说明

## 模型

工作流使用 `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`、`Qwen/Qwen3-TTS-12Hz-1.7B-Base` 和 `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice`，来源为 [Qwen Hugging Face](https://huggingface.co/Qwen)。`Qwen3Loader` 可从 Hugging Face/ModelScope 自动下载到节点自己的模型缓存；若指定本地路径，遵守节点文档，不能放入插件源码目录。

## ComfyUI 节点

安装 [ComfyUI-Qwen3-TTS](https://github.com/DarioFT/ComfyUI-Qwen3-TTS) 到 `custom_nodes/ComfyUI-Qwen3-TTS`。本插件使用 `Qwen3Loader`、`Qwen3VoiceDesign`、`Qwen3VoiceClone`；音频加载和保存来自 ComfyUI 核心。

## 验证

首次模型下载需要网络。重启 ComfyUI 后分别加载 VoiceDesign、Base 和 CustomVoice 仓库并生成短音频。
