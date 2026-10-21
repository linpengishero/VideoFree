# 一套定稿包，三个部分

一个项目只有一套定稿包。前期把全部文案做好、完成审核，然后生成阶段只读取定稿执行。下面十文件放在run_root顶层，文件名固定；输出图像、视频、台账和QA放执行目录，不放技能目录。

| 部分 | 文件 | 唯一职责 |
| --- | --- | --- |
| 内容 | task_config.yaml | 目标、预算、画幅、时长、模型与授权边界 |
| 内容 | research_notes.md | 完整研究、来源和不确定性 |
| 内容 | story_script.yaml | 完整故事文本/剧情节拍；仅按需包含角色对白与逐字口播稿 |
| 制作 | production_plan.md | 制作顺序、配乐、二采、合成与交付策略 |
| 制作 | asset_manifest.yaml | 跨镜主体身份、状态及按需使用的声音设计 |
| 制作 | scene_plan.yaml | 场景布局、气氛、镜头与资产使用关系 |
| 制作 | storyboard_groups.yaml | 逐镜视觉设计、四宫格顺序和每格图像描述 |
| 制作 | asset_prompts.md | Qwen草稿与定版角色板/场景图描述 |
| 制作 | video_prompts.yaml | 逐镜H3转换源稿、动作、运镜、对白（如有）和声音映射 |
| 审核 | preproduction_qa.md | 当前版本完整审核、问题关闭及来源文件哈希 |

没有随包固定角色：人物、动物、阵营、场景、道具及其状态全部由故事决定；跨镜或必须保持身份的主体才列入连续性资产，一次性背景元素不强制生成多视角板。先列清单、写完整草稿及定版描述；必要的主体参考板固定16:9。只有确实需要固定角色音色/对白时才添加 `voice` 计划（generated或provided）。前期写完整故事与镜头设计，不预设对谈结构。

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
  workspace_id: 本次独立运行ID（仅本地索引与台账，不随网关请求发送）
  aspect: '9:16'
  duration_target_sec: 60
  max_attempts_per_shot: 3
  min_scenes: 3
  single_scene_reason: ''
  allow_self_review: false
  automation_authorization:
    scope: this_project_and_revision
    h3_review_and_confirm: true
    self_review_fallback: false
    local_export: true
    external_publish: false
    evidence: 用户本次开场授权原文及时间
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

generation_settings按阶段保存前期确认的参数，字段和值必须以网关实时能力为准，上例不代替能力发现。程序按定稿自动填入画幅、按shot_ids顺序嵌入四宫格prompt的四条图格描述、逐镜时长和全部实际参考输入；角色板画幅始终覆盖为16:9。改变这些生成设置须修订并重审，不临时覆盖定稿。

`automation_authorization`必须来自开场真实授权，限定本项目与当前定稿revision。开始前一次确认H3逐稿审核/确认、QA代理不可用时是否允许明确标记的self_review、预算/重试/二采上限及本地导出；授权生效后不逐镜或逐阶段停下来询问。self_review获准时同时设`allow_self_review: true`。若H3审核确认获准，build后须在`production.json`写入对应的`h3_delegation`，其中`shot_specs`逐镜绑定当前compile规格；准确结构见[自动制作授权](generation.md)。超预算、外部发布、改变已批准故事方向仍须另行批准；真实歧义或能力故障按恢复规则处理。仅设置`h3_review_and_confirm: true`不代表允许self_review或外部发布。

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

story_script.yaml：

```yaml
story_beats:
  - id: beat_001
    purpose: 主角发现异常并决定追踪
    change: 从日常状态进入冲突
turns: [] # 可省略；只在故事包含逐字对白/口播时填写
```

有对白时，`turns` 使用以下结构；speaker/listener 可为空或省略 listener，不强制每段对白都是双人对话：

```yaml
turns:
  - id: turn_001
    speaker: protagonist
    function: warning
    line: 原始台词
    normalized_line: 最终逐字口播稿
    typo_checked: true
    speech_checked: true
```

story_beats描述完整故事的起承转合、冲突、转折与结局；可以是纯动作故事，不要求对话。每个turn必须对应镜头；实际存在的对白须绑定正确说话人并逐字核对。分镜文件不重复维护脚本字段。

### 制作部分

