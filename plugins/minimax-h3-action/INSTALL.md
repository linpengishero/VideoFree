# 连戏 · MiniMax-H3 安装说明

本插件打包了已实测的导演协作分段续写工作流（原始 UI 快照见 `workflows/source/`，插件执行使用 `workflows/video/two_segment_reference.json` API 快照）。时长字段填整片总时长（1–75 秒）：不超过 15 秒单段直接生成；超过 15 秒自动分为 2–5 段，第一段由参考图生成，后续每段以上一段末尾的 5 帧运动片段作为 H3 引导续写，最后自动拼接画面与声音为一条完整视频。导演协作管线：需求与素材策划（可多轮追问）→ 导演技能规划 → 整篇导演成稿（导演为总时长撰写一篇完整的六段式英文草稿，逐镜头 `[Shot N]` + 时间戳）→ 镜头呼吸点拆分（编辑环节沿动作短语完成点、落点、定格等可续拍呼吸点把整稿切成 2–5 段，段长可不等；段数、时长、镜头不重不漏、台词不跨段等由代码确定性校验）→ 逐段格式转换（每段转成独立的 H3 ref2va 六段式执行稿，含人数锁定与段间接续句）→ 链式契约检查 → 中文确认稿翻译。整条链路一次提交、一个任务。插件不会自动下载任何模型。

## 运行环境

- VideoFree Studio（含网关与 ComfyUI 执行器）；
- ComfyUI ≥ 0.37.0（`BlockSparseAttention` 等节点按 comfy-core 0.37 的 DynamicCombo V3 格式序列化，即 `selection.tau` 点号键；缺失时先升级 ComfyUI 到支持 MiniMax-H3 的版本）。

## 模型

