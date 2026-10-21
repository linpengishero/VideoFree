# Example skills / 演示技能

These optional packages demonstrate using VideoFree Studio from an external agent.
They are not framework source or runtime dependencies. Install complete skill
directories into the skill location supported by your agent; copying only
`SKILL.md` is insufficient. Configure the agent's VideoFree Studio MCP connection or
the REST client's gateway URL as described by the selected skill.

这些可选技能用于演示外部智能体如何使用 VideoFree Studio，不属于框架源码或运行依赖。
请将完整技能目录安装到智能体支持的技能位置，不要只复制 `SKILL.md`。
按对应技能说明配置 VideoFree Studio MCP 连接或 REST 客户端网关地址。

| Skill / 技能 | Purpose / 用途 |
| --- | --- |
| [videofree-creation](skills/videofree-creation/SKILL.md) | Direct API client and MCP guide / API 客户端与 MCP 指南 |
| [dialogue-video-skill](skills/dialogue-video-skill/SKILL.md) | Dialogue video production example / 对话视频制作演示 |
| [openmontage](skills/openmontage/SKILL.md) | Independent editing toolkit; retain its AGPL-3.0 license and notices / 独立剪辑工具包，保留其 AGPL-3.0 许可证及声明 |

The plugin development skill remains in
[.agents/skills/videofree-plugin-development](../.agents/skills/videofree-plugin-development/SKILL.md)
because it supports development of this repository.

插件开发技能保留在上述 `.agents/skills/` 目录，用于本仓库开发。

Run example tests separately / 单独运行演示测试：

```shell
python -m unittest discover -s examples/tests -p "test_*.py"
```

Framework tests remain in `tests/`. Each bundled toolkit may also provide its
own tests and dependencies; see its documentation.

框架测试仍在 `tests/`；工具包自有测试与依赖请参阅各自文档。

The dialogue example's existing tests still target an earlier fixed cast and
bridge CLI. They currently fail against the revised example and need updating
before they can serve as an acceptance check. Relocating them does not fix those
pre-existing mismatches.

对话演示的现有测试仍使用旧版固定角色和桥接命令，与当前演示不一致，尚不能作为
验收通过依据；本次目录迁移保留这些既有测试，未修改演示业务实现。