production_plan.md写清按什么顺序执行、Qwen/H3能力、参考使用、声音保留、配乐简报、预算/重试上限、二采策略及成片输出规格（film-studio的width/height/fps/fit与BGM音量策略）。这里不再复制逐字剧本或逐镜描述词。

asset_manifest.yaml：

```yaml
episode_assets:
  - id: protagonist
    kind: character
    description: 主角的外形、服装、伤势/装备等需要跨镜保持或演化的状态
  - id: scene_alley
    kind: location
    description: 该环境的身份及不变项
  - id: pursuer
    kind: character
    description: 追踪者外观与行动特征
```

人物、动物、阵营标识、物品、建筑、车辆等只要跨镜需识别为同一个就列入；资产集合由故事决定，不必为一次性群众或背景元素逐一造资产。角色只有在需要台词/固定音色时才填写 `voice` 计划。环境身份在这里定义，具体布局在scene_plan中，完整生成描述在asset_prompts中。

scene_plan.yaml：

```yaml
scenes:
  - id: scene_alley
    description: 场景设计及叙事功能
    layout: 主角、追踪者与出口的空间关系
    lighting: 灯光及时间
    shot_ids: [shot_001, shot_002, shot_003, shot_004]
```

每个location资产恰好一个场景条目；场景设计进入相关资产/镜头规格校验，修改后不能复用不匹配的旧参考。

storyboard_groups.yaml包含shots及storyboard_groups：

```yaml
shots:
  - id: shot_001
    story_beat_ids: [beat_001]
    audio_mode: h3_scene_audio
    duration: 6
    scene_id: scene_alley
    scene_function: pursuit
    shot_pattern: tracking_wide
    required_assets: []
    visible_characters: [protagonist, pursuer]
    action_start: 动作起点
    action_process: 动作过程
    action_end: 动作终点
    camera: 机位及运动
    continuity_in: 承接上一镜
    continuity_out: 衔接下一镜
    storyboard_prompt: 该格静态画面描述，包含构图、姿态、视线及参考身份
storyboard_groups:
  - id: grid_001
    scene_id: scene_alley
    panels: 4
    shot_ids: [shot_001, shot_002, shot_003, shot_004]
```

所有镜头在分组中恰好出现一次，每组四镜同一场景。storyboard_prompt是Qwen静态分镜图描述，不是H3视频动作源稿；生成时程序按shot_ids顺序把这四条描述嵌入单一四宫格prompt（Panel 1至4对应左上、右上、左下、右下）。实际图片输入根据scene_id、出镜角色和required_assets绑定，不能只把描述词传过去。

`audio_mode`按镜头声音设计取值：`h3_dialogue`（角色对白，绑定turn与说话人声音参考）、`h3_scene_audio`（H3生成环境/动作声音，不附加角色参考音频）、`pre_recorded_narration`（使用预录旁白替换）、`silent`（明确静音）。无对白镜头不填turn/speaker/listener；有多个出镜主体时用`visible_characters`列出需要身份保持的角色。打斗/追逐镜头需写清空间方位、动作起因与结果、受力、道具状态、镜头轴线和前后镜承接。

asset_prompts.md每项写完整设计说明，唯一数据块：

```yaml
prompts:
  - asset_id: pursuer
    draft: 追踪者主体草稿描述
    reference: 追踪者定版身份参考描述，锚定草稿参考图
  - asset_id: scene_alley
    draft: 完整Qwen场景草稿描述
    reference: 完整Qwen定版场景描述，锚定草稿参考图
```

每个episode_asset必须有draft/reference两条非空最终描述。草稿完成后只绑定真实图片，不另创外观；提交参数必须使用这里的原稿。

video_prompts.yaml：

```yaml
shots:
  - shot_id: shot_001
    reference_map: 图片1=分镜单格，图片2=主角参考，图片3=场景，图片4=关键道具
    execution: 完整H3转换源稿，包含身份引用、动作因果、空间关系、时序、运镜及按故事需要的对白/声音设计
```

镜头覆盖必须与shots完全一致。含对白的execution必须包含对应turn的normalized_line逐字台词；无对白镜头不应凭空添加对白。动作场面须保持故事事件和因果，不为适配模型而压缩或改写剧情。脚本会阻止实际对白与转换源稿不一致。

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
  story_script.yaml: 实际SHA256
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
  checks: {facts: PASS, narrative: PASS, assets: PASS, storyboard: PASS}
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
