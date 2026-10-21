# 前期制作与生产合同

先完成故事构思/研究、资产与分镜；前期审核和确定性校验通过前不生成媒体。故事可为虚构、历史、冒险、悬疑、战争、动作、打斗、科普等，不预设必须讲解或对话。资料型作品记录来源URL和不确定性；虚构故事明确标记虚构，不强制凑三条研究来源。

## 故事、场面与分镜

故事必须有清晰的主线、人物/主体目标、冲突、升级、转折和结局；表达形式由题材决定。纯动作故事可完全没有对白；需要时再加入角色对白、旁白或字幕，不把说明内容强行拆成角色问答。角色数量、阵营、能力、装备、关系和功能都按故事定义。

有对白/旁白时，保留原意稿和最终逐字稿；数字、单位、日期、专名按目标语音模型要求规范化。长台词按语义拆镜；时长上限来自能力发现，不能硬写8秒。口播估算只作规划，实际生成仍需听检。无台词故事以动作、表情、环境变化、构图和声音推动叙事。

一镜突出一个主要叙事动作，但可按需要同时呈现多个主体。对白镜才检查发言主体与口型；动作镜明确主体位置、运动方向、攻防意图、动作先后、碰撞/闪避结果、受伤/装备状态及镜头轴线。打斗要保证观众看懂谁对谁、动作因果与空间位置，不用连续无意义动作替代情节推进。

场景数量和功能由故事决定，不强制安排讲解场景。单场景故事要写明原因，并用景别、区域、光线和动作调度维持变化。跨镜出现、必须识别为同一主体或会影响连续性的角色/阵营/场景/关键道具在 `episode_assets` 建立资产；一次性背景元素不强制建多视角板。只有需固定角色音色时才写 `voice` 计划。

按故事节奏自然拆镜，再按同一场景组织四宫格。不为凑整改变事件因果；可以补有意义反应/过渡镜，标明padding。不同地点不能因拼格而共用错误场景图。分格后检查主体位置和动作方向；禁止直接把宫格作为单镜视频参考。

## production.json

文件格式和唯一归属见[定稿包](final-package.md)。production.json由preproduction.py生成，只保存索引和media_progress，不由智能体把完整文案写进去。YAML读取复用OpenMontage已有PyYAML依赖；所有技能命令使用安装了该依赖的同一个Python。

下面仅展示load_production从十文档**在内存中组装的校验结构**，用于理解校验字段；不是需要另存、手写或维护的第二份计划。所有项目文件路径相对run_root。示例字段按定稿包规则分别归档，实际项目不得留占位字符串：

```json
{
  "schema_version": 1,
  "revision": 1,
  "config": {
    "title": "片名",
    "project_id": "实际网关项目ID",
    "workspace_id": "story-独立运行ID",
    "aspect": "9:16",
    "duration_target_sec": 60,
    "max_attempts_per_shot": 3,
    "min_scenes": 1,
    "single_scene_reason": "",
    "allow_self_review": false,
    "refine": true,
    "subtitles": false
  },
  "research": {"kind": "factual", "sources": [{"url": "https://实际来源", "claim": "支持的事实"}], "uncertainties": []},
  "story_beats": [{"id": "beat_001", "purpose": "主角发现异常并决定追踪", "change": "从日常状态进入冲突"}],
  "episode_assets": [
    {"id": "protagonist", "kind": "character", "description": "主角外形、装备和需要连续的状态"},
    {"id": "pursuer", "kind": "character", "description": "追踪者外形和行动特征"},
    {"id": "scene_alley", "kind": "location", "description": "狭窄巷道及其空间结构"}
  ],
  "turns": [],
  "shots": [
    {
      "id": "shot_001", "story_beat_ids": ["beat_001"], "audio_mode": "h3_scene_audio", "duration": 6,
      "scene_id": "scene_alley", "scene_function": "pursuit", "shot_pattern": "tracking_wide",
      "visible_characters": ["protagonist", "pursuer"], "required_assets": [],
      "action_start": "主角发现追踪者逼近", "action_process": "主角沿巷道向画面右侧奔跑，追踪者从后方追近",
      "action_end": "主角拐入右侧出口，追踪者仍在后方",
      "camera": "机位与运动", "continuity_in": "承接上一镜", "continuity_out": "衔接下一镜",
      "prompt": {"reference_map": "分镜、主体和场景的实际编号映射", "execution": "完整动作执行描述，保持方向、空间和动作因果，不添加对白"}
    }
  ],
  "storyboard_groups": [{"id": "grid_001", "scene_id": "scene_alley", "panels": 4, "shot_ids": ["shot_001", "实际镜头2", "实际镜头3", "实际镜头4"]}],
  "preproduction_qa": {
    "schema_version": 1, "stage": "preproduction", "revision": 1,
    "reviewer": "独立审核标识", "review_mode": "independent", "status": "PASS",
    "shot_ids": ["完整镜头ID列表"],
    "checks": {"facts": "PASS", "narrative": "PASS", "assets": "PASS", "storyboard": "PASS"},
    "evidence": ["来源、故事节拍、主体设计和镜头动作的具体审核依据"], "issues": [], "limitations": []
  }
}
```

