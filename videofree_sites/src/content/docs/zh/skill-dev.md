---
title: 全自动长视频技能开发
lead: 仓库的演示技能 dialogue-video-skill 能把一个选题做成多角色对话长视频：研究、剧本、资产、分镜、逐镜生成、QA、剪辑合成全程由智能体自动执行。本篇拆解它的架构，教你做出自己题材的全自动流水线技能。
order: 7
---

## <span class="no">1</span>技能是什么

一个技能就是一个目录，放进智能体的技能目录即安装：

```text
dialogue-video-skill/
├─ SKILL.md          ← 主制片手册：流程、边界、完成条件
├─ references/       ← 阶段卡：前期、生成、合成、子智能体协议，按需读取
└─ scripts/          ← 确定性脚本：定稿索引、闸门校验、受控提交
```

SKILL.md 不是提示词模板，而是**给主智能体读的作业手册**；references 按阶段拆分，避免一次性塞满上下文；scripts 承担所有确定性工作——校验、哈希、台账，不靠模型记忆。

<div class="diagram">
  <div class="dtitle">three layers</div>
  <div class="dstack">
    <div class="dbox"><b>技能层</b><small>dialogue-video-skill（编排与合同） + OpenMontage（管线状态、阶段检查点、产物校验）</small></div>
    <div class="dbox hot"><b>VideoFree Studio 网关层</b><small>MCP 工具：能力发现 / 生成 / 等待 / 产物 · film-studio 动作：剪辑、混音、导出 · 进度与创作档案插件</small></div>
    <div class="dbox"><b>ComfyUI 引擎层</b><small>插件工作流：Qwen Image 2.1 出图 · MiniMax H3 对白视频 · TTS 配音</small></div>
  </div>
  <div class="dnote">技能层永远不直连 ComfyUI，不携带节点 ID 和模型路径——这是流水线可恢复、可换后端的前提</div>
</div>

## <span class="no">2</span>九阶段流水线

整片按固定阶段推进，每个阶段有闸门（gate），闸门不过不进入下一阶段：

<div class="diagram">
  <div class="dtitle">pipeline gates</div>
  <div class="dwrap">
    <div class="dbox"><b>preproduction</b><small>定稿包 + 前期QA</small></div>
    <div class="dbox"><b>drafts</b><small>主体草稿</small></div>
    <div class="dbox"><b>references</b><small>定版角色板/场景/声音</small></div>
    <div class="dbox"><b>grids</b><small>四宫格分镜图</small></div>
    <div class="dbox"><b>storyboard</b><small>分镜单格</small></div>
    <div class="dbox"><b>compiled</b><small>H3 编译确认</small></div>
    <div class="dbox"><b>media</b><small>镜头草稿 QA</small></div>
    <div class="dbox"><b>selected</b><small>版本选定</small></div>
    <div class="dbox hot"><b>final</b><small>film-studio 成片</small></div>
  </div>
</div>

阶段状态由 OpenMontage 的 `dialogue-video` 管线承载，恢复时用原生 `get_next_stage`，**已完成的生成任务绝不重提**；上游修改先让受影响的下游检查点失效，再局部重做。

## <span class="no">3</span>五条值得抄的架构规则

1. **定稿先行**。一个项目只有一套十文件定稿包（研究、完整剧本、资产设计、场景、四宫格描述、逐镜源稿等），全部审核通过后才允许碰任何媒体。`production.json` 只存文档路径、哈希、版本和任务绑定，不复制内容——改过但未重审的文档会被脚本直接拒绝。
2. **阶段闸门**。`validate.py` 校验确定性合同：文件在不在、哈希对不对、参考 ID 绑没绑。PASS 推进，FAIL 写 blocked。脚本不替代审美判断——看图听声是独立 QA 子智能体的事。
3. **受控提交**。所有生成统一经过 `guarded_mcp.py`：提交前校验参数合同，提交后把请求、回执、哈希写进 `jobs.jsonl` 台账，`idempotency_key` 防重复抽卡。详见[窄 MCP 封装](/guide/narrow-mcp/)。
4. **子智能体协议**。只有主制片能连媒体 MCP；子智能体只接收阶段卡（`preproduction.py context --stage` 生成），返回产物，不建项目、不生成、不重试、不改预设。单智能体自审只能标 `self_review`，不能冒充独立 QA。
5. **BLOCKED 语义**。缺能力、超重试上限、QA 不过——如实阻断并报告停在哪一阶段，绝不拿不合格版本冒充通过。预算未知不擅自大量付费抽卡。

## <span class="no">4</span>动手：做你自己的技能

以 dialogue-video-skill 为底改造，比从零写快得多。把仓库交给你的开发智能体：

> 阅读 examples/skills/dialogue-video-skill 的 SKILL.md 与 references/，保留九阶段闸门、定稿先行与受控提交架构，把题材改造为【你的题材，例如：单人口播财经解读】：替换资产策略、镜头风格、画幅与 QA 标准。所有媒体生成继续走 videofree MCP 通用工具，剪辑合成继续走 film-studio 插件动作，不要自写 FFmpeg，不要直连 ComfyUI。

改造时保持的骨架：SKILL.md 定边界与完成条件 → references 拆阶段 → scripts 写确定性校验与受控提交。可以替换的部分：阶段数量与闸门内容、资产策略（角色板/产品图/图表）、QA 标准（对白准确性/口型/构图主次）。

仓库里还有 `short-video-skill`（短视频文案）和 `videofree-creation`（通用创作）两个技能示例，可以对照看不同复杂度的写法。

## <span class="no">5</span>试跑与放量

1. **先跑一集 1 分钟、3 个镜头的小样**，每镜最大尝试次数写进任务配置（默认 3 次），预算封顶；
2. 全程在网关界面看进度：`ai-project-progress` 插件显示九阶段状态，`project-archive` 插件归档定稿稿件——技能每过一道闸门就推送一次；
3. 小样通过后加时长、加镜头；高清二采按需申请，任何时长都可以二采，选版必须人工确认；
4. 交付核对：成片可播放、实测尺寸/时长/音轨有记录、对白 QA 通过、任务台账完整。

::note
成片、混音、导出统一走网关 film-studio 动作（film.save / add-clip / validate / preview / render / get），重渲染会覆盖 final.mp4，拿到后立即下载并记哈希。
::
