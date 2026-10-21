# 网关生成、二采与断点恢复

## 唯一调用者

主制片调用当前MCP，不使用旧 `zizai_video`、`zizai_job` 等专用参数。工具schema以实时tools/list为准。查询、上传和下载可直接调用MCP；本技能的生成、续答和确认必须经过guarded_mcp提交校验，不使用REST或直接MCP提交绕开它。网关开启访问令牌时，guarded_mcp读取环境变量 `VIDEOFREE_API_TOKEN` 作为 `x-api-token` 请求头；令牌由管理员单独配置给主制片。

1. `get_health` -> `list_capabilities` -> `get_capability`，发现图像、视频、分格、配乐、后处理和film-studio合成动作能力。
2. `create_project` 返回project_id但不切换项目。`submit_generation` 和 `run_plugin_action` 每次明确携带project_id。网关请求没有workspace_id参数；config.workspace_id只是本地运行标识，写入索引binding与台账用于隔离本次运行，不随请求发送。
3. `upload_reference(filename, data_base64, media_type)` 上传实际文件，取得upload_id；保持图像与音频各自的输入顺序，按能力给role。
4. `submit_generation` 提交能力ID、prompt、inputs、settings、project_id和幂等键。
5. 返回job_id后 `get_job`/`wait_job`；完成后 `get_job_artifacts` 下载全部产物，用 `get_job_inputs(job_id)` 保存真实输入回执。实际upload_id和sha256必须与锁定参考一致，不能用请求副本冒充回执。
6. `list_plugin_actions(scope="resource", source_job_id=任务ID)` 查已完成视频支持的后处理，按实际返回action_id调用 `run_plugin_action`，传 source_job_id、project_id、inputs，保存新任务ID，再等结果与复审。

输入格式为 `{"type":"image","upload_id":"返回ID","role":"能力支持的角色"}`，不是本机路径或旧data_url。分辨率、variant、时长来自能力发现；不把草稿分辨率标成最终高清。

## 提示词与确认

### 本项目一次性自动制作授权

首次开工时一次性确认本次项目的故事/成片目标、预算和重试/二采上限，并征得两项明确授权：

1. 主制片可以审核并确认本项目所有符合已批准定稿、参考输入和能力约束的H3 compile结果，随后自动提交视频生成；不需要每镜再次询问。
2. 媒体QA优先由独立审核代理完成。若宿主没有可用的独立审核代理，是否允许主制片执行视觉抽帧、音频听检和技术检查并如实标记`self_review`；若允许，同时将`config.allow_self_review=true`。

把用户原话、项目ID、定稿revision、预算/重试范围、是否允许self_review和授权时间写入`task_config.yaml`的`automation_authorization`。若授权H3审核确认，在build后、首个compile前，将同一授权写入`production.json`的`h3_delegation`：`approved_by: user`、`evidence`为用户授权原文及时间、`allow_review_and_confirm: true`，`shot_specs`为每个当前shot_id对应的`validate.py specification(plan, 'compilations', shot_id)`。这是网关守卫要求的精确逐镜规格绑定，不是逐镜索取授权。修改故事/定稿revision后重新确认并重建受影响的H3规格映射。不得把授权扩展到超预算、外部发布、改变故事方向或静默接受不符合定稿的转换稿。

获得授权后自动推进前期制作、批次生成、QA、H3转换与确认、视频生成、剪辑、渲染和本地导出。普通转换追问优先引用定稿续答；只有涉及未定义的实质创作决策、预算或授权范围时才回到用户。阶段失败按已批准重试上限局部恢复，不重复询问正常确认点。

图像提交显式选择Qwen能力；H3视频一律 `prompt_processing=compile`，由网关按官方技能分析真实参考与描述词、纠错并转换。direct仅用于图像等不需H3转换的能力，不用于本技能的视频。不能把简单翻译或自行写六段稿冒充转换。

返回session时保存会话ID，不当作生成任务。`needs_input`通过guarded_mcp的continue续答原session。get_collaboration返回规范model_id、collaboration_mode、confirmation和revision，同时保留result兼容字段。若本项目授权记录覆盖当前定稿revision，生产者核对实际转换稿并自动确认；否则`awaiting_confirmation`展示双语稿等待用户批准。真实歧义或超出定稿仍停止。不能略过compile或覆盖转换结果。

