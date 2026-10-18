# Krea2 安装说明

## 模型

基础模型项目：[Krea 2 官方源码](https://github.com/krea-ai/krea-2)；ComfyUI 格式文件来自 [Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2)。

| 使用范围 | 文件 | 下载地址 | 安装到（相对 ComfyUI 根目录） |
| --- | --- | --- | --- |
| 全部生成模式 | `krea2_turbo_fp8_scaled.safetensors` | [直接下载](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/diffusion_models/krea2_turbo_fp8_scaled.safetensors) | `models/diffusion_models/` |
| 全部生成模式 | `qwen3vl_4b_fp8_scaled.safetensors` | [直接下载](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/text_encoders/qwen3vl_4b_fp8_scaled.safetensors) | `models/text_encoders/` |
| 全部生成模式 | `qwen_image_vae.safetensors` | [直接下载](https://huggingface.co/Comfy-Org/Krea-2/resolve/main/vae/qwen_image_vae.safetensors) | `models/vae/` |
| 人物四视图、分镜 | `krea2_identity_edit_v1_2.safetensors` | [ComfyUI-Krea2Edit 安装与权重说明](https://github.com/lbouaraba/comfyui-krea2edit) | `models/loras/` |
| 超清动作 | `OmniSR_X4_DIV2K.safetensors` | [OpenModelDB OmniSR](https://openmodeldb.info/models/4x-OmniSR) | `models/upscale_models/` |

超清工作流还引用 `realism_engine_krea2_v2.safetensors` 及一个 Krea2 painterly 风格 LoRA。它们属于可替换的风格 LoRA，不是 Krea 2 官方基础模型；放到 `models/loras/` 并在安装时按本机合法来源选择同名文件。若没有可信来源，应先在该工作流中换成用户已有、许可清楚的 Krea2 LoRA，不能从不明网盘自动下载。

## ComfyUI 节点

除当前 ComfyUI 核心外，安装以下节点包：

| 包 / Manager ID | 下载地址 | 安装到 | 本插件使用的节点 |
| --- | --- | --- | --- |
| `comfyui-krea2edit` | [lbouaraba/comfyui-krea2edit](https://github.com/lbouaraba/comfyui-krea2edit) | `custom_nodes/comfyui-krea2edit` | `Krea2EditGroundedEncode`、`Krea2EditModelPatch` |
| `comfyui-easy-use` | [yolain/ComfyUI-Easy-Use](https://github.com/yolain/ComfyUI-Easy-Use) | `custom_nodes/ComfyUI-Easy-Use` | `easy stylesSelector`、`easy showAnything`、数学节点 |
| `rgthree-comfy` | [rgthree/rgthree-comfy](https://github.com/rgthree/rgthree-comfy) | `custom_nodes/rgthree-comfy` | `Seed (rgthree)` |
| `comfyui_essentials` | [cubiq/ComfyUI_essentials](https://github.com/cubiq/ComfyUI_essentials) | `custom_nodes/ComfyUI_essentials` | `GetImageSize+` |
| `comfyui_ultimatesdupscale` | [ssitu/ComfyUI_UltimateSDUpscale](https://github.com/ssitu/ComfyUI_UltimateSDUpscale) | `custom_nodes/ComfyUI_UltimateSDUpscale` | `UltimateSDUpscale` |

部分可视化工作流还登记了 `comfyui-kjnodes`、`ComfyUI_Comfyroll_CustomNodes` 和 `ComfyUI_Lam`；通过 [ComfyUI Manager](https://github.com/ltdrdata/ComfyUI-Manager) 的缺失节点检查按实际启用工作流补装，不要仅凭目录名下载不明仓库。

风格库可选依赖 `custom_nodes/ComfyUI-Easy-Use/styles`。重启 ComfyUI 后确认模型专用节点、加载器和保存节点都可用。
