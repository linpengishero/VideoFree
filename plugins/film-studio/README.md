# 成片插件（film-studio）

项目内的成片方案、时间线剪辑与基础合成。时间线实现完全归插件所有，不依赖仓库内的
其他技能源码；FFmpeg 与 FFprobe 是用户安装的系统依赖，通过 `PATH` 发现，不随仓库分发。

## 目录

```text
plugins/film-studio/
├── plugin.json                     能力、动作、应用入口与固定资源声明（唯一注册来源）
├── actions.py                      HTTP/MCP 动作分发与应用启动钩子
├── schemas.py                      时间线方案与阶段写入的校验模型
├── service.py                      方案、入选素材、队列、进度、预览、代理图与清理
├── render.py                       FFmpeg 时间线引擎（探测、标准化、转场、叠加、混音、校验）
├── INSTALL.md                      FFmpeg、字幕模型与 ComfyUI 节点安装说明
├── licenses/                       FFmpeg 第三方依赖与许可提示
├── tests/                          真实 FFmpeg 回归
└── ui/                             时间线页面（FilmStudio.vue + Timeline.vue + plan.js）与素材扩展
```

## 时间线模型

方案文档为 `timeline_version: 2`，五条轨：

| 轨道 | 字段 | 定位方式 |
| --- | --- | --- |
| 主轨 | `clips[]` | 数组顺序即时间顺序；`kind=blank` 为黑场片段 |
| 叠加轨 | `overlay_clips[]` | 绝对落点 `start` + 画幅内矩形 `rect{x,y,w,h,opacity}` |
| 音轨 | `audio_clips[]` | 绝对落点 `start`，与主轨原声和背景音乐混音 |
| 字幕轨 | `captions[]` | 自动识别或手动编辑的对白字幕，底部居中显示 |
| 文字轨 | `texts[]` | 普通文字图层，带 `start/end/x/y/font_size/color`，可在监看画面拖动 |

每个片段可带 `volume`（0–100）、`fade_in`/`fade_out`（秒，两者之和不大于片段时长）、
`original`（是否保留原声）。主轨片段上的 `transition{type,duration}` 与**下一段**做交叉
转场（`fade`/`wipeleft`/`wiperight`/`slideup`/`slidedown`/`circleopen`），转场会吃掉两侧
素材，因此成片总时长等于各段之和减去所有转场时长。转场时长不得超过相邻两段各自的时长。

旧文档（只有 `clips`、没有新字段）无需迁移：缺省即 `kind=clip`、`volume=100`、无淡入淡出、
无转场，行为与升级前一致。

## 合成流程

`film.render`（正式）与 `film.preview`（低画质快速预览）走同一条流水线：

1. **素材检查**：用系统 FFprobe 读取时长、视频轨、音频轨。没有视频轨、时长读不出、
   裁剪起点已达素材末尾或裁剪终点超过实际时长的方案直接拒绝，且在排队前就返回错误。
2. **逐段标准化**：按 `in`/`out` 裁剪，统一画幅与帧率；`fit=contain` 完整显示并补黑边，
   `fit=cover` 放大后居中裁切；逐段应用 `volume` 与 `fade_in`/`fade_out`。黑场片段用
   `color` + `anullsrc` 生成。所有片段统一为 H.264/yuv420p、AAC 48kHz 立体声。
   标准化结果按内容指纹缓存，改一处只重算一段。
3. **拼接主轨**：无转场时用 concat 解复用器无损拼接；有转场时用单遍 `xfade` +
   `acrossfade` 图，`offset` 一律取**实测**片段时长累加，避免 concat 的毫秒级漂移。
4. **叠加轨**：`scale`+`pad` 到 `rect` 尺寸（自动取偶数，yuv420p 要求），`overlay` 按
   实测时间轴落点合成，`opacity` 走 alpha 通道。
5. **音频混合**：额外音轨用 `adelay` 定位到 `start`，与主轨原声、背景音乐一次
   `amix=normalize=0` 混音，背景音乐按 `volume` 缩放并截断到成片时长。
6. **发布与校验**：先写 `final.partial.seg`，`-movflags +faststart` 重封装，再用 FFprobe
   校验输出含视频轨与音频轨、总时长与画幅符合方案，校验通过才改名为 `final.mp4`
   并写入合成历史。预览输出 `preview.mp4`，不进入合成历史、不影响正式成片。
7. **运行保障**：同插件串行队列（`semaphore`）、进度百分比、`render.log` 日志、
   可真正终止的取消任务、网关关闭恢复、失败时清理媒体与中间文件并保留 `plan.json` 与日志。
   预览和正式导出互斥并使用提交时的方案快照；每部成片保留最近 20 个正式导出版本，
   新预览成功后自动清理旧预览目录。

