---
name: openmontage
description: 使用 OpenMontage 完整源码进行管线化视频制作、阶段检查点、产物校验、工具发现和 FFmpeg/Remotion/HyperFrames 合成。可独立使用，也作为 VideoFree Studio 故事视频技能的制作底座。
---

# OpenMontage

本目录是完整的 OpenMontage 源码包，不是 videofree 的改名版本。先读
[AGENT_GUIDE.md](AGENT_GUIDE.md) 和 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)，
按需读取实际管线、阶段 director、工具声明的技能和 schema。不得跳过管线直接生成。

## 安装与运行

- Python >= 3.10；在目标智能体使用的 Python 环境安装 `requirements.txt`。
- FFmpeg/ffprobe 放入 PATH。Remotion 按 `remotion-composer/` 原说明安装；
  HyperFrames 按 `skills/core/hyperframes.md` 配置。Node 渲染依赖只在选用对应渲染器时安装。
- 从本目录运行原 Python 命令，或将本目录加入该命令的 Python 模块搜索路径。
- 所有运行输出放到独立工作区；导入之前设置 `OPENMONTAGE_PROJECTS_DIR` 为该工作区的项目父目录。
- 通过 `tools.tool_registry.registry` 发现工具，只调用已配置、已授权的工具；
  实际工具接口是 `.execute(inputs)`，检查 `ToolResult.success`，不臆造 `.run()`。
- 缺依赖或能力明确返回 BLOCKED；不要自动下载模型、开启服务、安装全部供应商或降级成幻灯片。

## 与 story-video-skill 一起使用

两包分别安装。默认同级目录，也可以由用户指定两包的绝对路径。
VideoFree Studio 故事视频技能选择管线 `pipeline_defs/story-video.yaml`，读取
[导演规则](skills/pipelines/story-video/director.md)。不要混入
`pk-dialogue-story.yaml` 的原 Hermes 专用限制。

调用方的 `references/openmontage.md` 说明实际检查点命令、阶段产物、生成工具边界及恢复流程。
不能因调用方指定了 videofree 就擅自启用本包的其他生成供应商。
Remotion/HyperFrames 仍使用原始工具与原始 schema，不提供缩水替代实现。

## 版权和分发

原 README、版权声明、完整 [AGPL-3.0 许可证](LICENSE) 及第三方证明保留。
分发时携带完整源码与许可证，不仅分发入口文件。新增兼容入口和管线见
[集成说明](docs/story-video-integration.md)，它们不代表上游官方发布。
