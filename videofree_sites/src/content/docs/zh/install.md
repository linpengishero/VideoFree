---
title: 安装部署
lead: AI 时代最快的安装方式：把一段提示词交给能操作你电脑的智能体，它负责下载、启动和配置。想自己动手也没问题——下面每一步都对应智能体替你做的事。
order: 1
---

## <span class="no">1</span>让 AI 智能体安装部署（推荐）

把下面这段话发给能操作你电脑的智能体（豆包、Claude Code、Codex、Trae 等），填上你的路径，它会完成其余全部步骤：

> 帮我在这台电脑上安装部署 VideoFree Studio：1) 从 https://gitee.com/heroofgod_admin/videofreestudio 下载最新 Release 解压到 [安装目录]（或克隆源码并安装 requirements.txt）；2) 按 README.md 启动：Windows 双击 videofree.bat，Linux 执行 ./videofree.sh；3) 打开 http://127.0.0.1:8765 确认工作台就绪；4) 我的 ComfyUI 目录是【填路径】，检查它是否在运行、告诉我它的地址，没运行就按这个包的方式启动它；5) 给 ComfyUI 实际使用的 Python 环境安装 SageAttention（先核对显卡、Python、PyTorch、CUDA 版本，不要擅自升级）；6) 对照我想用的插件，告诉我还缺哪些模型和节点包，列出官方下载地址。遇到需要登录、接受条款或付费的下载，停下来交给我处理。

智能体会替你完成：

- 下载发布包或克隆源码，安装依赖并启动网关；
- 检查 ComfyUI 运行状态和地址，把 SageAttention 装进正确的 Python 环境；
- 对照各插件 `INSTALL.md`，报告缺失的模型和节点包；
- 遇到许可登录、付费下载时停下来，交给你本人处理。

装完自己核对三件事：

1. `http://127.0.0.1:8765` 能打开工作台；
2. 设置里已填好 ComfyUI 地址并保存；
3. 跑一个最小任务（低分辨率图片或短片）能出片。

::note
想自己动手、或想核对智能体每一步做了什么，继续往下看——每一节都对应总提示词里的一件事。
::

## <span class="no">2</span>准备 ComfyUI、模型和插件

VideoFree Studio 插件已经保存了工作流、参数界面和模型规则；ComfyUI 端只需要具备该插件声明的模型与节点。不要再把网上来源不明的工作流混进 VideoFree Studio 插件目录。

准备模型有两条路：

