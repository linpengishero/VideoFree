# 原生合成与交付

所有剪辑、混音、拼接、动画和渲染都使用独立安装的 OpenMontage 原生工具，不自行实现 FFmpeg 合成脚本。仅合成当前版本媒体QA通过的镜头，每次二采必须复审。技术检测不能替代听检和视觉QA。

## 剪辑与运行时

1. 阅读 OpenMontage `skills/pipelines/explainer/compose-director.md` 的运行时、混音及最终审核部分，以及工具声明的 `usage_location` 和 `agent_skills`。其中重新生成TTS或字幕的建议不能覆盖本技能固定声音、不烧字幕的约定。
2. 在 proposal 确定 `production_plan.render_runtime` 和 `renderer_family`，edit 阶段保存同一运行时及创作类型（双主持人可选 presenter，按原schema确认）：FFmpeg用于实拍视频剪辑；Remotion/HyperFrames按实际图形需求和授权选择。都由原生 `video_compose` 分发，不静默回退。
3. 按原始 schema 创建 `asset_manifest` 和 `edit_decisions`，不要把 `production.json` 冒充规范产物。真实本地路径使用绝对路径；cuts记录顺序、入出点、速度和转场。不能按估算口播时长截掉对白。
4. 显式设置 `edit_decisions.metadata.compose_target` 的 width、height、fit，以及工具的fps（按工具实际schema），保持批准的原生尺寸，不用输出平台预设偷偷放大480P。默认禁用字幕：`options.subtitle_burn=false`，规范产物中字幕同样禁用。

## 声音处理

- H3对白镜保留原始对白音轨。先确认确有音轨且台词完整，缺失则BLOCKED；原生工具给静音片补静音不能当对白通过。
- 旁白镜使用已审核的预录音，不再次生成主持人声音。先校验实际时长，长于镜头就调整经批准的剪辑，不截断台词。
- 使用原生 `audio_mixer` 的 extract、mix/full_mix、duck等实际支持的操作，按剪辑时间线安排对白、旁白、BGM和音效。阅读工具 `input_schema`，记录音量、起始时间和混音长度。
- 给 `video_compose.audio_path` 的必须是包含完整对白/旁白的最终混音，而非单独BGM；它会替换输出音轨。没有混音需求就不传此参数，让原生剪辑保留片源声音。
- 实测响度、峰值和终片同步，不能仅凭normalize选项声称听感通过。

## 执行与闸门

使用 [接入桥](openmontage.md) 的 `tool video_compose --production <run_root>/production.json`，输入operation=render、完整edit_decisions、asset_manifest、proposal_packet、新版本绝对output_path。cuts.id为shot_id且顺序与计划一致，source引用的路径和哈希必须对应selected选中视频。混音使用tool audio_mixer；如传audio_path，media_progress.mix必须有完整镜头集的final声音QA及文件哈希。桥只调用原生工具，不实现媒体算法。

运行合成前必须selected闸门PASS，保存真实compose.inputs。渲染后记录final的selection_sha256和compose_sha256，独立审核最终文件再运行final闸门；assets/edit完成检查点使用selected，compose/publish使用final，均携带--production。

检查 `success`、`error`、`data.final_review` 和实际文件，不将失败残留文件当成成片。原生自检不是独立QA。最终报告必须包括实际尺寸、时长、音轨、文件哈希及独立听检/视觉审核证据。

```text
python <skill_root>/scripts/validate.py qa <run_root>/qa/final.json --stage final --revision <当前版本> --shots <完整镜头ID，空格分隔>
```

QA通过后才提交render_report，它的outputs只能包含已审核终片。publish_log.metadata.source_sha256绑定终片哈希，成功本地export_path指向同一终片；失败或pending条目不能算完成。额外导出版本须另行审核。未经批准不外发平台。上游改动先使下游检查点失效，旧PASS不得放行新文件。

交付成片、高清镜头、固定及本期资产、BGM、十文件定稿包、production.json索引、规范阶段产物、原生检查点与历史、原生工具输入/结果、jobs.jsonl、修改记录和QA报告。所有路径来自本次真实运行；缺失能力明确BLOCKED，不编造通过结果。
