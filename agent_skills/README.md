# 智能协作技能管理

## MiniMax H3 管线

MiniMax H3 使用一条精简管线：

1. `pipeline/requirements.md`：制片确认素材职责、声音、配乐、内容用途与可行性，并输出可组合的 `capabilities`。除非用户明确指定，不预先决定镜头结构。
2. `pipeline/h3-director-compiler.md`：单一 H3 导演在一次调用中完成动作、表演、必要切镜、运镜和英文执行稿。程序按 `capabilities` 同时加载打斗、大招、对白、微表情、解说、电商或产品展示窄技能，不再让多个创作阶段接力改稿。
3. `pipeline/h3-chinese-translation.md`：完整翻译英文执行稿供中文用户确认。
4. 网关执行确定性检查；不再调用 AI 总监制评价创意。网页由用户确认，API V2 可由调用方 AI 审核。

一次生成是一个用户指定时长、最长 15 秒的视频片段，不等于只能有一个摄影镜头。`continuous` 使用连续镜头，双人对白可以使用 `shot_reverse_shot`，确有必要的动作或展示可以使用 `limited_sequence`。大型第三方导演资料和动态技能工具链不进入运行时；其中有价值的动作规则只以精炼后的窄技能形式按需加载。

MiniMax 官方 Skill 的来源记录在 `models/minimax-h3/upstream/h3-prompt-writing/SOURCE.md`。

## 其他模型

Krea2、Qwen、LTX 2.5 和 MiniMax Music 使用 `system.md + models/<model>/model.md + modes/<mode>.md` 的单阶段流程。