- **使用配套整合包（推荐中文用户）**：打开[配套 ComfyUI 整合包](https://pan.quark.cn/s/2d145a999169)，或把完整口令 `/~2ca93bYCBE~:/` 复制到夸克 APP。里面提供项目需要的 ComfyUI、模型和插件。
- **让智能体按插件说明下载（推荐英文用户与已有 ComfyUI 的用户）**：每个 VideoFree Studio 插件的 `INSTALL.md` 都写明了所需模型的准确文件名、下载地址和安装目录。把插件目录交给能操作你电脑的智能体，让它读取 `INSTALL.md` 并逐项下载。详见[插件安装](/guide/plugin-install/)。

**已经有 ComfyUI**：把模型放到你自己的 `ComfyUI/models/`，节点包放到 `ComfyUI/custom_nodes/`。按声明的目录结构放，不要把所有文件倒进一个文件夹，也不要随便改模型名。

**还没有 ComfyUI**：如果整合包提供完整安装包，下载并解压到空间充足的目录，按包内说明启动；如果只有模型和插件，先从 [ComfyUI 官网](https://www.comfy.org/download) 安装，再复制配套文件。

```text
你的 ComfyUI/
├─ models/        ← 模型，保留各自子目录
└─ custom_nodes/  ← 插件，每个插件一个完整文件夹
```

## <span class="no">3</span>更新 ComfyUI，装好节点依赖

先备份配置，再用你安装包自带的更新工具把 ComfyUI 更新到最新稳定版本。如果用了 Manager，也检查配套节点包是否需要更新。不同安装包的更新按钮不一样，找不到就让智能体先检查安装方式。

复制节点包不等于安装完成，有些节点包还需要安装 Python 依赖。让智能体在 **ComfyUI 自己的 Python 环境** 里处理。更新后重启，看启动日志有没有「导入失败」或「IMPORT FAILED」。

## <span class="no">4</span>让智能体安装 SageAttention

配套工作流需要 SageAttention。它不是模型，也不是复制一个节点文件夹就能装好的东西。如果你用了第 1 步的总提示词，这一步智能体已经做过；这里适合单独补装或重做。把下面这段话发给能操作你电脑的智能体，最后填上你的 ComfyUI 路径：

> 帮我给 ComfyUI 安装 SageAttention。先找到 ComfyUI 实际使用的 Python，检查显卡、Python、PyTorch 和 CUDA 版本，再选择兼容的安装方式。不要装到系统 Python，也不要未经确认升级 PyTorch 或 CUDA。安装后用这个 Python 验证能导入 sageattention。遇到不兼容先告诉我原因和方案。我的 ComfyUI 路径是：【填你的路径】。

::note
不建议照抄网上不明版本的安装命令。版本不匹配可能让原来能跑的 ComfyUI 也启动不了。
::

## <span class="no">5</span>启动 ComfyUI，记下它的地址

等启动完成，控制台会显示类似 `http://127.0.0.1:8189` 的地址。先在浏览器打开，能看到 ComfyUI 页面才算启动成功。端口以你自己的日志为准，也可能是 8188 或别的数字。

不要关闭启动窗口，关了服务也就停了。以后使用 VideoFree Studio 时，ComfyUI 也要保持运行。

## <span class="no">6</span>启动 VideoFree Studio，填连接地址

Windows 解压完整 VideoFree Studio 发布包后双击 `videofree.bat`；Linux 源码部署先安装 `requirements.txt`，再运行 `chmod +x videofree.sh && ./videofree.sh`。打开首页，点右上角「进入工作台」，先创建并进入一个项目，再点左侧工具栏的齿轮设置按钮。

使用剪辑插件还需自行安装 FFmpeg，并确保启动 VideoFree Studio 的环境可以执行 `ffmpeg -version` 和 `ffprobe -version`。VideoFree Studio 不随仓库分发这两个程序。

在 **ComfyUI / 网关地址** 填上刚才记下的 ComfyUI 地址，然后保存。两边在同一台电脑就用 `127.0.0.1`；不在同一台电脑，要填 ComfyUI 那台电脑的局域网 IP。

![设置界面示例：顶部填写 ComfyUI 地址，底部保存](/contact/guide-settings.png)

::note
ComfyUI 地址和 VideoFree Studio 地址不是一回事。8189 是这里的 ComfyUI 示例端口，8765 是 VideoFree Studio 默认端口；不要把 8765 填进 ComfyUI 接口地址。
::

## <span class="no">7</span>补齐 AI 配置，创建项目试一下

需要 H3 描述词转换或导演协作，就在设置里填 AI 服务地址、模型名和 API Key。需要 GPT-Image 云端生图，再填 GrisAI API Key；只用本地生图，不需要这个云端密钥。

回到项目列表，创建项目，再进项目生成。先用低分辨率、短视频或一张图片试跑，确认连接和依赖正常，再做长视频。素材会自动存到 `data/projects/` 对应项目，不用手动同步 ComfyUI 的输出目录。

![空项目列表示例：先创建项目，再进入项目生成](/contact/guide-projects.png)

## 遇到问题，先看这几项

- **缺节点**：对应节点包没装好，或依赖导入失败。检查 ComfyUI 启动日志，修好后重启。
- **缺模型**：检查文件名和子目录，不能只看「下载过了」。每个插件需要哪些模型，见[插件安装](/guide/plugin-install/)。
- **网关在线但不能生成**：只说明 VideoFree Studio 在运行，不代表 ComfyUI 已连上。
- **显存不足**：先减分辨率和时长。不是所有模型、尺寸都能在任意显卡运行。
- **局域网打不开**：用电脑的实际 IP，不要用 `0.0.0.0`。跨电脑连接还要检查监听地址和 Windows 防火墙，别把免认证服务暴露到公网。
