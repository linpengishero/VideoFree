---
name: zizai-media-gateway
description: 自由之手 (Zizai) LAN media gateway — local GPU image/video/speech/music generation through the zizai_* tools. Use when generating stills, video clips, voiceover, or music in this project instead of paid cloud APIs. Triggers include 自由之手, zizai, gpt-image-2.5, MiniMax H3, multi-reference video, preset voice, background music.
metadata:
  author: OpenMontage integration
  version: "1.0.0"
  tags: zizai, lan-gateway, local-gpu, image, video, tts, music
---

# 自由之手媒体网关（局域网 GPU 主机）

本项目的四类生成默认走局域网网关，不消耗云端 key：`zizai_image`、`zizai_video`、
`zizai_tts`、`zizai_music`（provider = `zizai`，runtime = `local_gpu`）。

网关地址在 `.env`：`ZIZAI_API_URL`（示例 `http://192.168.50.8:8765`），
`ZIZAI_API_TOKEN` 仅在网关启用 `MEDIA_GATEWAY_TOKEN` 时才需要填。
网关是第一台机器的能力：**它关机/端口不通时四类生成全部不可用**，
`preflight` 会显示 `zizai_*` 为 unavailable —— 先让用户把网关跑起来，别改走付费云。

## 能力与上限（网关实测）

| 工具 | 网关能力 | 关键上限 |
|---|---|---|
| `zizai_image` | `image.gpt_image.{text_to_image,image_to_image,character,scene,storyboard_4,storyboard_6}` | 参考图 0-8 张（character 恰好 1 张）；比例 8 种；分辨率 480P-2K |
| `zizai_video` | `video.reference`（MiniMax H3 全能参考）、`video.text_to_image`… | 参考图 0-9、参考视频 0-3、参考音频 0-3；**时长 1-15 秒**；变体 normal/fast/quick_preview/preview |
| `zizai_video`（LTX） | `video.ltx2_5.multi_reference` | 恰好 3 张参考图（subject_1..3），时长上限 30 秒 |
| `zizai_tts` | `tts.preset` / `tts.describe` | 18 个预设音色；describe 时文本当音色描述 |
| `zizai_music` | `music.create`（MiniMax Music 3） | 时长 1-360 秒 |

## 请求字段位置（踩过的坑，必须照做）

- **图片**：原生模型写在 `settings.native_model`（`gpt-image-2.5`），不是 model_id。
  参考图统一用角色 `reference`，网关自己按子能力布局。
- **视频**：`model_id: minimax-h3` + `mode_id: reference`（多参考）；参考图进
  `inputs[{type:image, upload_id, role:reference}]`。
- **配音**：朗读文本走顶层 `prompt`，音色走顶层 `voice_id`。
- **音乐**：`lyrics` 走**顶层**，`music_style_id` / `singer_id` / `voice_texture_id`
  必须在 **`settings`** 里 —— 放顶层会被静默忽略（网关改用默认流行+女声预设）。
  这三个 id 必须是网关预设，空值会 422。

## 预设目录

- 配音音色（`/api/v2/voices`，18）：`orion_7` 星河、`documentary_female` 纪录片女声、
  `narrator_male`/`narrator_female` 叙事男/女声、`news_male`/`news_female` 资讯、
  `warm_male`/`warm_female` 温暖/温柔、`calm_male`/`calm_female` 沉静、`young_*` 年轻 …
- 音乐风格（10）：pop / chinese 国风 / rock / folk / rnb / electronic / rap / jazz /
  **cinematic 电影感** / healing 治愈；歌手：female / male；
  音色纹理（9）：natural / smoky / clear / magnetic / sweet / deep / powerful / ethereal / warm。

## 宫格分镜：角色一致性最好的一条路

分别生成多张图时，角色会飘。**一次出一张宫格**（4 格或 6 格画在同一张画面里）一致性
天然稳得多，然后切成单格，逐格送进视频生成。

```
storyboard_4   zizai_image  generation_mode=storyboard_4  shots=[4 段]
storyboard_6   zizai_image  generation_mode=storyboard_6  shots=[6 段]   ← 格多，适合长分镜
               角色参考图放 image_paths（0-8 张），推荐 1 张大头/半身像
               切割默认自动开：4 格走 `split`，6 格走 `split_6`（3×2 行优先）
               结果 artifacts = [宫格图, 单格 1..N]；data.grid / data.panels 分别可取
```

**宫格是"分镜"用的，不是动作拆解**：每一格是**不同的镜头 / 不同时刻 / 不同状态**
（远景→中景→特写→结尾），这样才发挥它的价值。**一个连续动作不要拆成几格** —— 那是
一个镜头的事，整镜生成即可；拆了反而每格都短、都碎。

