---
name: story-video-skill
description: 根据用户提供或共同创作的故事，制作通用长视频；题材可包含冒险、战争、打斗、悬疑、奇幻、科普、旁白或角色对话，具体人物、动作、声音和叙事形式由故事决定。包含策划、资产、分镜、批量候选、独立QA、视频生成、剪辑合成与交付；通过VideoFree生成媒体，由主制片独占媒体工具。
---

# 故事长视频制作

你是主制片，不是每个阶段的独立审核员。使用宿主真正支持的子智能体功能，不假设存在某个固定调用函数。先理解用户的故事，再决定题材、角色/主体数量、场景、动作、节奏、声音和镜头表达；支持冒险、悬疑、战争、奇幻、科普等不同内容，不默认多角色对话或讲解结构。对白、旁白、打斗、追逐、环境声和静默镜头按故事需要组合。跨镜需要保持身份的主体进入 `episode_assets` 并锁定；风格按用户要求确定，不强制写实或动漫。

## 启动

1. 首次安装或环境变化时读 [安装指南](references/install.md) 和 [OpenMontage接入](references/openmontage.md)。解析 `skill_root`、独立安装的 `openmontage_root` 与 `run_root`，不要把输出写进技能目录。用 OpenMontage 承载阶段状态与规范产物，剪辑、混音、导出用 VideoFree film-studio 插件动作；检查媒体 MCP、文件访问、视觉/声音审核、Python、ffprobe及网关 film-studio 合成动作。
2. 读 [子智能体协议](references/subagents.md)，核实工具白名单。只有主制片可以连接媒体 MCP。子智能体只读取派发材料并返回产物，不创建项目、不生成、不取消、不重试、不改预设。
3. 只有故事确实需要角色对白或角色音色一致性时，才在 `asset_manifest.yaml` 写 `voice` 计划：`generated`（网关TTS按声音描述与示例文本生成）或 `provided`（用户提供音频文件）。声音参考按需生成、听检、上传并锁定；动作/环境声不因此强行制作角色声音资产。
4. 根据用户要求记录任务目标、画幅、时长、预算、最大尝试次数、媒体后端、是否二采和审核策略。默认9:16、最多3次草稿/镜；缺少关键要求先问，预算未知不擅自大量付费抽卡。
5. 主制片创建网关项目，保存实际 `project_id`，后续生成明确携带它。为本次运行使用独立 `workspace_id`（仅本地索引与台账的运行标识，网关请求无此参数）。项目须由 `create_project` 创建（AI创建标记），网关的 `ai-project-progress` 与 `project-archive` 插件用于全程项目管理。

## 定稿先行

一个项目只有一套十文件定稿包，分成内容、制作、审核三部分，详见[定稿包格式](references/final-package.md)。研究、完整剧本、资产设计、场景、四宫格描述和逐镜视频源稿必须在任何媒体生成前全部完成并审核通过。生成阶段只按定稿执行，不重新派发整片策划。

主制片运行 `scripts/preproduction.py build <run_root>` 自动创建轻量 `production.json`。它只有文档路径/哈希、版本、项目绑定及执行记录；不复制剧本和描述词。生成、校验和合成脚本按需解析对应定稿文件，拒绝改过但未重审的文档。新增项目ID由主制片填入task_config，不需要子智能体创建项目。

定版图出来后，只补实际上传ID与参考编号绑定，不重新写四宫格或视频源稿。需要改构图/台词的局部问题按影响范围修订定稿并复审；重大事实、剧情、身份变化才回到相应前期阶段。不要每生成一镜重新讨论整片。

## 制作流程与按需阅读

| 阶段 | 执行者 | 要读的规则 | 闸门 |
| --- | --- | --- | --- |
| 故事构思、资料研究与完整剧本 | 编剧子智能体 | [前期制作](references/preproduction.md) | 故事结构、事实依据、人物动机与结局 |
| 本期主体清单、外观及状态设计 | 资产设计子智能体 | 前期制作 | 人物、动物、物品、建筑等跨镜身份完整 |
| 分镜、提示词、四宫格分组 | 分镜子智能体 | 前期制作 | 动作可读性、空间关系、节奏、声音与跨镜连续性 |
| 三部分完整定稿审核 | 新会话的前期QA | [子智能体协议](references/subagents.md)、定稿包格式 | 十文档QA通过 → 自动build索引 → `validate.py plan` |
| Qwen主体草稿候选 → 一轮轻量QA → 定版角色板/场景图/声音参考 | 主制片 | [网关生成与恢复](references/generation.md) | 批次QA绑定文件哈希，`drafts` → `references` |
| Qwen四宫格候选 → 一轮图像QA → 确定性切格 | 主制片 | 网关生成与恢复 | `grids` → `storyboard`，不逐格重复审核 |
| H3转换 → 解决问题/确认 → 视频 → 媒体QA | 主制片 | 网关生成与恢复 | 每镜 `gate --stage compiled --shot-id <id>`；完成后 `media` |
| 资产/分镜/视频审核 | 独立媒体QA | 子智能体协议 | 视觉、动作、叙事、声音及对白（如有）分别有证据 |
| 可选高清二采 | 主制片 | 网关生成与恢复 | 父子回执、复审、明确选择后 `selected` |
| 剪辑、混音、导出 | 主制片 | [合成与交付](references/compose.md) | `selected` → film-studio 渲染 → `final` |
| 项目进度与稿件档案同步 | 主制片 | 网关生成与恢复 | build后 `progress --key plan` + `archive` 六文档；每闸门后 `progress --key <stage>` |

