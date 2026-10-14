# videofree

当前版本：`1.1.0`

## 许可证与第三方边界

videofree 自有源代码按 [GNU AGPL-3.0](LICENSE) 发布。AGPL-3.0 允许商业使用，
但使用、修改、分发或通过网络提供服务时必须履行许可证规定的义务。需要闭源集成、
企业部署、白标、技术支持或定制开发时，可查看[商业授权说明](COMMERCIAL_LICENSE.md)。

本项目主要负责调用用户配置的 ComfyUI 和外部媒体服务；ComfyUI、社区节点、模型、
LoRA、字体、FFmpeg 及其他资源不属于 videofree 的统一授权范围，请遵守各自许可证。
OpenMontage 是 `.agents/skills/openmontage/` 下可选安装的独立技能和剪辑工具，不是
videofree 网关的核心运行依赖，使用时请保留其目录中的许可证和版权声明。详见
[第三方组件说明](THIRD_PARTY_NOTICES.md)。

运行在 Windows + GPU 上的本地 AI 创作工作台，包含图片、视频、声音、音乐生成、持久任务记录和本地资源管理。

videofree 集成本地与云端 AI 能力，本地生成与部分后处理能力基于 ComfyUI 及其社区插件构建。模型与插件的版权和许可归各自作者所有，使用或分发时请遵守对应许可。

## AI军火库与知识星球