**完整模型包（推荐国内用户使用）**：[夸克网盘「models」](https://pan.quark.cn/s/b89d63346833)（提取码：`b0763bgX3m`）。据分享者说明，压缩包包含本插件所需的全部模型。下载并解压后，将其中的 `models/` 目录合并到 ComfyUI 根目录，保留子目录结构及文件名大小写；如遇同名文件，先核对文件后再决定是否覆盖。

| 必需 | 文件 | Hugging Face | 国内镜像（hf-mirror.com） | 安装到（相对 ComfyUI 根目录） |
| --- | --- | --- | --- |
| 必需 | `Cobijada_H3_Hybrid_Uncensored_pruned_hybrid_int8_convrot_pruned.safetensors` | 本轮未找到可核验的公开下载地址；可从上方夸克完整模型包获取 | 未找到可核验的公开镜像地址；可从上方夸克完整模型包获取 | `models/diffusion_models/minimax/` |
| 必需 | `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` | [Hugging Face 直链](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors) | [hf-mirror 国内镜像直链](https://hf-mirror.com/Comfy-Org/MiniMax-H3/resolve/main/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors) | `models/text_encoders/` |
| 必需 | `minimax_h3_video_vae_fp16.safetensors` | [Hugging Face 直链](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_fp16.safetensors) | [hf-mirror 国内镜像直链](https://hf-mirror.com/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_video_vae_fp16.safetensors) | `models/vae/` |
| 必需 | `minimax_h3_audio_vae_fp32.safetensors` | [Hugging Face 直链](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors) | [hf-mirror 国内镜像直链](https://hf-mirror.com/Comfy-Org/MiniMax-H3/resolve/main/vae/minimax_h3_audio_vae_fp32.safetensors) | `models/vae/` |
| 必需 | `minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors` | [Hugging Face 直链](https://huggingface.co/RunningHubAI/rh-minimax-h3-ref2v-turbo-8step-v1.0-768p-comfyui-bf16.safetensors-lora/resolve/main/minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors) | [hf-mirror 国内镜像直链](https://hf-mirror.com/RunningHubAI/rh-minimax-h3-ref2v-turbo-8step-v1.0-768p-comfyui-bf16.safetensors-lora/resolve/main/minimax_h3_ref2v_turbo_8step_v1.0_768p_comfyui_bf16.safetensors) | `models/loras/MINIMAX/` |
| 必需 | `H3_speed_slider_1.1.safetensors` | [Hugging Face 仓库页](https://huggingface.co/RunningHubAI/rh-h3-speed-slider-1.1-lora/tree/main)（下载前核对仓库内文件名） | [hf-mirror 国内镜像仓库页](https://hf-mirror.com/RunningHubAI/rh-h3-speed-slider-1.1-lora/tree/main)（镜像文件清单未能确认） | `models/loras/MINIMAX/` |
| 必需 | `Motion_Repair_V2.safetensors` | 本轮未找到可核验的公开下载地址；可从上方夸克完整模型包获取 | 未找到可核验的公开镜像地址；可从上方夸克完整模型包获取 | `models/loras/MINIMAX/` |
| 必需 | `H3_Combat_V2.safetensors` | [Hugging Face 直链](https://huggingface.co/JOKER141/MiniMax-H3-Combat-Base-V2/resolve/main/H3_Combat_V2.safetensors) | [hf-mirror 国内镜像直链](https://hf-mirror.com/JOKER141/MiniMax-H3-Combat-Base-V2/resolve/main/H3_Combat_V2.safetensors) | `models/loras/MINIMAX/` |

**国内镜像核验说明（2026-10-23）**：`hf-mirror.com` 上确认存在表中官方文本编码器、VAE 和 8-step LoRA 文件；Combat LoRA 的同名文件在 Hugging Face 仓库目录中确认。速度 LoRA 搜索到对应仓库，但镜像文件清单请求超时，所以这里只链接仓库页。融合底模与 Motion Repair 未找到可核验的公开来源，可使用分享者提供的夸克完整模型包；不要用相似文件替代。下载前仍应检查文件名、哈希（如发布方提供）和使用许可。

LoRA 目录名区分大小写：工作流按 `MINIMAX/<文件>` 相对 `models/loras/` 加载。

## ComfyUI 节点

| 必需 | 包 / Manager ID | 下载地址 | 安装到 | 本插件使用的节点类 |
| --- | --- | --- | --- | --- |
| 必需 | ComfyUI 核心（comfy-core ≥ 0.37.0） | ComfyUI 本体升级 | — | `MiniMaxH3ReferenceToVideo`、`MiniMaxH3AddGuide`、`MiniMaxH3SigmaShift`、`BlockSparseAttention`、`ModelAttentionBackend`、`EasyCache`、`ComfyMathExpression`、`GetImageRangeFromBatch`、`ImageBatchMulti`、`AudioConcat`、`SaveAudioAdvanced`、`PrimitiveInt`、`PrimitiveFloat` 及标准采样/加载/解码节点 |
| 必需 | ComfyUI-VideoHelperSuite（`comfyui-videohelpersuite`） | [Kosinkadink/ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite) | `custom_nodes/ComfyUI-VideoHelperSuite` | `VHS_VideoCombine`（最终输出）、`VHS_LoadVideo`（参考视频绑定） |

其余节点（`UNETLoader`、`CLIPLoader`、`VAELoader`、`LoraLoaderModelOnly`、`BasicGuider`、`BasicScheduler`、`ManualSigmas`、`RandomNoise`、`KSamplerSelect`、`SamplerCustomAdvanced`、`VAEDecode`、`VAEDecodeAudio`、`LoadImage`、`LoadAudio`）由 ComfyUI 核心提供。原始工作流中的 `ModelPreviewOverrideKJ`（ComfyUI-KJNodes）仅用于实时预览，插件快照已移除，不需要安装。

## 其他依赖

无 Python / 系统 / 云端 Key 依赖；全部推理在本地 ComfyUI 完成。显存需求随分辨率、段数与各段时长上升（总时长最长 75 秒 = 5 段 × 15 秒）。

“导演协作”使用 VideoFree Studio 设置中已配置的 AI 对话模型，完整复用官方 minimax-h3 导演技能包（需求策划、导演编译、一致性审查、中文翻译与各动作技能）；未配置 AI 模型时本插件不可用。画幅由你在提交界面选择（比例 8 档、分辨率 480P–768P，全部段共用），导演只负责段数与各段时长（可不等长）；16GB 显存下 720P/768P 段数多时耗时明显增加。

## 安装验证

1. 重启 ComfyUI，确认上表节点均可搜索到、模型文件出现在对应目录；
2. 重启 VideoFree 网关，在视频生成器中选择「MiniMax H3 长片」→「全能参考」（英文：MiniMax H3 Long-form → All-in-one Reference）。这是插件的正式生成入口，支持设置整片时长、比例和分辨率；
3. 上传 1–6 张参考图，填写剧情描述与总时长（1–75 秒），选择比例、分辨率后提交导演协作。导演依据提示词、参考素材与用户所选总时长完成策划；≤15 秒生成单段，>15 秒自动规划分段。生成器的协作面板可回答追问、查看中英文稿并确认生成，确认后一个任务产出一条合并视频（含连续声音）。导演不改写用户选择的比例和分辨率。

生成器协作面板源码为 `ui/Collaboration.js` 与 `ui/Collaboration.css`，修改后运行 `node plugins/minimax-h3-action/ui/build.mjs` 将组件和样式打包到 `ui/dist/collaboration.js`，然后重启网关；不需要重建框架前端。面板显示真实导演阶段与分段进度，追问可选择后一次提交；确认稿支持中英文切换与放大查看，确认生成按钮会在提交期间禁用。


分段时长会在生成确认前校验为合计等于整片总时长（允许 0.05 秒浮点误差）。H3 工作流按 24 FPS 并受 `17k+5` 帧数约束，实际导出时长可能与计划存在少量帧级偏差；这是模型/工作流帧数约束，不代表计划时长被静默改写。参考图片、视频和音频均绑定到每个续写段，后续段还会额外使用上一段末帧保持画面连续。

常见缺失错误：`MiniMaxH3ReferenceToVideo` 不存在 → ComfyUI 版本过旧；`VHS_VideoCombine` 不存在 → 未安装 VideoHelperSuite；LoRA 加载失败 → 检查 `models/loras/MINIMAX/` 目录名与文件名大小写。

## 许可证与自动下载说明

- 官方 H3 文本编码器与 VAE 的许可按 [MiniMax-AI/MiniMax-H3](https://github.com/MiniMax-AI/MiniMax-H3) 发布说明执行；
- Turbo、速度及 Combat LoRA 来自社区仓库，使用和再分发许可分别以对应仓库说明为准；融合底模与 Motion Repair 的原始来源仍未确认。夸克网盘仅是用户提供的下载渠道，不代表模型许可或再分发授权；无法确认许可时不要用于商用或再分发；
- 插件导入与网关启动阶段不联网下载任何依赖。
