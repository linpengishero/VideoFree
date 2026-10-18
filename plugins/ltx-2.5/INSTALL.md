# LTX 2.5 安装说明

## 模型

官方发布页：[Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5)。按实际启用模式安装：

| 使用范围 | 文件 / 仓库 | 下载地址 | 安装到（相对 ComfyUI 根目录） |
| --- | --- | --- | --- |
| 全部模式 | `ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` | [直接下载](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors) | `models/diffusion_models/` |
| 全部模式 | `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | [直接下载](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/text_encoders/gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors) | `models/text_encoders/` |
| 全部模式 | `ltx-2.5-video-vae-bf16.safetensors` | [直接下载](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/vae/ltx-2.5-video-vae-bf16.safetensors) | `models/vae/` |
| 带音频模式 | `ltx-2.5-audio-vae-bf16.safetensors` | [直接下载](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/vae/ltx-2.5-audio-vae-bf16.safetensors) | `models/vae/` |
| 文生/图生视频 | `ltx-2-spatial-upscaler-x2-1.0.safetensors` | [直接下载](https://huggingface.co/Lightricks/LTX-2/resolve/main/ltx-2-spatial-upscaler-x2-1.0.safetensors) | `models/latent_upscale_models/` |
| 其他高分辨率工作流 | `ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors` | [LTX-2.5 文件列表](https://huggingface.co/Lightricks/LTX-2.5/tree/main) | `models/latent_upscale_models/` |
| 多参考 | `LTX-2.5-Licon-MSR-V1.safetensors` | [LTX-2.5 文件列表](https://huggingface.co/Lightricks/LTX-2.5/tree/main) | `models/loras/` |

旧版工作流片段还可能显示 `ltx-av-step-1751000_vocoder_24K.safetensors` 或 Gemma 原始仓库目录；当前注册能力优先使用上表的 ComfyUI 格式文件。不要同时随意改名，实际下拉值必须与工作流一致。

## ComfyUI 节点

更新 ComfyUI 以获得 LTX 核心节点。工作流还使用：

| 包 | 下载地址 | 安装到 | 主要节点 |
| --- | --- | --- | --- |
| ComfyUI-LTXVideo | [Lightricks/ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo) | `custom_nodes/ComfyUI-LTXVideo` | LTX 引导、参考和多参考节点 |
| VideoHelperSuite | [Kosinkadink/ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) | `custom_nodes/ComfyUI-VideoHelperSuite` | `VHS_VideoCombine` |
| KJNodes | [kijai/ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes) | `custom_nodes/ComfyUI-KJNodes` | `FloatConstant`、`INTConstant`、`ImageResizeKJv2` |

重启后用 ComfyUI Manager 的缺失节点检查逐个核对随附工作流，再运行最小 480P 测试。
