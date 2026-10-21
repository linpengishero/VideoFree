# 安装与能力检查

## 安装

把整个 `dialogue-video-skill` 目录安装到目标智能体支持的技能目录，入口为 `SKILL.md`。必须一起携带 `references/`、`scripts/`，不是只粘贴入口文本。技能不随包任何角色资产，角色全部按剧本生成。不同平台的技能目录和子智能体接口以该平台说明为准。

本包不依赖旧 `dialogue-man`、Hermes、看板服务或 `/shared` 挂载。必须同时独立安装完整 `openmontage` 包（含 `dialogue-video` 管线），保留其 AGPL-3.0 许可证、版权和来源声明；不是只复制 SKILL.md。使用其管线状态、检查点与规范产物；剪辑、混音、渲染由网关 film-studio 插件完成，不另写合成器，也不使用 OpenMontage 的 video_compose/audio_mixer。Python依赖按 OpenMontage requirements 安装，ffprobe需在PATH用于下载校验；Remotion/HyperFrames不再用于本技能合成。旧包保留供原环境使用。本包不安装模型，不另启媒体服务。具体命令见 [OpenMontage接入](openmontage.md)。

主制片连接现有videofree MCP：`http://192.168.50.8:8765/mcp`。当前不用token。支持远程HTTP MCP的客户端填写服务名 `videofree` 与URL；部分客户端支持：

```json
{"mcpServers":{"videofree":{"type":"http","url":"http://192.168.50.8:8765/mcp"}}}
```

`type` 字段按客户端实际要求调整，不是通用配置。此服务接受POST JSON-RPC并返回JSON，不提供旧版SSE端点。网关正常运行即可，不需要另启8991等旧窄MCP端口。局域网另一台设备不能使用localhost连接网关。未来开启认证时只给主制片配置管理员提供的认证信息；guarded_mcp读取环境变量 `VIDEOFREE_API_TOKEN` 作为 `x-api-token` 请求头。

## 必须核实的能力

| 能力 | 检查方法 | 缺失时 |
| --- | --- | --- |
| 网关与能力发现 | `get_health`、`list_capabilities`、`get_capability` | 停止生成 |
| Qwen全图像链及H3转换 | 发现Qwen文生图、角色板、image_to_image场景参考、四宫格、image.split及video.reference的compile能力 | 停止，不回退GPT或direct视频 |
| 角色声音生成 | `list_plugin_actions`/`list_voices` 发现speech_preset、speech_describe等TTS动作且ready | 停止声音参考生成，不用本地TTS替代 |
| film-studio合成 | `list_plugin_actions` 发现film.save/add-clip/validate/preview/render/get且automation可用 | 停止合成，不写本地FFmpeg替代 |
| 项目管理插件 | `list_plugin_actions` 发现ai-project-progress.plan/update与project-archive.get_document/save_document且automation可用；项目由create_project创建（AI创建标记） | 降级为仅本地台账与文档并如实记录，不伪造网关进度或档案 |
| 子智能体及工具过滤 | 使用宿主的创建子智能体/工具白名单功能，检查实际生效配置 | 报告未隔离，转受限自审或换宿主，不冒充强隔离 |
| 图像/视频审核 | 验证审核模型真的能读参考图、视频或抽帧 | 对应QA标记BLOCKED |
| 声音审核 | 音频理解/听检，必要时ASR；不能用ffprobe替代 | 声音QA标记BLOCKED |
| 本地文件和下载 | 主制片能下载产物到run_root；共享材料对QA可见 | 停止本地合成，不传不可达路径 |
| 工具链 | `python --version`、`ffprobe -version`；渲染在网关film-studio端执行 | 修复环境，不改走未知后端 |

只有主制片绑定媒体MCP。子智能体关闭媒体工具、任意Shell、通用HTTP、浏览器任意导航、写入主目录、再次委派和继承工具；只放行实际需要的检索或媒体查看能力。脚本、ffprobe和抽帧由主制片执行，检测结果作为只读材料发给QA。

工具过滤是宿主能力，技能无法修改宿主权限。宿主无法限制时，不启动拥有全套工具的所谓“受限QA”；先报告限制。即使工具过滤成功，也不是多租户安全边界，网关仍是家庭局域网服务。

## 路径约定

- `skill_root`：安装后的技能绝对路径，资产路径相对它解析。
- `run_root`：一次制作的独立工作目录，生产计划、下载、台账和QA放这里。
- `deliver_root`：交付目录，可为run_root下的 `deliver/`。
- 子智能体只得到必要文件的可访问副本或附件，不得到服务器磁盘路径。

整个技能目录可直接复制到另一台机器。首次使用刷新技能发现，调用 `dialogue-video-skill`；示例需求：“围绕这个知识点设计两个角色对话讲解，角色形象和声音都由你按剧本生成，制作60秒竖屏视频，先完成并审核十文档定稿包，再按授权预算执行，保留对白、不要字幕；委托你审核并确认这份定稿各镜头的H3转换结果，遇到实质歧义再问我。”不确定预算、角色数量或画风时先补充要求。

定稿格式和build命令见[定稿包](final-package.md)。production.json由脚本生成，不要求用户或智能体手写大快照。所有脚本使用与OpenMontage相同的Python环境（含其既有PyYAML依赖）。
