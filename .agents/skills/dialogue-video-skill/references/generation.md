# 网关生成、二采与断点恢复

## 唯一调用者

主制片调用当前MCP，不使用旧 `zizai_video`、`zizai_job` 等专用参数。工具schema以实时tools/list为准。查询、上传和下载可直接调用MCP；本技能的生成、续答和确认必须经过guarded_mcp提交校验，不使用REST或直接MCP提交绕开它。

1. `get_health` -> `list_capabilities` -> `get_capability`，发现图像、视频、分格、配乐和后处理能力。
2. `create_project` 返回project_id但不切换项目。`submit_generation` 每次明确携带project_id；主制片为语音专用工具先 `set_current_project`，使用相同独立workspace_id。
3. `upload_reference(filename, data_base64, media_type)` 上传实际文件，取得upload_id；保持图像与音频各自的输入顺序，按能力给role。
4. `submit_generation` 提交能力ID、prompt、inputs、settings、project_id、workspace_id和幂等键。
5. 返回job_id后 `get_job`/`wait_job`；完成后 `get_job_artifacts` 下载全部产物，用 `get_job_inputs(job_id)` 保存真实输入回执。实际upload_id和sha256必须与锁定参考一致，不能用请求副本冒充回执。
6. `get_job_actions` 查已完成视频支持的后处理，按实际返回action_id调用 `run_job_action`，保存新任务ID，再等结果与复审。

输入格式为 `{"type":"image","upload_id":"返回ID","role":"能力支持的角色"}`，不是本机路径或旧data_url。分辨率、variant、时长来自能力发现；不把草稿分辨率标成最终高清。

## 提示词与确认

图像提交显式选择Qwen能力；H3视频一律 `prompt_processing=compile`，由网关按官方技能分析真实参考与描述词、纠错并转换。direct仅用于图像等不需H3转换的能力，不用于本技能的视频。不能把简单翻译或自行写六段稿冒充转换。

返回session时保存会话ID，不当作生成任务。`needs_input`通过guarded_mcp的continue续答原session。get_collaboration返回规范model_id、collaboration_mode、confirmation和revision，同时保留result兼容字段。前期明确记录本定稿镜头H3审核与确认的委托后，生产者核对实际转换稿并确认，无须每镜再问；真实歧义或超出定稿仍停止。没有这种委托时，`awaiting_confirmation`展示双语稿等待用户批准。不能把全自动制作的一般授权当作审核委托。

保存完整转换请求、就绪回执、用户批准或有范围的委托证据及确认回执。修改镜头后旧委托失效，须重新授权；禁止direct避开转换。

H3执行稿使用subject_definitions、summary、retention_analysis、detailed_description、overall_soundscape、non_diegetic_music结构：身份锚定实际参考编号，保留动作时序、镜头、对白和声音映射。只删重复身份外观描写，不压缩剧情。当前speaker的参考音频必须正确；对白逐字来自normalized_line。图片顺序：分镜单格、speaker角色板、listener角色板、场景及其他主体；超过能力数量时调整构图/拆镜，不静默丢参考。

## 资产、图格与声音

先验证固定主持人哈希，再逐项完成本期主体设计。出现两镜以上或必须识别为同一个的角色、动物、物品、交通工具、建筑和环境均建资产；前期QA检查是否遗漏。固定主持人直接使用随包身份和声音，不重生。

所有新图都用Qwen Image 2.1，严格顺序：
1. `image.qwen.text_to_image`生成每个主体/场景草稿，图像QA通过后运行drafts闸门。
2. 将草稿作为真实输入，人物、动物、物品用`image.qwen.character`生成角色板/多视角；环境用`image.qwen.scene`生成场景参考。QA通过后定版，运行references闸门。物品不能因不是人物而省略多视角。
   角色板/主体多视角一律显式传 `settings.ratio="16:9"`，不随项目9:16等画幅改变；这是身份参考的排版比例，不是视频比例。记录实际提交settings供闸门检查。场景、分镜和视频沿用项目画幅，固定主持人旧资产不裁切、不重生。
3. 主制片读取已审storyboard_groups.yaml里的构图、动作、视线、机位及连续性，绑定定版图实际上传ID；不重新派分镜子智能体策划。四宫格实际输入顺序为场景、按镜头顺序收集的全部可见主持人角色板和required_assets，重复去除。`settings.shots`为四条有序storyboard_prompt，不使用video_prompts里的视频执行稿；超过8张参考须前期重排分组，禁止少传。生成并审核后运行grids闸门，再切格。
4. `image.split`切割四个单格，按左上、右上、左下、右下映射shot_id；独立图像QA检查所有单格，上传实际单格，运行storyboard闸门。未经此闸门，不提交任何H3任务。
5. 每镜提交compile，解决needs_input；保存就绪回执，运行compiled闸门后才按授权确认。返回job_id后保存输入回执、下载、视频QA；通过media后可二采，选定版本并通过selected才进入剪辑。