保存完整转换请求、就绪回执、项目级授权证据及确认回执。授权按当前定稿revision生效；修改故事/镜头后仅对受影响镜头重新审核并更新授权映射。禁止direct避开转换。

H3执行稿使用subject_definitions、summary、retention_analysis、detailed_description、overall_soundscape、non_diegetic_music结构：身份锚定实际参考编号，保留故事事件、动作因果、时序、空间关系、运镜及按需的对白/声音设计。不压缩或改写剧情。只有对白镜才绑定speaker声音参考及normalized_line；无对白镜不得凭空添加台词。图片顺序为分镜单格、需要保持身份的出镜主体、场景及关键道具；超过能力数量时调整构图/拆镜，不静默丢参考。

## 资产、图格与声音

先逐项完成本期主体设计。没有随包角色，角色与声音参考按本期故事生成。跨镜出现、必须识别为同一主体或会影响后续镜头连续性的角色、场景、动物和关键道具必须建资产并锁定；一次性背景元素和不需要身份连续性的普通道具不强制制作多视角资产板。前期QA仍检查连续性资产是否遗漏。

所有新图都用Qwen Image 2.1，严格顺序：
1. `image.qwen.text_to_image`为一个主体/场景一次提交2–4个独立候选；用`--candidates 2|3|4`，然后对整批做一次轻量QA（方向匹配、主体可用性），用`validate.py batch-qa`按文件SHA256生成各候选的标准QA记录。只将选中的PASS候选登记为`media_progress.drafts`并运行drafts闸门。不要先逐张审核再重新派发同一资产。
2. 将定版草稿作为真实输入；重要角色/动物/关键道具用`image.qwen.character`生成角色板/多视角，环境用`image.qwen.image_to_image`生成场景参考（网关已移除`image.qwen.scene`，不得提交）。可对一组资产各提交2–4个候选后集中做一轮完整图像QA；只登记胜出的、通过QA的单个参考并运行references闸门。无需跨镜保持身份的一次性物件不做多视角板。
   角色板/主体多视角一律显式传 `settings.ratio="16:9"`，不随项目9:16等画幅改变；这是身份参考的排版比例，不是视频比例。记录实际提交settings供闸门检查。场景、分镜和视频沿用项目画幅。
   声音参考与定版图同在references闸门前定版：每个说话角色按asset_manifest的voice计划处理——`generated` 用 run_plugin_action 的 speech_describe/speech_preset（先查ready）生成示例文本音频，`provided` 复制用户文件到run_root；下载后听检（intelligibility/identity/quality）通过才上传，收录 `media_progress.voices`。同一角色全片只用同一声音参考，不得混用他人音色或中途换预设。
3. 主制片读取已审storyboard_groups.yaml里的构图、动作、视线、机位及连续性，绑定定版图实际上传ID；不重新派分镜子智能体策划。四宫格实际输入顺序为场景、按镜头顺序收集的全部可见角色角色板和required_assets，重复去除。`image.qwen.storyboard_4`不消费`settings.shots`，四条有序storyboard_prompt必须由guarded_mcp按shot_ids顺序嵌入单一prompt（Panel 1至4对应左上、右上、左下、右下），不使用video_prompts里的视频执行稿；超过8张参考须前期重排分组，禁止少传。可一次提交2–4张四宫格候选，集中做一轮完整图像QA，选中一张后运行grids闸门，再切格。
4. `image.split`每个网格只切割一次，按左上、右上、左下、右下映射shot_id。切割是确定性操作，不对同一网格的四个子图重复做完整图像QA；校验四文件非空及哈希、父网格哈希、索引顺序、上传ID与实际输入回执，然后运行storyboard闸门。未经此闸门，不提交任何H3任务。
5. 每镜提交compile，解决needs_input；保存就绪回执，运行compiled闸门后才按授权确认。返回job_id后保存输入回执、下载、视频QA；通过media后可二采，选定版本并通过selected才进入剪辑。

闸门的证据字段与命令见[生产合同](preproduction.md)。任一步失败，只回退受影响产物，并使受影响下游证据失效。草稿、定版图、四宫格、单格都必须下载保存；不得用资产ID、文字计划或捏造PASS替代文件。

四宫格能力固定产出2x2四格，四条格描述必须按顺序写入prompt；生成后检查实际格数与切割顺序。能力缺失则BLOCKED。分格尺寸要实测，禁止把低分辨率面板本地放大后声称原生高清。

