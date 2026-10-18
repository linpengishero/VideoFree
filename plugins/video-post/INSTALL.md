# 视频后期处理安装说明

## 模型

| 使用范围 | 文件 | 下载地址 | 安装到（相对 ComfyUI 根目录） |
| --- | --- | --- | --- |
| 插帧 | `rife47.pth` | [ComfyUI-Frame-Interpolation](https://github.com/Fannovel16/ComfyUI-Frame-Interpolation)（节点通常自动下载） | 节点包自己的 `ckpts/rife/` 目录，以其当前 README 为准 |
| LTX 超清 | `ltx-2.5-22b-distilled-transformer-bf16.safetensors` | [直接下载](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/diffusion_models/ltx-2.5-22b-distilled-transformer-bf16.safetensors) | `models/diffusion_models/LTX-2.5/` |
| LTX 超清 | `gemma4-12b-with-proj-ltx-2.5-bf16.safetensors` | [直接下载](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/text_encoders/gemma4-12b-with-proj-ltx-2.5-bf16.safetensors) | `models/text_encoders/LTX-2.5/` |
| LTX 超清 | `ltx-2.5-video-vae-bf16.safetensors` | [直接下载](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/vae/ltx-2.5-video-vae-bf16.safetensors) | `models/vae/LTX-2.5/` |
| LTX 超清 | `ltx-2.5-audio-vae-bf16.safetensors` | [直接下载](https://huggingface.co/Lightricks/LTX-2.5/resolve/main/vae/ltx-2.5-audio-vae-bf16.safetensors) | `models/vae/LTX-2.5/` |
| LTX 去模糊 | `ltx-2.3-22b-ic-lora-deblur-0.9.safetensors` | [直接下载](https://huggingface.co/Lightricks/LTX-2.3-22b-IC-LoRA-Deblur/resolve/main/ltx-2.3-22b-ic-lora-deblur-0.9.safetensors) | `models/loras/LTX-2.5/` |
| LTX 量化工作流分支 | `ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors` | [LTX-2.5 文件列表](https://huggingface.co/Lightricks/LTX-2.5/tree/main) | `models/diffusion_models/LTX-2.5/` |
| LTX 量化工作流分支 | `gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot.safetensors` | [LTX-2.5 文件列表](https://huggingface.co/Lightricks/LTX-2.5/tree/main) | `models/text_encoders/LTX-2.5/` |
| LTX 空间超清分支 | `ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors` | [LTX-2.5 文件列表](https://huggingface.co/Lightricks/LTX-2.5/tree/main) | `models/loras/LTX-2.5/` |

工作流明确使用 `LTX-2.5/` 子目录，不能把这些文件平铺到其他目录或擅自改名。

## ComfyUI 节点

通过 ComfyUI Manager 安装：

- `comfyui-frame-interpolation` → `custom_nodes/ComfyUI-Frame-Interpolation`（`RIFE VFI`）
- `comfyui-videohelpersuite` → `custom_nodes/ComfyUI-VideoHelperSuite`（`VHS_LoadVideo`、`VHS_VideoCombine`）
- `comfyui-kjnodes` → `custom_nodes/ComfyUI-KJNodes`（`GetImageSizeAndCount`）
- [pythongosssss/ComfyUI-Custom-Scripts](https://github.com/pythongosssss/ComfyUI-Custom-Scripts) → `custom_nodes/ComfyUI-Custom-Scripts`（`MathExpression|pysssss`）
- [yolain/ComfyUI-Easy-Use](https://github.com/yolain/ComfyUI-Easy-Use) → `custom_nodes/ComfyUI-Easy-Use`（`easy showAnything`）
- [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo)（LTX 超清节点）

工作流还含 ComfyUI 核心节点。重启后先执行 Manager 缺失节点检查，再分别验证插帧和超清动作。