- 实测：四宫格约 60-70 秒（1K，gpt-image-2.5），六宫格同等量级；角色/服装/光线跨格高度一致。
- 已有宫格图想补切：`generation_mode="split"`（4 格）或 `"split_6"`（6 格）+ 恰好 1 张宫格图。
- 场景图用 `generation_mode="scene"`（同场景多视角/多状态，参考图 0-8 张）。
- 角色单图用 `generation_mode="character"`（**恰好 1 张**参考图）。
- 家族可选 `image_family`：默认 `gpt_image`（gpt-image-2.5）；`qwen` 也支持 scene/storyboard_4/6；
  `krea2` 只有基础几种（工具会自动回落到 gpt_image）。
- `shots` 段数必须精确（4 或 6），段数不对网关会静默降级成普通文生图 —— 工具会先拦下。

## 提示词：默认走网关编译（prompt_mode）

MiniMax 吃的是它自己的专业描述词，**口语描述直连提交容易不对味**。所以
`zizai_video` 默认 `prompt_mode="compiled"`，走网关 `POST /v1/agent/translate-h3`
（`{text, mode}` → `{english_prompt}`，单次调用）：

    输入  老渔夫在天亮前的码头上收网，镜头慢慢推近，海面有薄雾
    产出  The old fisherman hauls in the net on the dock before dawn, the camera slowly pushes in,
          and there is thin mist on the sea surface.

兜底顺序：translate-h3 → 协作 quick → 直连（失败原因记在结果 `compile_error`）。
`prompt_mode="raw"` 只在提示词已经是专业稿时用。LTX 2.5 只支持 director 协作，跳过编译。

结果的这三个字段要留意：`prompt_brief`（原始描述）、`prompt`（实际提交的稿子）、
`prompt_mode_used`（compiled(translate-h3) / compiled(collaboration) / raw / raw(compile_failed)）。

## 两段式工作流：抽卡 → H3 二采（默认姿势）

抽卡慢的根因是"不满意就重抽整条片段"。网关对**已完成的任务**支持 refine
（`POST /v1/jobs/{id}/refine`，openapi 实测四种模式）：

```
h3_refine              H3 二采 —— 默认，同一条片段重采样到目标分辨率
preview_refine_fast    预览精修（快）
preview_refine_stable  预览精修（稳）
ltx_ultra              LTX 放大（慢，只在 H3 二采不可用时考虑）
```

```
第一段  zizai_video       480P + quick_preview（8/12 步）≈ 2.5 分钟一条 → 快速抽卡
                          ★ 记下 job_id 和 seed（seed 用于复现）
第二段  zizai_video_post  refine_mode=h3_refine + target_height=720/1080 ≈ 2.5 分钟
                          → 同一条片子重采样，人物/动作/构图保留，只抬质量
```

实测（5 秒片段）：480P quick_preview 158s → h3_refine 到 720p 153s，产物 864x480 →
1312x736。**不要**用"提高分辨率重抽"来定稿（会换人换动作），也别用 `ltx_ultra`。
想改内容/动作才重新生成（`regenerate` 可保留血缘）。

refine 挂在网关任务上，所以只对网关产出的片段有效；本地视频走不了这条路。

## 其他可用旋钮

- `seed`：锁种子，抽到满意构图后记下来，复现/二采都靠它。
- `style_lora`：`cinemagrade` = 电影感调色；`camera_lora`：`auto` / `crash_zoom` / `off`。

## 运行特性

- 提交后返回 `job_id`，靠循环 `wait`（单次上限 120 秒）推进；视频/音乐是**分钟级**：
  生图约 1 分钟、配音约 40 秒、30 秒音乐约 3 分钟、5 秒视频约 6 分钟。
- 产物 URL 是网关相对路径，工具会自动下载到 `output_path`，并按产物真实格式
  修正扩展名（网关给 FLAC 时不会留下假的 `.wav`/`.mp3`）。
- 提示词/素材相同会命中幂等；失败的任务不会自动重试视频（太贵），交给上层决定。

## 已知不完美（别当 bug 反复尝试）

- 音乐**时长不是硬控**：请求 30 秒实测得到约 20.6 秒。合成阶段按实际长度裁剪/循环。
- 音乐**没有纯音乐开关**：`instrumental` 只是把"无人声"写进歌词前缀，尽力而为。
- 图片的实际像素由 provider 决定，请求 720P 不保证正好 720 像素边。
- 视频产物 1312x736 这类非标准尺寸是正常现象（24fps，H.264 + AAC）。
- 网关仍有自己的 director 协作模式；**本项目一律用 direct 生成**，把审批闸门留在
  OpenMontage 自己的 gate 上，避免两层审批叠着问用户。

## 自有素材

用户自己的 BGM 放项目根目录 `music_library/`（`music_library` 工具零依赖读取）；
自己的参考图/首帧图直接给本地路径，工具会先上传到网关再生成。
