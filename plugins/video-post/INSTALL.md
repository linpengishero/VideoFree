# 视频后期处理安装说明

## 模型

插帧使用 `rife47.pth`，由 [ComfyUI-Frame-Interpolation](https://github.com/Fannovel16/ComfyUI-Frame-Interpolation) 管理并通常自动下载到该节点包约定的模型目录。超清工作流使用 [LTX 2.5](https://huggingface.co/Lightricks/LTX-2.5) 的 transformer、文本编码器、视频/音频 VAE 和 IC-LoRA；保持工作流中的 `LTX-2.5/` 子目录与文件名。

## ComfyUI 节点

通过 ComfyUI Manager 安装：

- `comfyui-frame-interpolation` → `custom_nodes/ComfyUI-Frame-Interpolation`（`RIFE VFI`）
- `comfyui-videohelpersuite` → `custom_nodes/ComfyUI-VideoHelperSuite`（`VHS_LoadVideo`、`VHS_VideoCombine`）
- `comfyui-kjnodes` → `custom_nodes/ComfyUI-KJNodes`（`GetImageSizeAndCount`）
- `comfyui-custom-scripts`（`MathExpression|pysssss`）
- `comfyui-easy-use`（`easy showAnything`）
- [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo)（LTX 超清节点）

工作流还含 ComfyUI 核心节点。重启后先执行 Manager 缺失节点检查，再分别验证插帧和超清动作。
