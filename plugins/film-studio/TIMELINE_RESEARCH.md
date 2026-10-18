# 成片时间线基础剪辑 · 可行性研究

> 研究结论已落地：P0/P1 范围（主轨顺序时间线 + 黑场、逐段音量与淡入淡出、转场、
> 叠加轨、额外音轨、片段缓存、快速预览与代理图）已实现，实现细节与运行数据见
> `README.md`；本文保留为设计依据与实测记录。字幕、自动语音识别和普通文字图层
> 已实现；尚未实现的是关键帧、变速和硬件编码。所有 FFmpeg 结论均用插件内置的 9.0.2 构建在本机实测过，
> 实测环境为合成素材（testsrc2 + sine），真实素材的编码耗时约为其 2–4 倍。

## 结论

可行，而且现有架构已经走了一半路。

- 现在的 `clips[]` 顺序数组 + `in/out` + 全局画幅，本质就是"单轨、无空档、无转场"
  的时间线退化形式；引擎的"逐段标准化 → 拼接"与时间线模型天然对齐。
- 内置 FFmpeg 具备时间线所需的全部原语：`xfade`、`acrossfade`、`overlay`、`adelay`、
  `amix`、`volume`、`afade`、`tpad`、`trim/setpts`、`concat`、`drawtext`、`ass/subtitles`、
  `showwavespic`、`thumbnail`，还带 `h264_nvenc/amf/qsv/mf` 硬件编码器。
- 成本不是障碍：24s 成片整片重渲 720p 1.5s、1080p 2.25s、480p15 代理 1.1s；
  转场链与单遍 filter graph 只多 0.2–0.4s。
- 真正的成本与风险在**前端时间线交互**和**预览策略**，不在 FFmpeg。

## 现状盘点

| 层 | 现状 | 与时间线的差距 |
| --- | --- | --- |
| 数据 | `clips[{job_id, artifact_index, in, out, original}]` + 全局 `bgm_job_id/volume/width/height/fps/fit` | 无绝对时间、无轨道、无逐片段音量/转场/位置 |
| 引擎 | 逐段标准化 → concat demuxer copy → BGM amix | 只能顺序、无空档、无转场、无叠加轨 |
| UI | 竖排卡片列表、上下移动按钮、数字输入裁剪、单镜头/成片 monitor | 无刻度尺、无拖拽、无波形缩略图、无分割 |
| 动作 | `film.list/sources/get/save/add-clip/select-source/progress/render/delete` | 缺预览、缺代理素材接口 |
| 前端依赖 | 仅 `vue` + `@iconify/vue`，框架内无时间线/拖拽组件 | 时间线交互需手写 pointer 事件 |

## 内置 FFmpeg 实测

| 能力 | 命令要点 | 实测 |
| --- | --- | --- |
| 转场 | `[a][b]xfade=transition=fade:duration=0.4:offset=O` 链 + `acrossfade=d=0.4` | 6 段 720p、5 次转场 0.92s，成片 22.000s = 24 − 5×0.4，偏移公式正确 |
| 画中画叠加 | `[1:v]scale=240:135,format=yuva420p[p];[0:v][p]overlay=x=W-250:y=20:enable='between(t,2,6)'` | 0.22s，时长不变，时间窗生效 |
| 空档（黑场+静音） | `color=black:s=WxH:r=F:d=D` + `anullsrc` 生成 gap 片段，再 concat | 0.09s 生成，拼接后 27.021s |
| 多音轨 | `[0:a]volume=0.4[a0];[1:a]adelay=1500|1500[a1];[a0][a1]amix=inputs=2:duration=longest:normalize=0` | 0.13s，视频流 `-c copy` 不动 |
| 逐片段淡入淡出 | `afade=t=in:st=0:d=0.5` / `fade=t=out:...` | 可用 |
| 中文字幕（drawtext） | `drawtext=fontfile='C\:/Windows/Fonts/msyh.ttc':text='中文…'` | 渲染出 7858 个亮点，字形正确；字体族名（fontconfig）不可用，必须显式字体文件 |
| 中文字幕（libass） | `ass=x.ass` / `subtitles=x.srt:charenc=utf-8`，用相对路径 + `cwd` | 渲染出 6969 / 1972 个亮点；libass 走 directwrite 字体提供，不需要 fontconfig |
| 波形图 | `showwavespic=s=2000x160` | 60s 素材 0.07s |
| 缩略图条 | `fps=1,scale=160:90,tile=10x6` | 60s 1080p 素材 0.66s；逐帧 2fps 出图 0.70s |
| 代理转码 | `scale=854:480,fps=15` + `ultrafast/crf32` | 60s 1080p → 1.08s |

