# CosyVoice3 安装说明

## 模型

必需仓库 `FunAudioLLM/Fun-CosyVoice3-0.5B`：[Hugging Face](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B) / [ModelScope](https://modelscope.cn/models/iic/Fun-CosyVoice3-0.5B)。`FL_CosyVoice3_ModelLoader` 默认由 ModelScope 下载并管理缓存，因此**没有固定的 ComfyUI `models/` 安装目录**；若选择手工离线安装，目录和配置方式必须遵循 [ComfyUI_Fill-Nodes](https://github.com/filliptm/ComfyUI_Fill-Nodes) 的当前说明，不能放入 VideoFree Studio 插件源码目录。

## ComfyUI 节点

安装 [ComfyUI_Fill-Nodes](https://github.com/filliptm/ComfyUI_Fill-Nodes) 到 `custom_nodes/ComfyUI_Fill-Nodes`。本插件使用 `FL_CosyVoice3_ModelLoader`、`FL_CosyVoice3_Instruct2`、`FL_CosyVoice3_ZeroShot`；`LoadAudio`、`SaveAudioMP3` 来自 ComfyUI 核心。

## 其他依赖与验证

首次模型自动下载需要网络和足够磁盘空间。预设声音 MP3 已随插件分发。重启 ComfyUI 后确认上述三个 `FL_` 节点可用并能加载模型。