- **AI军火库 · 前沿 AI 技术网站**：[laobanclaw.top](https://laobanclaw.top/)，关注前沿 AI 技术与实际应用。
- **知识星球**：分享各类 AI 视频自动化流水线，以及 AI、智能体与大模型专业知识。可在工作台首页扫码，或点击下方二维码放大查看。

[![知识星球二维码](frontend/public/contact/zsxq-qr.png)](frontend/public/contact/zsxq-qr.png)

## 配套 ComfyUI 模型和插件

我用夸克网盘给你分享了「配套Comfyui模型和插件」，点击链接或复制整段内容，打开「夸克APP」即可获取。

```text
/~576c3bQw8h~:/
链接：https://pan.quark.cn/s/306e83d5c2ce
提取码：5vM9
```

下载入口：[配套 ComfyUI 模型和插件](https://pan.quark.cn/s/306e83d5c2ce)

整合包包含项目配套所需的模型和插件。请保留模型文件名、模型子目录和插件目录结构，避免工作流找不到对应资源。插件安装或更新后，需要重启 ComfyUI 才会加载。

**重要：配套 ComfyUI 必须安装 SageAttention，否则使用依赖该注意力实现的工作流会报错。** SageAttention 要安装到 ComfyUI 实际使用的 Python 环境，不能只安装到系统 Python；其版本需与 Python、PyTorch、CUDA 和显卡环境匹配。安装失败时先检查对应版本的安装说明，不要盲目升级整合包中的 PyTorch。SageAttention 是运行依赖，不是模型文件，也不等同于注意力补丁节点。

## 启动

解压完整发布包后，直接双击 `start_gateway.cmd`。程序使用随包附带的 Python，启动成功后会自动打开创作页面，不要求用户安装 Python 或 Node.js。

首次使用请在网页设置中填写 ComfyUI 网关地址。项目资源目录自动创建，生成素材按图片、视频、声音和音乐分类保存，无需设置资源目录。需要通过环境变量覆盖配置时，可将 `.env.example` 复制为 `.env`。

`start_gateway.cmd` 会自动读取根目录的 `.env`；直接通过 PowerShell 启动 Python 时，PowerShell 本身不会自动读取该文件。网关默认监听 `0.0.0.0`，可通过本机或局域网访问；对局域网开放时建议设置 `MEDIA_GATEWAY_TOKEN`。如需限制为仅本机访问，将 `MEDIA_GATEWAY_HOST` 设置为 `127.0.0.1`。ComfyUI 地址通过 `COMFYUI_URL` 配置。

## 基本配置教程

网页图文教程：启动 videofree 后，在首页知识星球说明下点击“安装部署教程”或“全自动技能包教程”。也可访问 `http://127.0.0.1:8765/?guide=install` 与 `http://127.0.0.1:8765/?guide=skills`；局域网使用时替换为网关电脑的实际 IP。教程包含安装步骤、工作台界面示例和可交给智能体的安装指令。

### 1. 准备并启动 ComfyUI

解压配套 ComfyUI 整合包，确认模型、插件及 SageAttention 已安装到对应环境。先启动 ComfyUI，等待控制台显示访问地址，并检查是否有插件导入失败信息。用浏览器打开该地址，确认 ComfyUI 正常运行。

默认连接地址为 `http://127.0.0.1:8189`。如果 ComfyUI 实际监听其他端口，请使用控制台显示的地址，不要照抄默认端口。

### 2. 启动 videofree 并配置连接

双击 `start_gateway.cmd`，本机访问 `http://127.0.0.1:8765/`，进入工作台的设置，填写实际的 ComfyUI 地址并保存。ComfyUI 与网关在同一台电脑时使用 `127.0.0.1`；不同电脑时使用 ComfyUI 所在电脑的局域网 IP，并确保其监听地址和防火墙允许访问。

可选：复制 `.env.example` 为 `.env`，按实际情况修改以下内容。修改后重新启动网关：

```dotenv
COMFYUI_URL=http://127.0.0.1:8189
MEDIA_GATEWAY_HOST=0.0.0.0
MEDIA_GATEWAY_PORT=8765
MEDIA_GATEWAY_TOKEN=
```

局域网设备访问 `http://网关电脑的局域网IP:8765/`，不要使用 `0.0.0.0` 或另一台设备的 `localhost` 作为浏览器地址。访问失败时检查 Windows 防火墙是否允许网关端口；不要把免认证服务直接暴露到公网。

### 3. 配置 AI 与云端能力

需要导演协作、H3 描述词转换等能力时，在网页设置中配置对应 AI 服务的接口地址、模型名称及 API Key。需要 GPT-Image 云端生图时，配置 GrisAI API Key；仅使用本地生成能力时，不必配置该云端密钥。密钥不要写入 README 或提交到公开仓库。

### 4. 创建项目并生成素材

在工作台创建项目，填写名称、简介和内容概要，然后进入项目提交生成。系统自动创建项目目录，并按 `images`、`videos`、`audio`、`music` 分类保存最终素材，无需手动指定资源目录或同步 ComfyUI 输出文件。

生成素材位于 `data/projects/`。音色样本位于 `data/cache/voice_samples/`，预设配置、项目与任务记录保存在 `data/media_gateway.db`。不要把数据库和音色样本当作普通缓存删除。备份时保留整个 `data/`。

### 5. 常见问题

- **找不到节点**：确认对应插件已安装、依赖安装成功，并已重启 ComfyUI；查看启动日志中的导入错误。
- **找不到模型或 LoRA**：检查文件名、模型类型及子目录是否与工作流一致；仅下载模型但放错目录同样无法使用。
- **SageAttention 导入失败**：检查是否安装在 ComfyUI 自带 Python 中，以及依赖版本是否匹配；以 ComfyUI 启动日志为准。
- **视频保存失败**：H3 保存依赖 VideoHelperSuite 和支持 NVIDIA NVENC 的 FFmpeg，详见下方 API 说明。
- **显存不足**：先降低分辨率或时长；不同模型和后处理阶段的显存需求不同，配套整合包不保证所有尺寸都能在任意显卡运行。
- **网关在线但无法生成**：网关与 ComfyUI 是两个进程，分别检查连接地址、ComfyUI 状态及任务报错。

如需让外部 AI 调用，使用 `.agents/skills/zizai-creation` 中的技能与客户端，并将网关地址配置为调用设备可访问的地址。接口及可用能力以 `/api/v2/capabilities` 返回为准。

## API

设置 `MEDIA_GATEWAY_TOKEN` 后，接口使用 `X-API-Token` 认证；留空则免认证。生成前通过 `/v1/uploads` 流式上传素材，再将返回的 `upload:<id>` 放入生成请求。任务可通过 `/v1/jobs/{id}` 查询，通过 `/v1/jobs/{id}/cancel` 取消。

工作流按类型存放在 `workflows/`，并统一注册到 `workflows/registry.json`。网关只调用注册表中存在的工作流；请求中的 `{{prompt}}` 会在提交 ComfyUI 前替换。

H3 生成与二采的最终保存链路在提交前统一编译为 VideoHelperSuite `VHS_VideoCombine`，使用独立 FFmpeg 的 `video/nvenc_h264-mp4` 编码（H.264、15 Mbps、原有音频）。ComfyUI 需安装 VideoHelperSuite，且其 FFmpeg 支持 NVIDIA NVENC；不会回退到已出现原生崩溃的 PyAV 保存链路。仓库工作流模板的输出节点编号、采样参数和 latent 保存逻辑保持不变，任务快照记录实际提交的编码节点。

队列默认最多等待 20 个任务，可通过 `MAX_QUEUE_SIZE` 调整。排队任务和 ComfyUI `prompt_id` 保存在 SQLite 中，网关重启后会继续排队或追踪已经提交的任务。

智能协作默认不限制本地模型响应时间。需要设置上限时，可通过 `AGENT_TIMEOUT_SECONDS` 指定秒数；保持为 `0` 时，连接未断开且网关仍在运行就会继续等待。

### AI API v2

面向 AI 的稳定接口位于 `/api/v2`。先调用 `/api/v2/capabilities` 发现当前可用能力，再通过 `/api/v2/uploads` 上传素材，最后向 `/api/v2/generations` 提交能力 ID、素材角色、比例和命名分辨率。该接口不会暴露 ComfyUI 节点、工作流文件或模型路径。

声音、音乐和图片预设分别通过 `/api/v2/voices`、`/api/v2/music/*` 和 `/api/v2/image/styles` 查询。AI 调用 Skill 位于 `.agents/skills/zizai-creation`，其中包含无第三方依赖的命令行客户端。

支持 MCP 的其他 AI 可使用 [MCP 安装与使用指南](.agents/skills/zizai-creation/references/mcp-install.md)，该文件可单独转发。局域网入口为 `http://127.0.0.1:8765/mcp`，随网关启动，不需要额外服务；原有 REST 技能保留。

### 双主持人视频技能

[dialogue-video-skill](.agents/skills/dialogue-video-skill/SKILL.md) 与独立的 [OpenMontage](.agents/skills/openmontage/SKILL.md) 整包安装：主制片使用媒体 MCP，宿主原生子智能体负责剧本、分镜和独立 QA；OpenMontage 原生工具负责剪辑、混音、渲染和阶段检查点，不另写合成器。包含固定角色及声音参考、合同校验和原生接入桥；不依赖 Hermes，原 `dialogue-man` 保留。OpenMontage 完整源码、AGPL-3.0许可证及版权声明保持随包分发，集成增量见其文档。安装和权限配置见 [安装说明](.agents/skills/dialogue-video-skill/references/install.md)。长镜允许按实际可用能力二采，不再使用八秒禁用规则。

### 安装示例技能

仓库提供双主持人对话视频制作示例，只需安装以下两个完整目录到智能体支持的技能目录，再给主制片配置 videofree MCP，不要只复制 `SKILL.md`：

| 技能 | 仓库位置 | 职责 |
| --- | --- | --- |
| dialogue-video-skill | `.agents/skills/dialogue-video-skill/` | 主制片、固定主持人与音色、分镜、独立QA及交付 |
| openmontage | `.agents/skills/openmontage/` | 原生剪辑、混音、渲染与阶段检查点 |

1. 两个技能目录建议同级放置。保留资产、脚本、参考文档，以及 OpenMontage 完整源码、AGPL-3.0许可证和版权声明。旧 `dialogue-man` 是原环境版本，不是新技能的依赖。`zizai-creation` 是作者自用的直接接口调用技能，不是本示例的依赖，公开使用者无需安装。
2. 安装 Python 3.10+ 和 FFmpeg，确保 `python`、`ffmpeg`、`ffprobe` 可执行。在智能体使用的 Python 环境运行 `python -m pip install -r <技能目录>/openmontage/requirements.txt`。只有选择 Remotion/HyperFrames 渲染时，才按 OpenMontage 原文档配置对应 Node 依赖。
3. 启动 videofree 网关，给主制片配置 MCP 地址 `http://<网关电脑IP>:8765/mcp`，例如 `http://192.168.50.8:8765/mcp`。同机可用 `127.0.0.1`，其他设备不能用它。客户端配置格式见 [技能安装说明](.agents/skills/dialogue-video-skill/references/install.md)及当前智能体的 HTTP MCP 配置文档。媒体生成由主制片直接调用 MCP，不经过其他技能。
4. 刷新智能体的技能发现，让它读取 dialogue-video-skill 的安装指南。支持子智能体的宿主应只给主制片媒体工具，QA只读必要材料；缺乏独立审核能力时需明确说明，不冒充独立QA通过。
5. 验证固定资产：`python <技能目录>/dialogue-video-skill/scripts/validate.py assets <技能目录>/dialogue-video-skill`。生产输出放到技能目录外的独立工作目录；首次运行按 [OpenMontage接入说明](.agents/skills/dialogue-video-skill/references/openmontage.md) 执行 preflight 和 init。

示例请求：

> 使用 dialogue-video-skill，制作一段机器人和青年男人对话讲解的视频，主题是“为什么天空是蓝色的”，60秒、9:16、保留对白、不加字幕。先给出方案和预计生成次数，我确认后再生成。

全自动制作需明确授权内容、成本或次数上限、审核策略和二采选择。技能不是一键启动的独立服务；需要宿主智能体、可用媒体后端及真实视听审核能力。安装新技能不会启动额外网关，也不需要旧 Hermes 窄MCP服务。

### 支持项目

您的支持，是我持续前进的动力。如果 videofree 对您的创作有所帮助，欢迎自愿支持项目的持续维护与分享。

<img src="frontend/public/contact/wechat-support.jpg" alt="微信自愿支持收款码" width="220" />