### 整片重渲成本（24s 成片，6 段）

| 目标 | 耗时 | RTFx |
| --- | --- | --- |
| 1920x1080@30 veryfast crf20 | 2.25s | 10.7 |
| 1280x720@30 veryfast crf20 | 1.54s | 15.6 |
| 854x480@15 ultrafast crf32（预览代理） | 1.11s | 21.7 |
| 单遍 `filter_complex` concat（720p） | 0.78s | 30.8 |
| concat demuxer `-c copy` | 0.06–0.10s | — |

真实素材按 2–4 倍估算：3 分钟 1080p 成片整片重渲约 40–90s，因此**不能**"拖一下就重渲"。

## 三个必须避开的坑（实测确认）

1. **concat copy 有时间漂移**：6 段各 4.000s（120 帧）拼出 24.0213s，约 3.5ms/段。
   顺序播放无感，但时间线里算 xfade offset、空档位置、绝对落点会累积错位。
   → 偏移一律用**标准化后实测片段时长**累加，不用名义 `out-in`；
   或需要精确时间轴时改用单遍 `filter_complex` concat（实测精确 24.000s）。
2. **输入侧 `-ss` 会重置 PTS**：`-ss 1 -i x.mp4` 之后 `enable='between(t,...)'`、
   字幕时间都会按重置后的时间轴判定（实测字幕因此"看不见"）。
   → 时间线模式统一在 filter graph 内用 `setpts=PTS-STARTPTS+start/TB`，
   或把 seek 放到输出侧 / 加 `-copyts`。
3. **转场需要"把手"**：xfade 会吃掉两侧各 `duration` 的素材。裁剪点贴着素材末尾时
   没有可重叠帧 → 需要向素材余量借帧，或用 `tpad` 补最后一帧，否则转场处掉帧。

## 数据模型草案（向后兼容）

保持 `clips` 为"主轨顺序"旧写法可读可写，新增可选字段，读取时补算绝对时间：

```jsonc
{
  "timeline_version": 2,
  "tracks": [
    {"index": 0, "kind": "video", "clips": [
      {"job_id": "…", "artifact_index": 0, "in": 1.2, "out": 3.4,
       "start": 0.0,            // 绝对落点；缺省时按顺序累加
       "volume": 100,           // 逐片段音量
       "fade_in": 0.3, "fade_out": 0.3,
       "transition": {"type": "fade", "duration": 0.4},   // 与下一段之间
       "rect": null             // 叠加轨用：{x,y,w,h,opacity}
      }
    ]},
    {"index": 1, "kind": "overlay", "clips": [ /* 带 rect 的画中画 */ ]},
    {"index": 2, "kind": "audio",  "clips": [ /* 音效/配音，volume + fade */ ]}
  ],
  "bgm_job_id": "…", "volume": 18,
  "width": 1920, "height": 1080, "fps": 30, "fit": "contain"
}
```

校验规则要新增：同轨重叠检测（报错或自动 ripple）、总时长与片段数上限、
`transition.duration <= min(左右可借帧时长)`、`rect` 不超出画幅。
`FilmWrite` 现有 `extra='forbid'` 与 `max_length=500` 需按新结构重排，
但 `film.save` 的动作 id 与入参形状可以保持不变（旧客户端仍可存单轨顺序方案）。

## 引擎改造路径

1. **片段层不变**：逐段标准化仍是唯一重编码点，天然可缓存。
   缓存 key = `(job_id, artifact_index, in, out, width, height, fps, fit, volume, fade_in, fade_out)`，
   放 `films/<film_id>/segments/`，按 plan hash 做 LRU 清理。改一处只重渲一段。
2. **拼接分三档**（按 plan 自动选择）：
   - 顺序无空档无转场 → concat demuxer `-c copy`（现状，最快）
   - 有空档 → 生成 gap 片段后仍用 copy
   - 有转场/叠加/绝对落点 → 单遍 `filter_complex`（concat / xfade 链 / overlay 链）
