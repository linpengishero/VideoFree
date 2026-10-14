# 一套定稿包，三个部分

一个项目只有一套定稿包。前期把全部文案做好、完成审核，然后生成阶段只读取定稿执行。下面十文件放在run_root顶层，文件名固定；输出图像、视频、台账和QA放执行目录，不放技能目录。

| 部分 | 文件 | 唯一职责 |
| --- | --- | --- |
| 内容 | task_config.yaml | 目标、预算、画幅、时长、模型与授权边界 |
| 内容 | research_notes.md | 完整研究、来源和不确定性 |
| 内容 | dialogue_script.yaml | 完整对话与逐字口播稿 |
| 制作 | production_plan.md | 制作顺序、配乐、二采、合成与交付策略 |
| 制作 | asset_manifest.yaml | 跨镜主体身份、状态、固定主持人引用 |
| 制作 | scene_plan.yaml | 场景布局、气氛、镜头与资产使用关系 |
| 制作 | storyboard_groups.yaml | 逐镜视觉设计、四宫格顺序和每格图像描述 |
| 制作 | asset_prompts.md | Qwen草稿与定版角色板/场景图描述 |
| 制作 | video_prompts.yaml | 逐镜H3转换源稿、动作、运镜、对白和声音映射 |
| 审核 | preproduction_qa.md | 当前版本完整审核、问题关闭及来源文件哈希 |

固定主持人角色板与声音引用随包资产，不重新设计。所有本期跨镜主体先列清单、写完整草稿及定版描述；角色板固定16:9。前期写的是完整设计，不是先列标题后到生成阶段临时补稿。

## 数据格式与归属

YAML文件顶层为对象。Markdown保留完整可读正文，research_notes、asset_prompts、preproduction_qa各包含**唯一一个**yaml或json围栏作为可执行数据；production_plan是纯Markdown。正文是说明/证据，不另放一份与数据块冲突的执行稿。读取复用OpenMontage的PyYAML，JSON语法也是合法YAML。

下例是字段格式，不是完整项目；所有占位内容在定稿前填写真实值。常规镜头详细必填字段沿用[前期合同](preproduction.md)和[QA合同](subagents.md)。

### 内容部分

task_config.yaml：

```yaml
revision: 1
config:
  title: 实际片名
  project_id: 实际网关项目ID
  workspace_id: 本次独立工作区ID
  aspect: '9:16'
  duration_target_sec: 60
  max_attempts_per_shot: 3
  min_scenes: 3
  single_scene_reason: ''
  allow_self_review: false
  refine: true
  subtitles: false
  budget: 用户批准的预算
  visual_style: 用户指定的风格
  generation_settings:
    drafts: {resolution: '1K'}
    references: {resolution: '1K'}
    grids: {resolution: '1K'}
    compilations: {resolution: '480P', variant: quick_preview}
```

generation_settings按阶段保存前期确认的参数，字段和值必须以网关实时能力为准，上例不代替能力发现。程序按定稿自动填入画幅、四条图格描述、逐镜时长和全部实际参考输入；角色板画幅始终覆盖为16:9。改变这些生成设置须修订并重审，不临时覆盖定稿。

模型策略、授权、时长估算等可在config记录额外字段，但不能以“一口气做完”推导无限预算或用户没授权的对外发布。需要无人值守H3确认，在前期明确征求“审核并确认本定稿镜头的H3转换结果”的授权，并记录证据；不需要每镜再问一次。未授权默认等待批准，真实歧义必须停止。

research_notes.md：正文完整记录研究结论、来源、原文依据与不确定性；唯一数据块：

```yaml
research:
  kind: factual
  sources:
    - url: https://实际来源网址
      claim: 该来源支持的具体事实
  uncertainties: []
```

虚构故事用kind=fictional，不能捏造事实来源。资料型作品必须有真实来源，未解决的关键不确定性不能进入生成。

dialogue_script.yaml：

```yaml
turns:
  - id: turn_001
    speaker: host_young_man
    listener: host_robot
    function: ask
    line: 原意台词
    normalized_line: 最终逐字口播稿
    knowledge_delta: 本句引入的问题
    typo_checked: true
    speech_checked: true
```

全部turn必须对应镜头。说话人、听者、normalized_line以这里为准，由程序投影到内存镜头数据，分镜文件不重复维护这些字段。

### 制作部分

production_plan.md写清按什么顺序执行、Qwen/H3能力、参考使用、声音保留、配乐简报、预算/重试上限、二采策略及原生OpenMontage渲染运行时。这里不再复制逐字剧本或逐镜描述词。

asset_manifest.yaml：

```yaml
fixed_cast:
  - host_robot
  - host_young_man
episode_assets:
  - id: scene_lab
    kind: location
    description: 该环境的身份及不变项
  - id: prop_meter
    kind: object
    description: 跨镜仪器的身份及结构不变项
```

人物、动物、物品、建筑、车辆等只要跨镜需识别为同一个就必须列入。固定主持人不加入episode_assets重新生成。环境身份在这里定义，具体布局在scene_plan中，完整生成描述在asset_prompts中。

scene_plan.yaml：

```yaml
scenes:
  - id: scene_lab
    description: 场景设计及叙事功能
    layout: 人物、仪器与背景的空间关系
    lighting: 灯光及时间
    shot_ids: [shot_001, shot_002, shot_003, shot_004]
```

每个location资产恰好一个场景条目；场景设计进入相关资产/镜头规格校验，修改后不能复用不匹配的旧参考。

