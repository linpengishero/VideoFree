# Krea2 安装说明

## 模型

模型项目：[Krea 2](https://huggingface.co/krea/krea-2)。工作流要求：

- `models/diffusion_models/krea2_turbo_fp8_scaled.safetensors`
- `models/diffusion_models/krea2_identity_edit_v1_2.safetensors`
- `models/text_encoders/qwen3vl_4b_fp8_scaled.safetensors`
- `models/vae/qwen_image_vae.safetensors`

## ComfyUI 节点

除当前 ComfyUI 核心外，随附 UI 工作流引用以下 Manager ID：`comfyui-easy-use`、`comfyui-kjnodes`、`rgthree-comfy`、`comfyui_essentials`、`ComfyUI_Comfyroll_CustomNodes`、`ComfyUI_Lam`、`comfyui_ultimatesdupscale`。优先通过 [ComfyUI Manager](https://github.com/ltdrdata/ComfyUI-Manager) 按 ID 安装到 `custom_nodes/`；本插件运行图包含 `Krea2EditGroundedEncode`、`Krea2EditModelPatch`、`QwenImage21Cache` 等模型专用类，安装后以 ComfyUI 缺失节点检查为准。

风格库可选依赖 `custom_nodes/ComfyUI-Easy-Use/styles`。重启 ComfyUI 后确认模型专用节点、加载器和保存节点都可用。