3. **时间轴计算**：先标准化并 probe 每段实际时长，再累加出每段 `start`、
   xfade `offset`、overlay `enable` 窗口、`adelay` 毫秒数。
4. **音频**：主轨原声 + 叠加音轨（`volume`/`adelay`/`afade`）+ BGM（现有 amix）
   一次 `amix=normalize=0` 混完，避免多次重编码。
5. **校验**：沿用现有"输出必须含视频轨与音频轨 + 时长与画幅符合方案"，
   时长期望值改为**实测累加值**，容差按段数缩放（现有 `min(5, 0.5+0.02n)` 保留）。

## 预览策略（产品成败关键）

| 方案 | 成本 | 适用 |
| --- | --- | --- |
| 浏览器端零渲染预览：主轨用多个 `<video>` + JS 调度按 `start/in/out` 接力播放 | 零服务端成本，即时 | 单轨顺序剪辑的 90% 编辑动作（排序、裁剪、分割、删除） |
| 代理预览 `film.preview`：480p15 ultrafast 整片 | 24s 片 1.1s；3 分钟片约 15–30s | 有转场/叠加/混音时确认效果 |
| 片段级预览：只重渲被改的那一段并在浏览器里替换 | 单段亚秒级 | 拖动裁剪手柄时的实时反馈 |
| 刻度尺素材：每源一次缩略图条 + 波形，缓存复用 | 60s 素材约 0.7s | 时间线绘制，必须做 |

建议：编辑态一律走浏览器端预览 + 片段缓存；`film.render` 保持"高质量整片"语义不变；
新增 `film.preview` 与 `film.proxies`（返回缩略图条/波形 URL）两个动作。

## UI 拆解

`ui/FilmStudio.vue` 现在 21KB 单文件，需要拆成插件内组件（不新增前端依赖，手写 pointer 事件）：

- `TimelineRuler.vue` 刻度尺 + 缩放（px/s）
- `TimelineTrack.vue` 轨道容器、吸附、拖拽落点、波纹删除
- `TimelineClip.vue` 片段块、左右裁剪手柄、分割、音量标签、转场标记
- `TimelineInspector.vue` 选中片段的检视面板（现有 in/out/original 输入迁到这里）
- monitor 升级为"时间线播放头"驱动，代理预览与浏览器预览二选一

工作量集中在交互细节（拖拽手感、吸附、虚拟化渲染 >200 片段、撤销重做），
不在渲染。

## 风险清单

- concat copy 漂移与 PTS 重置（已量化，见上）
- 转场把手不足导致掉帧
- 叠加轨需统一像素格式（`yuva420p`）与画幅，否则 overlay 报错
- filter graph 深度：xfade/overlay 链是流式的，长片不炸内存，但**未实测 5 分钟以上**
- 中文字幕依赖系统字体（`msyh.ttc`）；跨平台一致需随插件带字体并处理授权
- 前端无时间线组件与拖拽库，手写成本高；片段数多时需虚拟化
- 片段缓存会占盘（每段约 1–5MB），需要 LRU 与项目删除时一并清理
- 预览产物不得进 `library_outputs`，否则素材库会被代理文件污染

## 分阶段建议

| 阶段 | 内容 | 量级 |
| --- | --- | --- |
| P0 单轨时间线 | 刻度尺 + 拖拽排序 + 拖拽裁剪 + 分割 + 波纹删除 + 缩略图/波形 + 浏览器端预览；schema 加 `start` | 1–2 天 |
| P1 时间线语义 | 逐片段音量与淡入淡出、空档黑场、转场（xfade/acrossfade）、多音轨混音；引擎切 filter_complex + 实测时长偏移；片段缓存 | 2–4 天 |
| P2 叠加与字幕 | 叠加轨（画中画/贴图 `rect`）、字幕（drawtext 或 ASS + 字体策略）、`film.preview` 代理预览一键高质量 | 3–5 天 |
| 明确不做 | 关键帧动画、调色、音频包络曲线、多机位同步、速度曲线 | — |

## 未验证项（诚实标注）

- 真实拍摄素材的编码 RTFx（本次用 testsrc2，噪声大的实拍会更慢）
- 5 分钟以上成片的 filter graph 内存与耗时
- 浏览器内 200+ 片段拖拽的帧率
- 硬件编码器（`h264_nvenc` 等）在本机的可用性与画质收益