storyboard_groups.yaml包含shots及storyboard_groups：

```yaml
shots:
  - id: shot_001
    turn_id: turn_001
    audio_mode: h3_dialogue
    duration: 6
    scene_id: scene_lab
    scene_function: host_dialogue
    shot_pattern: over_shoulder
    required_assets: [prop_meter]
    listener_face_policy: rear_three_quarter
    listener_mouth: closed
    visual_dominance:
      primary: host_young_man
      secondary: host_robot
      lighting_priority: primary
    action_start: 动作起点
    action_process: 动作过程
    action_end: 动作终点
    camera: 机位及运动
    continuity_in: 承接上一镜
    continuity_out: 衔接下一镜
    storyboard_prompt: 该格静态画面描述，包含构图、姿态、视线及参考身份
storyboard_groups:
  - id: grid_001
    scene_id: scene_lab
    panels: 4
    shot_ids: [shot_001, shot_002, shot_003, shot_004]
```

所有镜头在分组中恰好出现一次，每组四镜同一场景。storyboard_prompt是Qwen静态分镜图描述，不是H3视频动作源稿；生成时settings.shots由程序按shot_ids顺序读取这四条。实际图片输入根据scene_id、出镜主持人和required_assets绑定，不能只把描述词传过去。

静音镜不填turn_id，若有固定主持人出镜显式visible_hosts；旁白镜用pre_recorded_narration及narration_text/narration_audio/narration_duration，按前期合同处理。

asset_prompts.md每项写完整设计说明，唯一数据块：

```yaml
prompts:
  - asset_id: prop_meter
    draft: 完整Qwen主体草稿描述
    reference: 完整Qwen定版多视角描述，锚定草稿参考图
  - asset_id: scene_lab
    draft: 完整Qwen场景草稿描述
    reference: 完整Qwen定版场景描述，锚定草稿参考图
```

每个episode_asset必须有draft/reference两条非空最终描述。草稿完成后只绑定真实图片，不另创外观；提交参数必须使用这里的原稿。

video_prompts.yaml：

```yaml
shots:
  - shot_id: shot_001
    reference_map: 图片1=分镜单格，图片2=说话人，图片3=听者，图片4=场景，图片5=仪器；音频1=说话人音色
    execution: 完整H3转换源稿，包含身份引用、动作时序、运镜、逐字台词和声音设计
```

镜头覆盖必须与shots完全一致。execution必须含该turn的normalized_line逐字台词；这次必要的重复是对模型的执行指令，不是第二份可独立修改的剧本。台词改变时需同步受影响视频源稿，由校验阻止不一致。

这里是H3转换**源稿**，不是伪造网关的转换结果。生成时仍必须compile；实际转换英文稿保存到执行记录。参考编号提前按固定顺序确定，生成后绑定upload_id，不让模型猜哪张图是谁。

### 审核部分

前期QA读取上述完整九文件，不只审摘要/索引。审核事实、台词、资产遗漏、分镜、图像/视频描述以及预算授权。完成审核后运行：

```text
python <skill_root>/scripts/preproduction.py hashes <run_root>
```

将输出的九文档真实哈希绑定到preproduction_qa.md唯一数据块：

```yaml
source_sha256:
  task_config.yaml: 实际SHA256
  research_notes.md: 实际SHA256
  dialogue_script.yaml: 实际SHA256
  production_plan.md: 实际SHA256
  asset_manifest.yaml: 实际SHA256
  scene_plan.yaml: 实际SHA256
  storyboard_groups.yaml: 实际SHA256
  asset_prompts.md: 实际SHA256
  video_prompts.yaml: 实际SHA256
qa:
  schema_version: 1
  stage: preproduction
  revision: 1
  reviewer: 实际独立审核会话标识
  review_mode: independent
  status: PASS
  shot_ids: [shot_001, shot_002, shot_003, shot_004]
  checks: {facts: PASS, speech: PASS, assets: PASS, storyboard: PASS}
  evidence: [实际审核依据与已修正问题]
  issues: []
  limitations: []
```

复制哈希不等于审核通过；仍须满足完整QA证据合同。需要自审降级时先获取用户同意。

## 自动索引与生成

```text
python <skill_root>/scripts/preproduction.py build <run_root>
python <skill_root>/scripts/validate.py plan <run_root>/production.json
```

build验证十文档和审核后，生成schema_version=2的production.json：revision、sources（文件路径/哈希）、binding（project/workspace）与media_progress；可记录有真实授权证据的h3_delegation。它不保存完整台词、资产描述或镜头源稿。不手写索引、不把load_production返回的展开结果写回去。

旧schema_version=1的大快照不是新版本的定稿包，明确停止并要求整理十文档；不默默假装兼容。原dialogue-man及其运行环境不受影响。

生成脚本每次读取并核对索引和实际文档，内部组装执行字段。主制片只更新实际上传、请求、回执、产物和QA等media_progress，不让文案子智能体手工填哈希/回执。OpenMontage原生规范产物从同一份定稿投影，不另写不同版本的剧本。

前期文档变更必须递增revision、复审影响范围并更新当前整体审核，再build；原执行记录保留，不重新生成未变化资产。原QA实际版本不改写，变更规格及依赖哈希自动阻断相关旧产物。

生成阶段只做定稿执行、文件绑定及产物检查。局部失败重抽对应内容；实际歧义、事实/身份变化、预算超限才停止或回到对应审核，不重启整个策划流程。
