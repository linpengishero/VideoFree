# film-studio 合成与交付

剪辑、混音、拼接和渲染统一使用 videofree 网关的 film-studio 插件动作（`run_plugin_action`），不自行实现 FFmpeg 合成脚本，也不使用 OpenMontage 的 video_compose/audio_mixer。OpenMontage 只承载阶段状态、检查点与规范产物。仅合成当前版本媒体QA通过的镜头，每次二采必须复审。技术检测不能替代听检和视觉QA。

## 能力与诚实缺口

先 `list_plugin_actions` 确认 film.save、film.add-clip、film.validate、film.preview、film.render、film.get 可用（automation:true）。film.select-source、film.delete 等为 UI-only，自动化不得依赖。缺口如实记录，缺能力即 BLOCKED，不冒充：

- 无自动ducking：BGM只有全局 `volume` 与分段 `volume`/fade。需要压低BGM让对白时，把BGM拆成多个 `audio_clips` 手工做音量包络，或接受固定低音量；不得声称有原生duck。
- 无 Remotion/HyperFrames 动效：只有 overlay、texts、captions。需要动态图形时如实停止或去掉该需求。
- 输出规格是枚举：width/height 取 720/1080/1280/1440/1920，fps 取 24/25/30/60，fit 取 contain/cover。9:16 用 1080x1920。镜头原生尺寸不在枚举时按批准尺寸 contain/cover，不假装原生输出。
- 每个 film 的重渲染覆盖 `films/final.mp4`：每次 render 完成后立即下载到 run_root 换版本名并加哈希，闸门只认已下载审核的文件。

## 时间线计划

前置：selected 闸门 PASS；旁白镜的预录 TTS 任务和 BGM 任务已生成、QA 并有 job_id。

1. `film.save`（project_id、name）创建方案，保存返回 film_id。
2. 按计划镜头顺序逐个 `film.add-clip`（job_id=该镜 selected 任务），自动入选并追加主轨。
3. `film.get` 读取当前 revision，再 `film.save`（film_id、expected_revision、完整计划）：
   - `clips` 按 shot 顺序，`in/out` 入出点；对白与 `h3_scene_audio` 镜头 `volume=100` 保留H3原始声音，旁白/静音镜 `volume=0`；转场与 `fade_in/out` 按定稿制作计划。
   - `audio_clips`：每个旁白镜挂已审核 TTS job_id 与绝对 `start`，先校验实际音频时长，长于镜头就调整经批准的剪辑，不截断台词。
   - `bgm_job_id` + BGM `volume`（默认18）；需要包络时拆 `audio_clips`。
   - `width/height/fps/fit` 按批准输出规格；默认不烧字幕：`captions`、`texts` 留空，`film.transcribe` 不使用，除非用户明确要字幕。
4. `film.validate` 校验计划，错误修复后重跑；回执记入 composition.validate。

## 预览、渲染与下载

1. `film.preview` 提交低画质预览，`film.get` 轮询 preview.status/progress；完成后下载 preview.url 到 run_root 加哈希。主制片与独立QA审预览：故事顺序、动作连续、对白/旁白（如有）、环境声与BGM响度、字幕策略、尺寸时长。
2. 预览通过后才 `film.render`（除非用户已明确委托预览级审核，成片审核仍不可省）。`film.get` 轮询 render.status/progress；completed 后 `render.url` 指向库内 `films/final.mp4`，立即下载原子改名、实测非空、SHA256 和 ffprobe。渲染失败残留不算成片。
3. 实测响度、峰值和终片同步靠听检与抽帧，不能仅凭参数声称听感通过。对白镜须确认台词完整；动作/环境声按设计核对；无声镜确认未意外带入声音。

## 证据与闸门

`media_progress.composition` 记录：`film_id`；`sources`（按计划顺序每镜 `{shot_id, job_id, audio_mode}`，job_id 必须等于 selected）；`audio_clips`（每旁白镜 `{shot_id, job_id, start}`）；`bgm_job_id`；`validate/preview/render` 回执（含 film_id、status=completed；preview 回执带下载 path/sha256，render 回执带网关 url）；`output`（library_path、run_root 内 path、sha256）。`media_progress.final` 记录终片 path、sha256、qa、selection_sha256 和 compose_sha256=fingerprint(composition)。

```text
python <skill_root>/scripts/validate.py gate <run_root>/production.json --stage final
python <skill_root>/scripts/validate.py qa <run_root>/qa/final.json --stage final --revision <当前版本> --shots <完整镜头ID，空格分隔>
```

final 闸门确定性检查：sources 覆盖全部镜头且等于 selected、旁白 audio_clips 绑定 TTS job、三段回执完整、下载文件哈希一致。独立审核（看片+听检）通过后才写 final QA。assets/edit 完成检查点使用 selected，compose/publish 使用 final，均携带 --production。final QA 写完后运行 `guarded_mcp.py --operation progress --key final` 同步网关进度，并用 `--operation archive --key continuity` 推送真实交接记录（已完成范围、阻断、下一步）；selected 阶段同样同步 `progress --key selected` 与 continuity。

规范产物仍按 OpenMontage 原 schema 投影：edit_decisions 投影时间线计划（cuts 顺序、入出点、转场），render_report 的 outputs 只含已审核终片，publish_log.metadata.source_sha256 绑定终片哈希，成功本地 export_path 指向同一终片；失败或 pending 条目不算完成。额外导出版本须另行审核。未经批准不外发平台。上游改动先使下游检查点失效，旧 PASS 不得放行新文件。

## 交付

交付成片、高清镜头、本期生成资产、BGM、十文件定稿包、production.json 索引、规范阶段产物、OpenMontage 检查点与历史、film 方案与渲染回执、jobs.jsonl、修改记录和 QA 报告。所有路径来自本次真实运行；缺失能力明确 BLOCKED，不编造通过结果。