背景音乐发现 `music.ace_step.background`，歌词为空，按故事写器乐配乐简报，节奏拍号用schema支持的值（如"4"而不是"4/4"）。不把唱歌模型当器乐配乐默认方案。

旁白先发现插件动作，再用 run_plugin_action 调用 speech_preset（先查ready）、speech_describe或speech_clone（先上传声音），文本与speed等放inputs，显式传project_id。speed为0.5–2.0，中文约4–5字/秒仅可粗估；参考音频不超过30秒，优先3–10秒。角色H3音频参考使用该角色voices中的声音参考，不替换为其他预设或其他角色的音色。

## 二采政策

常规草稿优先发现可用480P预览模式，通过QA后按config.refine决定是否二采。**长镜允许二采，不设8秒禁令，不硬编码15秒上限。** 需要源latent的H3操作以list_plugin_actions带source_job_id的实际可用性为准；缺latent报告具体原因，不能改用其他放大器冒充H3二采。

同一镜头可继续二采，记录完整父子任务链；不要无限循环，遵守用户授权的二采次数和预算。LTX2.5仅在能力可用且制作计划批准时使用；先确认声音保留策略。所有二采产物重新检查故事信息、动作连续性及适用的对白/声音，关键情节丢失不能放行。

成功二采记录进refinements，保留get_job的completed父子回执及文件哈希和复审；失败尝试只留台账。不覆盖videos初稿。selected明确记录每镜最终选用的job_id；即使不二采也必须选中审核过的初稿。

## 校验后的MCP提交

```text
python <skill_root>/scripts/guarded_mcp.py --production <run_root>/production.json --endpoint <gateway_origin>/mcp --operation grids --key <group_id>
python <skill_root>/scripts/guarded_mcp.py --production <run_root>/production.json --endpoint <gateway_origin>/mcp --operation drafts --key <asset_id> --candidates 3
```

operation支持drafts、references、grids、panels、compilations、continue、confirm；key是资产、图格或镜头ID。普通生成无需inputs文件：脚本从定稿和真实上传记录组装prompt、四格描述、参考顺序、画幅/时长、项目和稳定幂等键。草稿、定版参考和四宫格可用`--candidates 2|3|4`一次提交多个候选；仅图像这三个operation支持。候选使用稳定且互异的seed及幂等键；同参数同批次重跑复用已提交回执，单个失败可重跑而不重复成功项。`--attempt`仍是批准范围内的失败重试次数，不是候选编号；不同attempt会换seed。网关仍决定本地任务排队与执行，并不保证GPU并行或更短的总推理时间；收益是把提交与QA往返合并。

批次QA由一份独立报告逐候选给出id、相对路径、SHA256、status、required checks、evidence与issues，再运行：

```text
python <skill_root>/scripts/validate.py batch-qa <batch-report.json> --root <run_root> --stage draft --revision <revision> --candidate <asset>-1=<relative-file-1> --candidate <asset>-2=<relative-file-2> --select <asset>-2=<asset>
```

输出的`qa_by_candidate`保留每个候选的审查结果，`selected_qa_by_artifact`可直接回填`media_progress`中正式资产/图格记录的胜出稿报告；同时记录该记录的`candidate_index`与`candidate_attempt`，使提交合同可复核。每份批审报告只对应一个资产或网格候选组；网格胜出报告通过`--shot-ids <shot1> <shot2> <shot3> <shot4>`绑定组内镜头。候选文件、路径、哈希必须完全匹配。只允许选中status=PASS且必需检查全通过的候选。draft只检查方向匹配与可用性；reference/grid仍用完整图像检查。视频每镜的叙事信息、身份、动作与连续性必须逐镜审核；对白/声音检查依据该镜实际设计执行，不能用代表镜头代替整片审核。

continue/confirm必须带--inputs，保存实际会话问题答复或确认参数。也可为普通生成传真实request.json，但仍校验定稿描述和参考绑定。脚本检查前置文件/QA后提交，并追加jobs.jsonl的intent和回执，主制片从台账收录request，不重新抄描述词。同键同请求恢复原回执，同键不同请求拒绝；缺回执时复用原幂等键查询/重试，不能新建重复转换。编译幂等在网关持久化且按项目隔离。panels操作按网格只提交一次切割，四个shot记录同一请求、同一job回执及各自panel_index；不要四次重复切割。

