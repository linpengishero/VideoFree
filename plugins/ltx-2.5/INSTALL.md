# LTX 2.5 安装说明

## 模型

官方发布页：[Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5)。至少安装：

- `models/diffusion_models/ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors`
- `models/latent_upscale_models/ltx-2.5-latent-spatial-upscaler-x2-bf16-1.0.safetensors`

具体模式还会引用同发布页的 Gemma 文本编码器、视频/音频 VAE 和 IC-LoRA；保留工作流内 `LTX-2.5/` 子目录及准确文件名。

## ComfyUI 节点

更新 ComfyUI 以获得 LTX 核心节点。多参考/首尾帧工作流还使用 [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo)、[VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) 和 [KJNodes](https://github.com/kijai/ComfyUI-KJNodes)，分别安装到 `custom_nodes/ComfyUI-LTXVideo`、`custom_nodes/ComfyUI-VideoHelperSuite`、`custom_nodes/ComfyUI-KJNodes`。

重启后用 ComfyUI Manager 的缺失节点检查逐个核对随附工作流，再运行最小 480P 测试。