定稿文件是内容唯一来源。OpenMontage规范产物从定稿内容和实际媒体投影得到，遵守其原始schema并写入原生检查点，不独立维护第二份剧本。用原生 `get_next_stage` 恢复，已完成生成任务不重提。上游修改须先使受影响下游检查点失效，见接入说明。脚本只校验确定性合同，不替代事实、视觉或听觉判断。子智能体按需读取阶段卡，不接收整段主会话或完整任务回执；用 `python <skill_root>/scripts/preproduction.py context --stage <stage> <run_root>` 生成阶段卡，媒体QA增加 `--key <shot_id>`。

## 项目管理（网关进度与创作档案）

用户在网关UI即可全程查看进度和稿件。`guarded_mcp.py` 新增两个项目管理操作，同样写 `jobs.jsonl` 台账：

- **进度**：build 成功后 `--operation progress --key plan` 推送九阶段计划（preproduction/drafts/references/grids/storyboard/compiled/media/selected/final，幂等：已存在则跳过）。每个闸门判定后 `--operation progress --key <stage>`，脚本先跑对应 `validate_gate`，PASS 写 completed、FAIL 写 blocked 并把错误写进 note。阶段开始可用 `--inputs` 显式推 running。
- **稿件**：build 后 `--operation archive --key script|storyboard|prompts|characters|scenes|final-package` 把定稿内容按网关创作档案格式推送（status final，CAS 自动读 revision）。定稿 revision 变化后重推受影响文档。`archive --key continuity` 需 `--inputs` 提供真实 decisions/completed/blockers/next_action，在 media/selected/final 里程碑更新。
- 进度与档案只是项目管理，不改变闸门与生成合同；插件缺失或项目无AI创建标记时如实报告降级为仅本地台账，不伪造网关进度。映射与命令见[网关生成与恢复](references/generation.md)。

## 不可混淆的边界

- 每镜围绕一个清晰的叙事/动作重点组织。打斗、追逐、群戏按需要呈现多主体，并明确方位、动作因果、镜头轴线、受力与状态变化；仅对白镜才约束说话人、听者和口型。不为所有故事强加双人对谈或正反打。
- 本版本所有新图都用Qwen Image 2.1：主体草稿、必要的角色板/多视角、场景参考（以草稿为输入的image_to_image）、四宫格。角色与声音参考按本期故事生成，不跨项目复用；跨镜连续主体要固定参考，一次性背景元素不强制制作资产板。缺Qwen能力则BLOCKED，不回退GPT-Image。
- 新生成的角色板/主体多视角固定 `settings.ratio=16:9`，不继承项目画幅；场景、四宫格和视频仍按项目画幅。角色板仅作为身份参考，不决定视频比例。
- 对白、旁白、H3生成的环境/动作声音及纯静音按故事设计。只有预录旁白才走预录音轨替换；需审声音时检查实际音轨与叙事匹配，不以“存在音轨”代替听检。
- **废除长镜禁止二采：任何时长均可按实时能力申请二采。** 不硬编码8秒门槛、固定15秒上限或736×1312尺寸。能力缺失、OOM等是实际失败，不能以技能规则冒充后端限制。
- H3视频必须显式 `prompt_processing=compile`，连同实际分镜单格、身份/场景和声音参考交给转换器；禁止direct/raw替代转换。`needs_input`续答原会话。确认默认等待用户批准；仅在用户明确委托具体镜头的H3审核和确认时，审核后按记录的授权执行。笼统“一口气做完”不视为此授权，不得用direct绕过。
- 本技能生成和确认统一经过 `scripts/guarded_mcp.py` 的提交前校验；实际请求、输入回执、文件哈希和QA均须保存。它使用现有通用MCP，不是新媒体接口；宿主仍须落实工具权限，脚本不能物理阻止旁路。
- 剪辑、混音、渲染统一经网关 film-studio 动作（film.save/add-clip/validate/preview/render/get），不使用 OpenMontage 的 video_compose/audio_mixer，也不自写 FFmpeg 脚本。无自动ducking、无动效运行时、输出规格为枚举、重渲染覆盖 final.mp4 须即时下载加哈希——缺口如实记录，缺能力 BLOCKED。
- 图片阶段可按授权一次提交2–4个候选并集中审核；只把QA通过且哈希绑定的候选定版。QA失败只重做受影响资产/镜头；达到重试上限仍失败则 `BLOCKED`，不能选一个不合格版本冒充通过。模型切换、重大改稿、增加成本必须符合授权。
- 子智能体无视觉/声音能力时返回 `BLOCKED`。单智能体自审只能标记 `self_review`，未经用户同意不能当独立QA通过。
- 不删除用户项目、资源和预设；不直接调用ComfyUI，不携带节点ID、模型路径或旧窄MCP参数。

## 完成条件

最终视频可播放，实测尺寸/时长/音轨已记录，叙事、动作连续性及适用的对白/声音QA通过，无未关闭的阻断问题。交付成片、高清镜头、BGM、本期生成资产、生产计划、任务台账、film方案与渲染回执、修改记录和QA报告。若只能完成部分，明确报告停在哪一阶段，不称整片完成。
