# ACE-Step 安装说明

## 模型

模型发布页：[ACE-Step 1.5](https://huggingface.co/ACE-Step/ACE-Step-v1.5)。工作流使用以下准确文件名：

| 必需 | 文件 | 下载地址 | 安装到（相对 ComfyUI 根目录） |
| --- | --- | --- | --- |
| 是 | `acestep_v1.5_turbo.safetensors` | [ACE-Step-v1.5](https://huggingface.co/ACE-Step/ACE-Step-v1.5/tree/main) | `models/diffusion_models/` |
| 是 | `qwen_0.6b_ace15.safetensors` | [ACE-Step-v1.5](https://huggingface.co/ACE-Step/ACE-Step-v1.5/tree/main) | `models/text_encoders/` |
| 是 | `qwen_1.7b_ace15.safetensors` | [ACE-Step-v1.5](https://huggingface.co/ACE-Step/ACE-Step-v1.5/tree/main) | `models/text_encoders/` |
| 是 | `ace_1.5_vae.safetensors` | [ACE-Step-v1.5](https://huggingface.co/ACE-Step/ACE-Step-v1.5/tree/main) | `models/vae/` |

## ComfyUI 节点

使用当前 ComfyUI 核心的 `UNETLoader`、`DualCLIPLoader`、`TextEncodeAceStepAudio1.5`、`EmptyAceStep1.5LatentAudio`、`ModelSamplingAuraFlow`、`VAEDecodeAudio` 和 `SaveAudio`。无需额外节点包；若核心不存在这些类，请先更新 ComfyUI。

## 其他依赖与验证

无额外系统程序或云端 Key。重启 ComfyUI 后确认上述节点存在、四个模型能被加载，再重启 VideoFree Studio 网关。