示例只说明内存结构，不是可运行的完整定稿包；实际还有从asset_prompts派生的资产prompts、从scene_plan派生的scene_design，以及storyboard_groups中逐镜storyboard_prompt。`story_beats`描述所有故事的主线；`turns`可为空，仅在有对白时填写。脚本检查ID、可选对白映射、资产/场景引用、图格覆盖、动作描述及QA版本。

`audio_mode=h3_dialogue`：角色对白并绑定turn/说话人；`h3_scene_audio`：无对白但保留H3生成的环境/动作声音，不附角色参考音频；`silent`：明确静音；`pre_recorded_narration`：使用预录旁白，另写 `narration_text`、`narration_audio`、`narration_duration`，时长按实际音频规划，合成时替换原声。

校验命令：

```text
python <skill_root>/scripts/validate.py plan <run_root>/production.json
```

脚本PASS只证明合同完整；来源真假、动作可行性、镜头好坏仍由前期QA判断。研究、详细文案与提示词必须在十文档定稿包中，不在production索引复制。

build 成功后主制片用 `guarded_mcp.py --operation progress --key plan` 推送九阶段进度计划，并用 `--operation archive --key script|storyboard|prompts|characters|scenes|final-package` 把定稿投影推入网关创作档案，让用户在UI可看可审；映射与重推规则见[网关生成与恢复](generation.md)。

错字、数字口播、单镜视觉弱化可局部修订并重做对应QA；事实、剧情、身份、场景结构变化必须重新审影响范围。递增revision，记录原稿、新稿、原因及影响镜头；旧QA不得给新版本放行。

## 实物证据闸门

只在production索引中追加 `media_progress`，不把load_production返回的内存结构写回索引，不创建第二套检查点系统。每阶段提交下一类生成前，运行累积闸门；它会检查前置产物，不允许先造视频再补资产。production.json必须放在run_root顶层。这些检查由主制片运行脚本，不要求子智能体重读所有历史。

```text
python <skill_root>/scripts/validate.py gate <run_root>/production.json --stage drafts
python <skill_root>/scripts/validate.py gate <run_root>/production.json --stage references
python <skill_root>/scripts/validate.py gate <run_root>/production.json --stage grids
python <skill_root>/scripts/validate.py gate <run_root>/production.json --stage storyboard
python <skill_root>/scripts/validate.py gate <run_root>/production.json --stage compiled --shot-id <实际镜头ID>
python <skill_root>/scripts/validate.py gate <run_root>/production.json --stage media
python <skill_root>/scripts/validate.py gate <run_root>/production.json --stage selected
python <skill_root>/scripts/validate.py gate <run_root>/production.json --stage final
```

`media_progress`包含以下字典，键为真实asset_id/group_id/shot_id：
- `drafts`：所有episode_assets的Qwen主体/场景草稿。
- `references`：所有episode_assets的Qwen定版角色板、多视角或场景图。
- `grids`：每个group的Qwen四宫格。
- `panels`：每个shot的切割单格。
- `compilations`：每镜真实compile请求、就绪回执及确认提交回执。
- `videos`：每镜从该转换会话确认生成的初稿及媒体QA，不被二采覆盖。
- `refinements`：按shot_id保存成功二采数组，每项含parent_job_id、parent_sha256、action_id，以及get_job实际返回的gateway_job。失败尝试只进台账。
- `selected`：每个shot_id对应一个已审核的初稿或二采job_id，合成不得自动挑最新文件。
- `composition`：保存film-studio方案与渲染回执：film_id、按计划顺序的sources（shot_id/job_id/audio_mode）、旁白audio_clips、bgm_job_id、validate/preview/render回执及output（library_path、run_root内path、sha256）；`final`保存终片path、sha256、qa、selection_sha256和compose_sha256。
- `voices`：按说话角色asset_id保存本期声音参考：path（run_root内音频）、sha256、revision、upload_id、spec_sha256（specification(plan, "voices", asset_id)）及听检QA（stage=voice，checks为intelligibility/identity/quality）。`generated` 由网关TTS按voice计划生成并记录job_id/capability_id；`provided` 记录用户文件复制路径。同一角色全片只用同一声音参考。

