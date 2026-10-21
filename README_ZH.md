# VideoFree Studio

[English](README.md) · **中文**

当前版本：`2.0.0`

官方网站：[videofreestudio.com](https://videofreestudio.com)

**把零散、复杂的本地 AI 工作流，变成普通用户能使用、开发者能分发、Agent 能稳定调用的完整创作能力。**

VideoFree Studio 是一个面向本地 AI 视频创作的工作台、能力网关和插件平台。它以 ComfyUI 作为底层生成引擎，但不要求用户直接面对复杂的节点连线、模型路径和零散工作流。VideoFree Studio 将模型、工作流、参数界面、提示词技能和配套资源封装成可安装插件，再用统一的项目、分类、素材和任务系统组织整个创作过程。

普通用户可以在工作台中完成创作，外部 Agent 可以通过 MCP 或 HTTP API 使用同一套插件能力、项目数据和本地素材。

## 为什么需要 VideoFree Studio

### 从云端转向本地，首先面对的是混乱

云端产品通常已经替用户选择好了模型、参数和操作流程。转到本地后，用户面对的却是琳琅满目的模型、散落在网络各处的工作流，以及难以理解的 ComfyUI 节点和连线。

即使下载了工作流，也经常遇到缺少节点、模型路径不一致、参数含义不清楚和版本不兼容。用户需要先成为“工作流维护者”，才能开始真正的内容创作。

VideoFree Studio 不替代 ComfyUI，而是在它之上建立一层稳定的产品能力。开发者可以将已经调试好的工作流制作成插件，把工作流、输入规则、模型参数、专用编译逻辑和依赖说明放在一起。用户安装插件后，可以像使用普通创作软件一样选择能力，而不必理解内部节点。

### 降低不同模型的提示词学习成本

图片、视频、语音和音乐模型拥有不同的提示词格式、参考素材要求和参数限制。同一句自然语言需求，交给不同模型往往需要完全不同的写法。

每个 VideoFree Studio 插件可以携带自己的模型知识和协作技能。用户只需要用大白话描述想要的画面、动作、对白或音乐，智能协作就能根据当前模型和生成模式进行追问、检查素材关系，并整理为模型真正需要的执行稿。增加新模型时，它的特殊规则仍留在插件中，不会继续堆进主程序。

### 解决本地创作的文件和素材混乱

ComfyUI 擅长执行工作流，但不是完整的视频项目管理工具。生成的图片、视频、声音和中间文件容易混在输出目录中，剧本、文案、提示词和参考素材又散落在文档、聊天记录与文件夹里。

VideoFree Studio 使用“项目—分类—素材”组织创作：项目可以对应一部影片或一个系列，分类可以对应某一集、章节或镜头组；最终素材自动归档，任务记录保留输入来源、生成参数、能力和重新生成关系，人物、场景与声音等项目资产可以反复使用。剧本、分镜、制作进度等业务数据还可以由项目插件管理，并始终跟随当前项目或分类上下文。

### 让 Agent 稳定使用 ComfyUI 工作流

直接让 Agent 操作原始 ComfyUI 工作流并不稳定。Agent 必须理解节点编号、输入连接、模型文件和工作流版本，任何细节变化都可能导致调用失败。

VideoFree Studio 把工作流转换为带固定能力 ID、输入 Schema 和执行契约的接口。Agent 只需要发现能力、上传素材、提交参数并查询任务；平台负责工作流选择、参数校验、素材绑定、排队、恢复、错误报告和结果归档。工作台、MCP 与 HTTP API 共用同一个能力目录和任务服务，不是三套生成实现。

### 让工作流成为可以安装和复用的产品

一个插件可以同时包含 ComfyUI 工作流、模型与能力声明、参数界面、专用编译器、智能协作技能、预设资源、后处理动作和独立应用页面。同一个插件既能供用户在工作台中操作，也能通过 MCP 或 HTTP API 提供给 Agent。

插件开发入口：

- [插件开发指南](plugins/PLUGIN_DEVELOPMENT.md)
- [插件协议](docs/plugin-protocol.md)
- [VideoFree Studio 插件开发 Skill](.agents/skills/videofree-plugin-development/SKILL.md)

纯声明式生成插件安装时只需复制完整插件目录并重启网关。带独立 UI 的应用插件应在插件目录内构建和分发自己的 `ui/dist/`，无需修改 VideoFree Studio 主前端。

## 许可证与第三方边界

项目来源标识、发布留证、商业交付记录与贡献者授权流程见[来源与留证规范](docs/source-provenance.md#中文说明)，版权和仓库来源见 [NOTICE](NOTICE)。

VideoFree Studio 自有源代码按 [GNU AGPL-3.0](LICENSE) 发布，可先阅读[中文许可证说明](LICENSE_ZH.md)。需要闭源集成、企业部署、白标、技术支持或定制开发时，可查看[商业授权说明](COMMERCIAL_LICENSE_ZH.md)。

ComfyUI、社区节点、模型、LoRA、字体、FFmpeg 及其他资源不属于 VideoFree Studio 的统一授权范围，请遵守各自许可证。剪辑功能属于 `plugins/film-studio/` 应用插件，要求用户自行安装 FFmpeg/ffprobe 并加入系统 `PATH`，仓库不分发其二进制文件；详见[剪辑插件安装说明](plugins/film-studio/INSTALL.md)。`examples/skills/openmontage/` 是独立的自动化视频制作技能，不是剪辑插件的运行依赖。详见[第三方组件说明](THIRD_PARTY_NOTICES_ZH.md)。

## AI军火库与知识星球

- **AI军火库 · 前沿 AI 技术网站**：[laobanclaw.top](https://laobanclaw.top/)，关注前沿 AI 技术与实际应用。
- **知识星球**：分享各类 AI 视频自动化流水线，以及 AI、智能体与大模型专业知识。点击二维码可放大查看。
- **VideoFree Studio 微信交流群**：交流本地模型、插件开发、工作流封装和 AI 视频创作。二维码失效时可前往 [laobanclaw.top](https://laobanclaw.top/) 获取最新入口。

<table>
  <tr>
    <td align="center"><strong>知识星球</strong><br /><a href="frontend/public/contact/zsxq-qr.png"><img src="frontend/public/contact/zsxq-qr.png" alt="知识星球二维码" width="220" /></a></td>
    <td align="center"><strong>VideoFree Studio 微信交流群</strong><br /><a href="https://laobanclaw.top/videofree/qrcode.jpg"><img src="https://laobanclaw.top/videofree/qrcode.jpg" alt="VideoFree Studio 微信交流群二维码" width="220" /></a></td>
  </tr>
</table>

## 配套 ComfyUI 整合包

我用夸克网盘给你分享了「配套Comfyui整合包」，点击链接或复制整段内容，打开「夸克APP」即可获取。

```text
/~2ca93bYCBE~:/
链接：https://pan.quark.cn/s/2d145a999169
```

下载入口：[配套 ComfyUI 整合包](https://pan.quark.cn/s/2d145a999169)

整合包包含项目配套所需的模型和插件。请保留模型文件名、模型子目录和插件目录结构，避免工作流找不到对应资源。插件安装或更新后，需要重启 ComfyUI 才会加载。

**重要：配套 ComfyUI 必须安装 SageAttention，否则使用依赖该注意力实现的工作流会报错。** SageAttention 要安装到 ComfyUI 实际使用的 Python 环境，不能只安装到系统 Python；其版本需与 Python、PyTorch、CUDA 和显卡环境匹配。安装失败时先检查对应版本的安装说明，不要盲目升级整合包中的 PyTorch。SageAttention 是运行依赖，不是模型文件，也不等同于注意力补丁节点。

## 启动

Windows 解压完整发布包后，直接双击 `videofree.bat`。程序使用随包附带的 Python，启动成功后会自动打开创作页面，不要求用户安装 Python 或 Node.js。Linux 源码部署先安装 `requirements.txt`，执行 `chmod +x videofree.sh`，再运行 `./videofree.sh`。

剪辑插件要求系统 `PATH` 中可以执行 `ffmpeg` 和 `ffprobe`，仓库不提交或自动下载这两个程序。请从 [FFmpeg 官方下载页](https://ffmpeg.org/download.html)安装，并在启动 VideoFree Studio 的同一环境执行 `ffmpeg -version`、`ffprobe -version` 验证；各平台步骤见[剪辑插件安装说明](plugins/film-studio/INSTALL.md)。

首次使用请在网页设置中填写 ComfyUI 网关地址。项目资源默认保存在 `data/projects/`，也可在“设置 → 基础设置”指定其他本地目录；修改后只读写新目录，不迁移或继续读取旧目录。需要通过环境变量覆盖配置时，可将 `.env.example` 复制为 `.env`。

`videofree.bat` 与 `videofree.sh` 都会自动读取根目录的 `.env`；直接启动 Python 时，终端本身不会自动读取该文件。网关默认监听 `0.0.0.0`，可通过本机或局域网访问；对局域网开放时建议设置 `MEDIA_GATEWAY_TOKEN`。如需限制为仅本机访问，将 `MEDIA_GATEWAY_HOST` 设置为 `127.0.0.1`。ComfyUI 地址通过 `COMFYUI_URL` 配置。

## 基本配置教程

网页图文教程：启动 VideoFree Studio 后，可在首页进入安装部署、MCP、全自动技能包和插件开发四个教程。对应地址为 `?guide=install`、`?guide=mcp`、`?guide=skills` 和 `?guide=plugin`；局域网使用时将 `127.0.0.1` 替换为网关电脑的实际 IP。教程包含工作台示例、可交给智能体的安装指令和插件开发 Skill。

### 1. 准备并启动 ComfyUI

解压配套 ComfyUI 整合包，确认模型、插件及 SageAttention 已安装到对应环境。先启动 ComfyUI，等待控制台显示访问地址，并检查是否有插件导入失败信息。用浏览器打开该地址，确认 ComfyUI 正常运行。

默认连接地址为 `http://127.0.0.1:8189`。如果 ComfyUI 实际监听其他端口，请使用控制台显示的地址，不要照抄默认端口。

### 2. 启动 videofree 并配置连接

Windows 双击 `videofree.bat`；Linux 运行 `./videofree.sh`。本机访问 `http://127.0.0.1:8765/`，进入工作台的设置，填写实际的 ComfyUI 地址并保存。ComfyUI 与网关在同一台电脑时使用 `127.0.0.1`；不同电脑时使用 ComfyUI 所在电脑的局域网 IP，并确保其监听地址和防火墙允许访问。

可选：复制 `.env.example` 为 `.env`，按实际情况修改以下内容。修改后重新启动网关：

```dotenv
COMFYUI_URL=http://127.0.0.1:8189
MEDIA_GATEWAY_HOST=0.0.0.0
MEDIA_GATEWAY_PORT=8765
MEDIA_GATEWAY_TOKEN=
```

局域网设备访问 `http://网关电脑的局域网IP:8765/`，不要使用 `0.0.0.0` 或另一台设备的 `localhost` 作为浏览器地址。访问失败时检查 Windows 防火墙是否允许网关端口；不要把免认证服务直接暴露到公网。

### 3. 配置 AI 与云端能力

需要导演协作、H3 描述词转换等能力时，在“设置 → LLM 服务”配置系统公共模型，插件通过框架接口调用且不能读取该密钥。需要 GPT-Image 云端生图时，在“设置 → 插件配置 → GPT-Image”填写 GrisAI 参数；值保存在 `plugins/gpt-image/.env`。仅使用本地生成能力时不必配置。插件 `.env` 已被 Git 忽略，不要将密钥提交到公开仓库。

### 4. 创建项目并生成素材

在工作台创建项目，填写名称、简介和内容概要，然后进入项目提交生成。系统自动创建项目目录，并按 `images`、`videos`、`audio`、`music` 分类保存最终素材，无需手动指定资源目录或同步 ComfyUI 输出文件。

未自定义资源目录时，生成素材位于 `data/projects/`。内置音色样本随声音插件分发，例如 `plugins/cosyvoice3/samples/`，不依赖框架缓存；系统设置、项目与任务记录保存在 `data/media_gateway.db`，插件专属配置位于各插件的 `.env`。不要删除数据库或插件自带的音色资源。

### 5. 常见问题

- **找不到节点**：确认对应插件已安装、依赖安装成功，并已重启 ComfyUI；查看启动日志中的导入错误。
- **找不到模型或 LoRA**：检查文件名、模型类型及子目录是否与工作流一致；仅下载模型但放错目录同样无法使用。
- **SageAttention 导入失败**：检查是否安装在 ComfyUI 自带 Python 中，以及依赖版本是否匹配；以 ComfyUI 启动日志为准。
- **视频保存失败**：H3 保存依赖 VideoHelperSuite 和支持 NVIDIA NVENC 的 FFmpeg，详见下方 API 说明。
- **显存不足**：先降低分辨率或时长；不同模型和后处理阶段的显存需求不同，配套整合包不保证所有尺寸都能在任意显卡运行。
- **网关在线但无法生成**：网关与 ComfyUI 是两个进程，分别检查连接地址、ComfyUI 状态及任务报错。

如需让外部 AI 调用，使用 `examples/skills/videofree-creation` 中的技能与客户端，并将网关地址配置为调用设备可访问的地址。接口及可用能力以 `/api/v2/capabilities` 返回为准。

## API

在设置页配置“网关访问令牌”，默认留空免认证；工作台、HTTP API 和 MCP 共用此令牌。API/MCP 客户端通过 `X-API-Token` 请求头发送令牌。浏览器首次连接时输入令牌，验证后使用 HttpOnly、SameSite=Strict Cookie 访问接口与媒体，有效期七天；更换令牌会使旧会话失效，当前保存设置的浏览器自动续接。不要将令牌放入 URL；跨机器使用时建议通过 HTTPS 访问。

`MEDIA_GATEWAY_TOKEN` 仅作为尚未保存网关令牌设置时的启动缺省值，设置页保存的值优先（包括显式清空）。生成前通过 `/v1/uploads` 流式上传素材，再将返回的 `upload:<id>` 放入生成请求。任务可通过 `/v1/jobs/{id}` 查询，通过 `/v1/jobs/{id}/cancel` 取消。取消会移除尚在 ComfyUI 队列中的提示词；运行中的计算采用协作取消并丢弃结果，不调用会影响其他客户端的全局中断。执行器退出前禁止删除任务、分类或项目；开始归档后不再接受取消。

每个插件独立存放在 `plugins/<plugin-id>/`，工作流、处理器和注册清单 `plugin.json` 均放在插件内。网关只调用插件已注册的能力；请求中的 `{{prompt}}` 会在提交 ComfyUI 前替换。不再读取旧的 `workflows/registry.json`。

H3 生成与二采的最终保存链路在提交前统一编译为 VideoHelperSuite `VHS_VideoCombine`，使用独立 FFmpeg 的 `video/nvenc_h264-mp4` 编码（H.264、15 Mbps、原有音频）。ComfyUI 需安装 VideoHelperSuite，且其 FFmpeg 支持 NVIDIA NVENC；不会回退到已出现原生崩溃的 PyAV 保存链路。仓库工作流模板的输出节点编号、采样参数和 latent 保存逻辑保持不变，任务快照记录实际提交的编码节点。

队列默认最多等待 20 个任务，可通过 `MAX_QUEUE_SIZE` 调整。排队任务和 ComfyUI `prompt_id` 保存在 SQLite 中，网关重启后会继续排队或追踪已经提交的任务。

智能协作默认不限制本地模型响应时间。需要设置上限时，可通过 `AGENT_TIMEOUT_SECONDS` 指定秒数；保持为 `0` 时，连接未断开且网关仍在运行就会继续等待。

### AI API v2

面向 AI 的稳定接口位于 `/api/v2`。先调用 `/api/v2/capabilities` 发现当前可用能力，再通过 `/api/v2/uploads` 上传素材，最后向 `/api/v2/generations` 提交能力 ID、素材角色、比例和命名分辨率。该接口不会暴露 ComfyUI 节点、工作流文件或模型路径。

声音、音乐和图片预设分别通过 `/api/v2/voices`、`/api/v2/music/*` 和 `/api/v2/image/styles` 查询。AI 调用 Skill 位于 `examples/skills/videofree-creation`，其中包含无第三方依赖的命令行客户端。

支持 MCP 的其他 AI 可使用 [MCP 安装与使用指南](examples/skills/videofree-creation/references/mcp-install.md)，该文件可单独转发。局域网入口为 `http://127.0.0.1:8765/mcp`，随网关启动，不需要额外服务；原有 REST 技能保留。

### 双主持人视频技能

[dialogue-video-skill](examples/skills/dialogue-video-skill/SKILL.md) 与独立的 [OpenMontage](examples/skills/openmontage/SKILL.md) 整包安装：主制片使用媒体 MCP，宿主原生子智能体负责剧本、分镜和独立 QA；OpenMontage 原生工具负责剪辑、混音、渲染和阶段检查点，不另写合成器。包含固定角色及声音参考、合同校验和原生接入桥；不依赖 Hermes，原 `dialogue-man` 保留。OpenMontage 完整源码、AGPL-3.0许可证及版权声明保持随包分发，集成增量见其文档。安装和权限配置见 [安装说明](examples/skills/dialogue-video-skill/references/install.md)。长镜允许按实际可用能力二采，不再使用八秒禁用规则。

### 安装示例技能

仓库提供双主持人对话视频制作示例，只需安装以下两个完整目录到智能体支持的技能目录，再给主制片配置 videofree MCP，不要只复制 `SKILL.md`：

| 技能 | 仓库位置 | 职责 |
| --- | --- | --- |
| dialogue-video-skill | `examples/skills/dialogue-video-skill/` | 主制片、固定主持人与音色、分镜、独立QA及交付 |
| openmontage | `examples/skills/openmontage/` | 原生剪辑、混音、渲染与阶段检查点 |

1. 两个技能目录建议同级放置。保留资产、脚本、参考文档，以及 OpenMontage 完整源码、AGPL-3.0许可证和版权声明。旧 `dialogue-man` 是原环境版本，不是新技能的依赖。`videofree-creation` 是作者自用的直接接口调用技能，不是本示例的依赖，公开使用者无需安装。
2. 安装 Python 3.10+ 和 FFmpeg，确保 `python`、`ffmpeg`、`ffprobe` 可执行。在智能体使用的 Python 环境运行 `python -m pip install -r <技能目录>/openmontage/requirements.txt`。只有选择 Remotion/HyperFrames 渲染时，才按 OpenMontage 原文档配置对应 Node 依赖。
3. 启动 videofree 网关，给主制片配置 MCP 地址 `http://<网关电脑IP>:8765/mcp`，例如 `http://192.168.50.8:8765/mcp`。同机可用 `127.0.0.1`，其他设备不能用它。客户端配置格式见 [技能安装说明](examples/skills/dialogue-video-skill/references/install.md)及当前智能体的 HTTP MCP 配置文档。媒体生成由主制片直接调用 MCP，不经过其他技能。
4. 刷新智能体的技能发现，让它读取 dialogue-video-skill 的安装指南。支持子智能体的宿主应只给主制片媒体工具，QA只读必要材料；缺乏独立审核能力时需明确说明，不冒充独立QA通过。
5. 验证固定资产：`python <技能目录>/dialogue-video-skill/scripts/validate.py assets <技能目录>/dialogue-video-skill`。生产输出放到技能目录外的独立工作目录；首次运行按 [OpenMontage接入说明](examples/skills/dialogue-video-skill/references/openmontage.md) 执行 preflight 和 init。

示例请求：

> 使用 dialogue-video-skill，制作一段机器人和青年男人对话讲解的视频，主题是“为什么天空是蓝色的”，60秒、9:16、保留对白、不加字幕。先给出方案和预计生成次数，我确认后再生成。

全自动制作需明确授权内容、成本或次数上限、审核策略和二采选择。技能不是一键启动的独立服务；需要宿主智能体、可用媒体后端及真实视听审核能力。安装新技能不会启动额外网关，也不需要旧 Hermes 窄MCP服务。

### 支持项目

您的支持，是我持续前进的动力。如果 videofree 对您的创作有所帮助，欢迎自愿支持项目的持续维护与分享。

<img src="frontend/public/contact/wechat-support.jpg" alt="微信自愿支持收款码" width="220" />