run_plugin_action 的 inputs 遵循动作 input_schema；H3二采按返回声明提供 inputs.width、inputs.height（必填）和可选 inputs.parameters，动作schema为additionalProperties:false，不得传upscaler等未声明字段。不能额外塞未公布参数，也不能省略必需尺寸。生成动作拿到job_id才等待；即时动作读取result，不当作任务。

## 项目进度与创作档案同步

`guarded_mcp.py --operation progress|archive` 经网关 `ai-project-progress` 与 `project-archive` 插件做项目管理，同样追加 jobs.jsonl 台账；项目须带AI创建标记（`create_project` 创建），插件缺失或校验失败时如实降级为仅本地台账。

- `--operation progress --key plan`：build 后执行一次。先get，九阶段（preproduction/drafts/references/grids/storyboard/compiled/media/selected/final）已存在则跳过，不重复覆盖状态。
- `--operation progress --key <stage>`：闸门判定后立即执行。脚本先跑该stage的 `validate_gate`（preproduction 由 load_production 已全量校验），PASS→completed，FAIL→blocked且note带前部错误。阶段开工用 `--inputs {"stage_id":…,"stage_name":…,"status":"running","note":…}` 显式推送。
- `--operation archive --key script|storyboard|prompts|characters|scenes|final-package`：build 后推送定稿投影——script为story_script.yaml原文；storyboard含逐镜描述、动作与selected状态；prompts含每资产draft/reference与每镜视频源稿；characters含主体/道具及按需存在的 `-voice` 声音计划条目；scenes含场景布局灯光；final-package含概要、十文档哈希与QA结论。status final，先get_document读revision再CAS保存；revision冲突须重读后重推，不硬改expected_revision。定稿revision变化后重推受影响文档。
- `--operation archive --key continuity`：media/selected/final 里程碑用 `--inputs` 提供真实 decisions/completed/blockers/next_action 四段文本，记录已完成范围、阻断与下一步；这是给后续会话和用户的交接稿，不代替本地台账。
- 档案内容里的 job 引用必须是本项目真实任务，网关会拒绝悬空 job_id；进度不代替闸门——UI显示completed前该stage的本地gate必须真实通过。

## 台账与恢复

主制片在run_root维护 `jobs.jsonl`（逐事件追加），每项记录：event_id、时间、revision、shot_id/asset_id、operation、project_id、workspace_id、idempotency_key、候选candidate_index、输入upload_id与角色映射、实际settings/seed、job_id/session_id、parent_job_id、attempt、status、产物URL/路径/SHA256、QA文件。交给AI时只传对应阶段卡和当前事件摘要；完整回执留在台账，不回灌主会话。

提交前先写intent与幂等键；得到ID立刻写submitted，不等整片结束才记录。每个镜头的生成、二采、下载、QA分开记事件。无需把原始Base64或巨大工具返回存进模型上下文。

恢复时读取台账与阶段摘要：

- 已有job_id先查原任务；queued/running继续等待，不重新提交。
- 不明确提交是否成功：对支持幂等键的submit_generation复用原键；无幂等保证的后处理先检查原任务/子任务，无法确认则BLOCKED，不盲目重发。
- 单次wait_job最多30秒（MCP硬上限）；需要更久就循环再次等待。超时只是本次等待结束，不取消、不认定失败、不另起二采。
- confirm返回“插件已更新，请新建会话并重新确认”类409时，旧转换会话作废：该镜头以新attempt、新幂等键重新compile，重新走审核与确认，不盲目重试旧collaboration_id。confirm对已提交会话返回reused:true和原job_id时，收录该回执进台账，不重复提交。
- 429节流后重试同一逻辑请求，不立即轰炸队列；默认最多同时有2个在途本地任务，按实际队列收敛。
- failed保留error_info并诊断；缺模型/节点、OOM不机械重复三次。
- 每个生成key最多config.max_attempts_per_shot个attempt；每个attempt最多4个图像候选。attempt与candidate分别记账，合格候选不因其他资产/镜头失败而重做。

下载相对URL以网关origin拼接，不用客户端localhost。临时文件下载完原子改名，校验非空、SHA256和ffprobe；同一路径已有不同内容时保留版本，不覆盖。产物已完成但下载失败时重试下载，不重新生成。不能把网关服务器路径传给远程QA当本地路径。

阶段摘要只含决策、项目ID、下一步、阻断和文件路径，子智能体每次新会话，只读取当前阶段材料。
