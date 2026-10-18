# Qwen Image 2.1 安装说明

## 模型

官方来源：[Qwen-Image-2.1](https://github.com/QwenLM/Qwen-Image-2.1)、[T2I 模型](https://huggingface.co/Qwen/Qwen-Image-2.1-PE-T2I)、[I2I 模型](https://huggingface.co/Qwen/Qwen-Image-2.1-PE-I2I)。工作流使用：

- `models/diffusion_models/Qwen/qwen_image_2.1_int8_convrot.safetensors`
- `models/text_encoders/qwen3vl_8b_int8_convrot.safetensors`
- `models/vae/qwen_image_2.1_vae_bf16.safetensors`

## ComfyUI 节点

使用当前 ComfyUI 核心的 Qwen Image 2.1 节点，包括 `TextEncodeQwenImage21`、`QwenImage21Cache`、`TESpeedQwenImage21` 与通用加载/采样/保存节点。缺失时更新 ComfyUI。

重启后分别验证文生图、图生图、人物、场景和分镜模式。