所有外部程序都以参数数组启动，不拼接 shell 命令；进程被取消或超时时会被终止。

## 动作

| 动作 | 用途 |
| --- | --- |
| `film.list` / `film.get` / `film.sources` / `film.assets` | 查询成片、方案、入选素材与插件导入素材 |
| `film.save` | 创建或部分更新时间线方案（省略字段保留原值）；可传 `expected_revision` 防止并发覆盖 |
| `film.add-clip` | 把一条入选视频追加到主轨末尾 |
| `film.select-source` | 标记/撤回入选视频 |
| `film.import-asset` / `film.delete-asset` | 导入素材；删除未被方案引用的插件导入素材 |
| `film.progress` | 填写人工阶段进度（剪辑合成阶段由系统维护） |
| `film.render` | 提交正式合成，结果在 `render.url` |
| `film.preview` | 提交 480p/15fps 快速预览，结果在 `preview.url` |
| `film.validate` / `film.cancel` | 预检方案；取消排队或正在执行的预览/正式导出 |
| `film.proxies` | 生成时间线缩略图条与波形图，返回 data URL 与素材时长 |
| `film.transcribe` | 一键识别整条时间线中的视频原声和独立音频轨 |
| `film.delete` | 删除成片与其合成输出 |

## FFmpeg 运行依赖

- 插件通过系统 `PATH` 查找 `ffmpeg` 和 `ffprobe`，不提交或自动下载二进制。
- 两个命令缺少任意一个都会在提交预览、导出、代理图或自动字幕前返回明确错误。
- 安装入口、各平台命令和验证步骤见 [INSTALL.md](INSTALL.md)；许可边界见
  [licenses/FFMPEG-NOTICE.md](licenses/FFMPEG-NOTICE.md)。

## 运行数据

插件文件一律写在 `runtime.directory(project_id)` 下（按插件 ID 隔离），不写入插件源码目录：

```text
data/projects/<项目>/.plugins/film-studio/
├── films/<film_id>/<render_id>/
│   ├── final.mp4        校验通过后发布的成片
│   ├── preview.mp4      预览成片（仅预览任务）
│   ├── plan.json        本次合成的方案快照
│   ├── render.log       FFmpeg 与 FFprobe 日志
│   └── segments/        逐段标准化产物，成功后清除
├── films/<film_id>/_cache/   标准化片段缓存（最多 40 段，按内容指纹复用）
├── imports/                  插件导入并托管的项目素材
└── _proxies/                 时间线缩略图与波形缓存
```

过程文件统一使用 `.seg`（仍是 MP4 容器）与 `.dat`（仍是 PNG）后缀，素材库按扩展名索引，
因此只有 `final.mp4` 与 `preview.mp4` 会出现在素材库里。

## 回归测试

```powershell
python -m unittest discover -s plugins/film-studio/tests -p 'test_*.py'
```

用系统 PATH 中的 FFmpeg 生成夹具并合成；未安装时真实渲染用例会跳过。测试覆盖混合规格、黑场、转场重叠与时长、叠加轨落点、
额外音轨延迟、逐段音量与淡入淡出、无音轨、原声开关、背景音乐循环与静音、contain/cover
画幅、预览降质、片段缓存复用、中文与空格路径、越界裁剪、损坏素材、无声素材、取消中断、
缺少内置程序、代理图缓存以及成功后的中间文件清理。

## 自动字幕

`film.transcribe` 提交后立即返回当前成片，并在后台由插件任务识别；通过 `film.get` 读取
`transcribe.status`（`queued`、`running`、`completed` 或 `failed`）。识别完成后，先由系统 FFmpeg 按最终时间线混合所有启用的视频原声和独立音频轨，
排除背景音乐，再通过 ComfyUI-Whisper 的 `LoadAudio`、`Apply Whisper` 与 rgthree 的
`Display Any` 输出节点一次识别，默认使用 `large-v3-turbo`。返回时间戳天然对应整条成片，
并替换方案的 `captions` 字段。字幕和普通文字在预览与正式导出时统一由系统 FFmpeg
烧录 ASS；产品不提供 SRT 导入、导出。ASR 适配、字幕模型和过程文件均不进入框架。

更新现有方案时可省略 `plan.name`；创建方案仍必须提供名称。中文默认传给 Whisper 的语言为 `zh`，插件使用 OpenCC 将繁体输出转换为简体。

## 当前范围

不含关键帧动画、变速、音频降噪与多机位同步；主轨仍是顺序轨（顺序即时间），
只有叠加轨与音轨使用绝对落点。
