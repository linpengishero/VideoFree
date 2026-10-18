# MiniMax H3 安装说明

## 模型

官方项目：[MiniMax-AI/MiniMax-H3](https://github.com/MiniMax-AI/MiniMax-H3)。本插件工作流会使用 H3 基础/参考模型、H3 视频与音频 VAE、Qwen3-VL 文本编码器、H3 3D latent upscaler；超清二采还会使用 [LTX 2.5](https://huggingface.co/Lightricks/LTX-2.5) 的模型。准确文件名以 `workflows/` 中加载节点为准，安装到对应的 `models/diffusion_models`、`models/text_encoders`、`models/vae`、`models/latent_upscale_models` 和 `models/loras` 子目录，不能改名。

常用 H3 文件包括 `minimax_h3_ref2va_pruned_int8_convrot.safetensors`、`minimax_h3_fl2va_pruned_int8_convrot.safetensors`、`minimax_h3_video_vae_fp16.safetensors`、`minimax_h3_audio_vae_fp32.safetensors` 和 `minimax_h3_latent_upscaler_3d_fp16.safetensors`。

## ComfyUI 节点

工作流登记为当前 ComfyUI 核心节点，包括 `MiniMaxH3ReferenceToVideo`、`MiniMaxH3ImageToVideo`、`MiniMaxH3SigmaShift` 及 H3 latent checkpoint/upscale 节点；缺失时先更新 ComfyUI。LTX 二采还要求 [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo)。

重启 ComfyUI 后分别检查 H3 文生/图生/首尾帧/参考模式以及所选二采档位；显存需求随模型量化和分辨率变化。
