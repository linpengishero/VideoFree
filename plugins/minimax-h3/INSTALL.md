# MiniMax H3 安装说明

## 模型

官方项目：[MiniMax-AI/MiniMax-H3](https://github.com/MiniMax-AI/MiniMax-H3)。模型下载和许可条件以官方项目发布说明为准；插件不会自动下载。工作流使用的准确文件和目录如下：

| 使用范围 | 文件 | 下载地址 | 安装到（相对 ComfyUI 根目录） |
| --- | --- | --- | --- |
| 基础/首尾帧 | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | [MiniMax-H3 官方项目](https://github.com/MiniMax-AI/MiniMax-H3) | `models/diffusion_models/` |
| 参考生成 | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | [MiniMax-H3 官方项目](https://github.com/MiniMax-AI/MiniMax-H3) | `models/diffusion_models/` |
| 部分参考二采 | `minimax_h3_ref2va_pruned_w4a8_mixed.safetensors` | [MiniMax-H3 官方项目](https://github.com/MiniMax-AI/MiniMax-H3) | `models/diffusion_models/` |
| 全部模式 | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | [MiniMax-H3 官方项目](https://github.com/MiniMax-AI/MiniMax-H3) | `models/text_encoders/` |
| 全部模式 | `minimax_h3_video_vae_fp16.safetensors`、`minimax_h3_audio_vae_fp32.safetensors` | [MiniMax-H3 官方项目](https://github.com/MiniMax-AI/MiniMax-H3) | `models/vae/` |
| 快速档 | `minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors`、`minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` | [MiniMax-H3 官方项目](https://github.com/MiniMax-AI/MiniMax-H3) | `models/loras/` |
| H3 latent 二采 | `minimax_h3_latent_upscaler_3d_fp16.safetensors` | [MiniMax-H3 官方项目](https://github.com/MiniMax-AI/MiniMax-H3) | `models/latent_upscale_models/` |
| LTX 超清二采 | `ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5) | `models/diffusion_models/` |
| LTX 超清二采 | `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5) | `models/text_encoders/` |
| LTX 超清二采 | `ltx-2.5-video-vae-bf16.safetensors`、`ltx-2.5-audio-vae-bf16.safetensors` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5) | `models/vae/` |
| LTX 超清二采 | `ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors` | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5) | `models/loras/` |

## ComfyUI 节点

工作流把 `MiniMaxH3ReferenceToVideo`、`MiniMaxH3ImageToVideo`、`MiniMaxH3SigmaShift`、H3 latent checkpoint/upscale 节点登记为当前 ComfyUI 节点；缺失时先更新到 MiniMax-H3 官方说明要求的 ComfyUI 版本。LTX 二采还要求 [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo)，安装到 `custom_nodes/ComfyUI-LTXVideo`。保存视频所需的 `SaveVideo`/`CreateVideo` 必须在当前 ComfyUI 中可用。

重启 ComfyUI 后分别检查 H3 文生/图生/首尾帧/参考模式以及所选二采档位；显存需求随模型量化和分辨率变化。
