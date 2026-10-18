# MiniMax Music 3 安装说明

## 模型

模型与说明入口：[MiniMax-Music3](https://github.com/MiniMax-AI/MiniMax-Music3)。

| 必需 | 文件 | 下载地址 | 安装到（相对 ComfyUI 根目录） |
| --- | --- | --- | --- |
| 是 | `minimax_music3_dit_int4_convrot.safetensors` | [MiniMax-Music3 官方项目](https://github.com/MiniMax-AI/MiniMax-Music3) | `models/diffusion_models/` |
| 是 | `minimax_music3_text_encoder_pruned_int8_convrot.safetensors` | [MiniMax-Music3 官方项目](https://github.com/MiniMax-AI/MiniMax-Music3) | `models/text_encoders/` |
| 是 | `minimax_music3_dav.safetensors` | [MiniMax-Music3 官方项目](https://github.com/MiniMax-AI/MiniMax-Music3) | `models/vae/` |

## ComfyUI 节点

使用当前 ComfyUI 核心的 `MiniMaxMusic3TextEncode`、`EmptyMiniMaxMusic3LatentAudio`、`VAEDecodeAudioTiled` 及通用加载/采样/保存节点；缺失时更新 ComfyUI。

## 验证

重启后确认三个模型能加载，并分别运行创作模式和预设模式的短时长测试。