闸门的证据字段与命令见[生产合同](preproduction.md)。任一步失败，只回退受影响产物，并使受影响下游证据失效。草稿、定版图、四宫格、单格都必须下载保存；不得用资产ID、文字计划或捏造PASS替代文件。

四宫格使用能力实际支持的shots字段，检查实际格数与切割顺序。能力缺失则BLOCKED。分格尺寸要实测，禁止把低分辨率面板本地放大后声称原生高清。

背景音乐发现 `music.ace_step.background`，歌词为空，按故事写器乐配乐简报，节奏拍号用schema支持的值（如"4"而不是"4/4"）。不把唱歌模型当器乐配乐默认方案。

旁白可用speech_preset（先查ready）、speech_describe或speech_clone（先上传声音）。speed为0.5–2.0，中文约4–5字/秒仅可粗估；参考音频不超过30秒，优先3–10秒。主持人H3音频参考使用固定文件，不替换为另一个预设。

## 二采政策

常规草稿优先发现可用480P预览模式，通过QA后按config.refine决定是否二采。**长镜允许二采，不设8秒禁令，不硬编码15秒上限。** 需要源latent的H3操作以get_job_actions实际可用性为准；缺latent报告具体原因，不能改用其他放大器冒充H3二采。

同一镜头可继续二采，记录完整父子任务链；不要无限循环，遵守用户授权的二采次数和预算。LTX2.5仅在能力可用且制作计划批准时使用；先确认声音保留策略。所有二采产物重新检查台词、音色、动作和音轨，丢对白不能放行。

成功二采记录进refinements，保留get_job的completed父子回执及文件哈希和复审；失败尝试只留台账。不覆盖videos初稿。selected明确记录每镜最终选用的job_id；即使不二采也必须选中审核过的初稿。

## 校验后的MCP提交

```text
python <skill_root>/scripts/guarded_mcp.py --production <run_root>/production.json --endpoint <gateway_origin>/mcp --operation grids --key <group_id>
```

operation支持drafts、references、grids、panels、compilations、continue、confirm；key是资产、图格或镜头ID。普通生成无需inputs文件：脚本从定稿和真实上传记录组装prompt、四格描述、参考顺序、画幅/时长、项目和稳定幂等键。config.generation_settings按operation保存前期批准的分辨率、variant、seed等参数；不在生成阶段自行换模型参数。重抽用--attempt递增，断线恢复保持原attempt，不能超出授权上限。

continue/confirm必须带--inputs，保存实际会话问题答复或确认参数。也可为普通生成传真实request.json，但仍校验定稿描述和参考绑定。脚本检查前置文件/QA后提交，并追加jobs.jsonl的intent和回执，主制片从台账收录request，不重新抄描述词。同键同请求恢复原回执，同键不同请求拒绝；缺回执时复用原幂等键查询/重试，不能新建重复转换。编译幂等在网关持久化且按workspace隔离。panels操作按网格只提交一次切割，四个shot记录同一请求、同一job回执及各自panel_index；不要四次重复切割。

当前run_job_action只接受job_id/action_id，不能额外塞width、height或target参数；目标尺寸由公布的动作定义决定。没有合适尺寸动作时报告限制，不承诺当前MCP不能做到的自定义尺寸。

## 台账与恢复

主制片在run_root维护 `jobs.jsonl`（逐事件追加），每项记录：event_id、时间、revision、shot_id/asset_id、operation、project_id、workspace_id、idempotency_key、输入upload_id与角色映射、实际settings、job_id/session_id、parent_job_id、attempt、status、产物URL/路径/SHA256、QA文件。交给AI时只传对应阶段卡和当前事件摘要；完整回执留在台账，不回灌主会话。

提交前先写intent与幂等键；得到ID立刻写submitted，不等整片结束才记录。每个镜头的生成、二采、下载、QA分开记事件。无需把原始Base64或巨大工具返回存进模型上下文。

恢复时读取台账与阶段摘要：

- 已有job_id先查原任务；queued/running继续等待，不重新提交。
- 不明确提交是否成功：对支持幂等键的submit_generation复用原键；无幂等保证的后处理先检查原任务/子任务，无法确认则BLOCKED，不盲目重发。
- 单次wait最多120秒；超时只是本次等待结束，不取消、不认定失败、不另起二采。
- 429节流后重试同一逻辑请求，不立即轰炸队列；默认最多同时有2个在途本地任务，按实际队列收敛。
- failed保留error_info并诊断；缺模型/节点、OOM不机械重复三次。
- 每镜草稿最多config.max_attempts_per_shot次，合格镜头不因其他镜头失败而重做。

下载相对URL以网关origin拼接，不用客户端localhost。临时文件下载完原子改名，校验非空、SHA256和ffprobe；同一路径已有不同内容时保留版本，不覆盖。产物已完成但下载失败时重试下载，不重新生成。不能把网关服务器路径传给远程QA当本地路径。

阶段摘要只含决策、项目ID、下一步、阻断和文件路径，子智能体每次新会话，只读取当前阶段材料。