drafts/references/grids/panels/videos记录共有path（run_root内相对路径）、sha256、revision、job_id、capability_id、spec_sha256。drafts/references/grids和videos保存QA；panels为确定性切割结果，靠父网格SHA256、panel_index、文件SHA256及实际输入回执校验，不重复要求逐格语义QA。候选胜出记录还保存candidate_index、candidate_attempt。图像记录另有upload_id、request及gateway_inputs（get_job_inputs完整返回）；videos保存gateway_inputs和compiled_sha256（实际英文执行稿的fingerprint）。QA的input_sha256将path绑定到实测哈希；shot_ids在资产QA中使用asset_id，图格使用组内完整镜头ID，单格/视频使用对应shot_id。

revision是该产物实际审核版本，须为1到当前plan.revision；不得为“追上版本”修改旧报告。spec_sha256使用scripts/validate.py的specification(plan, section, key)，绑定当前相关资产设计/镜头/画幅，不包含全局revision。未改动资产可复用旧QA；改动及依赖源哈希变化只阻断相关下游。前期整体QA仍须对应当前plan.revision。

references另带parent_sha256指向草稿；grids的reference_sha256精确覆盖场景、全部可见角色和required_assets；panels带源grid的parent_sha256及从0开始的panel_index。切格按左上、右上、左下、右下映射，校验四个真实文件与有序输入回执；宫格的完整图像QA已覆盖语义与构图，不对确定性切割重复做四次相同审核。静音镜如包含角色出镜，shots.visible_characters显式列出资产ID。

角色板/主体多视角的request.settings.ratio固定16:9，其他图像及视频按项目画幅。四宫格prompt必须按shot_ids顺序嵌入该组四条有序storyboard_prompt静态图格描述（`image.qwen.storyboard_4`不消费settings.shots），不是视频源稿；所有请求明确project_id和idempotency_key，workspace_id只进本地索引binding与台账、不随网关请求发送，输入严格匹配锁定资产。gateway_inputs不能用request或手写哈希代替；旧任务没有来源回执则BLOCKED并补采证据，不捏造兼容记录。

compilations每条记录含`revision`、`request`（原始submit_generation参数）、`response`（保存get_collaboration返回awaiting_confirmation时的完整回执）以及确认后的`submission`。request显式compile、当前project_id、当前镜头源稿及真实inputs；图片依次为单格、当前speaker和listener定版角色板、scene_id、其余required_assets（场景去重），音频仅为speaker的voices声音参考。静音/旁白镜不传speaker和声音。response必须是MiniMax H3 quick转换会话，六段英文执行稿及逐字对白完整；needs_input不能放行。submission的collaboration_id和job_id必须关联该会话及videos记录。

确认默认逐稿取得用户批准：compilation.authorization记录approved_by=user、真实evidence和response_sha256=fingerprint(response)。若用户明确委托特定镜头的H3审核及确认，在plan.h3_delegation记录approved_by=user、真实evidence、allow_review_and_confirm=true、shot_specs={shot_id: specification(plan, 'compilations', shot_id)}。不得从笼统“全自动”推断此委托。先审核就绪稿，再按当前collaboration_id/revision确认，禁止确认时覆盖稿件。

成功refinements记录具有视频同等文件/QA/spec字段，gateway_job.id、status=completed及parent_job_id必须与记录匹配。父文件哈希对应真实上级，每条成功二采复审。selected覆盖全部镜头；终片QA绑定实际文件，并以selection_hash(plan)和fingerprint(composition证据)记录selection_sha256/compose_sha256。

这些校验不能证明恶意伪造的回执真实，也不能物理阻止智能体绕开脚本调用通用MCP。宿主须落实工具白名单，主制片只经guarded_mcp提交。OpenMontage assets/edit完成检查点执行selected闸门，compose/publish执行final闸门，必须携带--production。不能用空manifest或未复审二采推进。
