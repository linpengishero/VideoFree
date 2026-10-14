# OpenMontage 接入与恢复

独立安装 `openmontage` 和 `dialogue-video-skill`，无须旧 dialogue-man。完整源码、LICENSE、版权/来源文件必须随 OpenMontage 分发；本项目集成增量记录于其 `docs/dialogue-video-integration.md`，不宣称上游官方版本。先读其 AGENT_GUIDE.md 和 PROJECT_CONTEXT.md。

解析 `openmontage_root` 为实际安装目录，不硬编码本机路径。`projects_root` 是技能目录外的本次工作目录；网关 project_id 与本地生产ID分别记录，不假设二者自动互通。所有生成任务仍明确传网关 project_id/workspace_id。

## 原生状态桥

下面 `<bridge>` 指 `<skill_root>/scripts/openmontage_bridge.py`。每次调用都带三个全局参数：

```text
python <bridge> --openmontage-root <openmontage_root> --projects-root <run_root>/projects --project-id <local_id> preflight
python <bridge> --openmontage-root <openmontage_root> --projects-root <run_root>/projects --project-id <local_id> init --title <title>
python <bridge> --openmontage-root <openmontage_root> --projects-root <run_root>/projects --project-id <local_id> next
```

桥直接调用 `lib.pipeline_loader`、`lib.checkpoint`、`schemas.artifacts` 和原生工具注册表，不提供第二套状态系统。缺失依赖时报错，不自动安装或启动看板。项目ID仅字母、数字、下划线和短横线。一个ID不能切换管线。

阶段顺序严格为 research → proposal → script → scene_plan → assets → edit → compose → publish。逐阶段读 `skills/pipelines/dialogue-video/director.md`，按 `schemas/artifacts/<name>.schema.json` 准备产物：research_brief、proposal_packet/decision_log、script、scene_plan、asset_manifest、edit_decisions、render_report、publish_log。文件内容不能杜撰来源或研究证据，虚构内容明确标注；schema要求不能诚实满足时暂停，不用假事实填空。

前期从内容定稿到制作定稿再到完整审核，十文档全部通过前不得进入assets媒体生成。原生script/scene_plan等规范产物是定稿文件的格式投影，不是独立维护的另一套剧本。production.json仅是自动索引和执行记录，桥在媒体操作前读取真实定稿并核验哈希。

产物集合文件是 `{ "artifact_name": { ...原始schema内容... } }`，不是路径列表或production.json。写检查点：

```text
python <bridge> --openmontage-root <root> --projects-root <projects> --project-id <id> checkpoint --stage script --status in_progress --artifacts <artifacts.json>
python <bridge> --openmontage-root <root> --projects-root <projects> --project-id <id> checkpoint --stage script --status completed --artifacts <artifacts.json>
```

未获得自动推进授权时用--require-approval和awaiting_human；--approved必须有真实用户批准。H3确认是另一个边界，默认人工批准，仅明确记录的特定镜头审核及确认委托可例外，不允许通用自动确认。

assets内部按Qwen草稿、定版图、四宫格、切割、H3 compile、视频QA执行。二采复审并选中后运行selected。完成assets/edit检查点自动检查selected，compose/publish检查final，均追加--production。修改上游只重做受影响内容；未变化资产可通过spec哈希复用，不修改旧QA版本假称复审。

修改上游阶段前，按管线顺序把该阶段及所有已有下游检查点通过原生API写回 `in_progress`（使用各自当前产物集合），随后重做和复审。原生历史归档保留旧记录；完成前读取 next，禁止跳过未完成前置阶段。jobs.jsonl保存网关任务ID用于恢复，不重复提交。

## 原生媒体工具

```text
python <bridge> --openmontage-root <root> --projects-root <projects> --project-id <id> tool audio_mixer --inputs <absolute-mix-inputs.json>
python <bridge> --openmontage-root <root> --projects-root <projects> --project-id <id> tool video_compose --inputs <absolute-render-inputs.json> --production <run_root>/production.json
```

工具输入遵守原生 `input_schema`，读取源码/用法说明，而非自造 compose.json。render至少带 operation=render、output_path、edit_decisions、asset_manifest、proposal_packet。所有本地媒体和输出路径用绝对路径；输出已有则换版本名，不覆盖。桥仅注册上述本地原生工具，不导入全量供应商适配器，不启动新生成通路。success=false或进程非零即失败，不能把技术自检当独立QA。

需要其他原生分析工具时按 OpenMontage 的注册表、能力检查和授权流程使用，不重新实现；生成端始终由主制片独占 videofree。Remotion/HyperFrames依赖缺失则报告，不能偷偷改运行时。
