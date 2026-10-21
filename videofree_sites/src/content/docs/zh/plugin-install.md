---
title: 插件安装
lead: 复制目录、重启网关，插件就装好了；模型和节点不用你逐个手动下载——把插件目录交给 AI 智能体，让它按 INSTALL.md 自己完成。这篇讲安装、模型下载与验证，附全部演示插件的模型需求速查表。
order: 2
---

<div class="diagram">
  <div class="dtitle">install flow</div>
  <div class="dflow">
    <div class="dbox"><b>插件目录</b><small>plugin.json + INSTALL.md</small></div>
    <div class="darr">→</div>
    <div class="dbox"><b>复制到 plugins/</b><small>整个目录</small></div>
    <div class="darr">→</div>
    <div class="dbox"><b>重启网关</b><small>扫描并注册</small></div>
    <div class="darr">→</div>
    <div class="dbox hot"><b>工作台 + MCP</b><small>能力自动出现</small></div>
  </div>
</div>

## <span class="no">1</span>插件从哪来

- **仓库自带的演示插件**：`plugins/` 目录里的图像、视频、声音、音乐、后期等插件都是演示，用来展示一个插件能封装什么。
- **别人分享的插件**：拿到一个完整插件目录即可，安装方式完全相同。
- **你自己开发的插件**：见[插件开发](/guide/plugin-dev/)。

## <span class="no">2</span>安装：复制目录，重启网关

```text
VideoFree Studio/
└─ plugins/
   └─ 你的插件/     ← 整个目录复制进来，plugin.json 是唯一注册入口
```

重启网关后，工作台界面和 MCP 能力列表里就会出现这个插件——不需要为它写任何接入代码。卸载 = 移除目录再重启。

这一步也可以直接交给智能体：「把【插件目录】整个复制到 VideoFree Studio 的 `plugins/` 目录，然后重启网关。」

::note
只安装来自可信来源的插件。插件是可信本地代码，不是安全沙箱。
::

## <span class="no">3</span>模型和节点：交给智能体按 INSTALL.md 下载

插件不会自动下载模型——你也不需要逐个手动操作。每个插件的 `INSTALL.md` 都写明了所需模型的准确文件名、官方下载地址和安装目录，把插件目录交给能操作你电脑的智能体（Claude Code、Codex、OpenCode 等），让它读取说明、自己下载并放好。中英文智能体客户端都适用。

发送下面这段话，把路径换成你的实际路径：

**中文智能体提示词：**

> 我要启用 VideoFree Studio 插件：【填插件目录路径，例如 D:\VideoFree Studio\plugins\ltx-2.5】。先读取该目录下的 INSTALL.md，列出它需要的全部模型文件和 ComfyUI 节点包。我的 ComfyUI 根目录是：【填你的 ComfyUI 路径】。逐个核对哪些文件已存在（文件名和子目录都必须一致），缺失的从 INSTALL.md 声明的官方地址下载，放到声明的目录，不要改名、不要平铺到其他目录。全部就位后告诉我需要重启 ComfyUI，并列出你下载了什么、跳过了什么。遇到许可限制或下载失败，先停下来告诉我原因。

**English prompt for your agent:**

> I want to enable a VideoFree Studio plugin: [plugin folder path, e.g. C:\VideoFree Studio\plugins\ltx-2.5]. First read INSTALL.md in that folder and list every model file and ComfyUI node package it requires. My ComfyUI root is: [your ComfyUI path]. Check which files already exist (exact filename and subfolder), download the missing ones from the official URLs declared in INSTALL.md, and place them in the declared directories. Do not rename files or flatten directories. When everything is in place, tell me to restart ComfyUI and list what you downloaded and what you skipped. If a license gate or download failure blocks you, stop and explain.

::note
模型都有各自的许可协议。遇到需要登录、同意条款或付费的仓库（如部分官方项目），智能体应停下来让你本人完成，不要绕过许可限制。
::

## <span class="no">4</span>验证装好了

1. **重启 ComfyUI**，启动日志里没有「导入失败 / IMPORT FAILED」。
2. 用 ComfyUI Manager 的缺失节点检查，逐个核对插件声明的节点包。
3. 在 VideoFree Studio 里跑一个最小任务（低分辨率图片或 480P 短片），出片即安装成功。

手动下载模型时记住三条铁律：**文件名和子目录必须与 `INSTALL.md` 完全一致**（工作流按准确文件名加载，改名或平铺都会导致「缺模型」）；**只从声明的官方来源下载**；**装完重启 ComfyUI 再验证**。显存紧张时优先选择 int8 / fp8 量化文件、降低分辨率和时长，先跑通再逐步提高质量。

## 附录：各插件模型需求速查表

下表是快速索引；**准确文件清单以各插件目录内的 `INSTALL.md` 为准**。

| 插件 | 类型 | 模型来源 | ComfyUI 节点 |
| --- | --- | --- | --- |
| [Krea2](https://gitee.com/heroofgod_admin/videofreestudio/tree/master/plugins/krea2)（生图） | 本地 | [Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2)：`krea2_turbo_fp8_scaled`、`qwen3vl_4b_fp8_scaled`、`qwen_image_vae`；人物四视图另需 `krea2_identity_edit_v1_2`（[comfyui-krea2edit](https://github.com/lbouaraba/comfyui-krea2edit)）；超清另需 [OmniSR_X4_DIV2K](https://openmodeldb.info/models/4x-OmniSR) | comfyui-krea2edit、ComfyUI-Easy-Use、rgthree-comfy、ComfyUI_essentials、ComfyUI_UltimateSDUpscale |
| [Qwen Image 2.1](https://gitee.com/heroofgod_admin/videofreestudio/tree/master/plugins/qwen-image)（生图） | 本地 | [QwenLM/Qwen-Image-2.1](https://github.com/QwenLM/Qwen-Image-2.1)：`qwen_image_2.1_int8_convrot`（放 `models/diffusion_models/Qwen/`）、`qwen3vl_8b_int8_convrot`、`qwen_image_2.1_vae_bf16` | 更新 ComfyUI 核心即可 |
| [GPT-Image](https://gitee.com/heroofgod_admin/videofreestudio/tree/master/plugins/gpt-image)（云端生图） | 云端 | 无本地模型；在插件设置中配置 GrisAI API Key | 无 |
| [MiniMax H3](https://gitee.com/heroofgod_admin/videofreestudio/tree/master/plugins/minimax-h3)（视频） | 本地 | [MiniMax-AI/MiniMax-H3](https://github.com/MiniMax-AI/MiniMax-H3) 官方项目：fl2va / ref2va 主干、`qwen3vl_32b_minimax_h3_nvfp4_awq`、视频与音频 VAE、快速档 LoRA、latent 超清；LTX 二采另需 LTX-2.5 全套 | 更新 ComfyUI 核心；LTX 二采需 [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo) |
| [LTX 2.5](https://gitee.com/heroofgod_admin/videofreestudio/tree/master/plugins/ltx-2.5)（视频） | 本地 | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5)：int8 transformer、Gemma 文本编码器、视频/音频 VAE、空间超清、多参考 LoRA | [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo)、VideoHelperSuite、KJNodes |
| [CosyVoice3](https://gitee.com/heroofgod_admin/videofreestudio/tree/master/plugins/cosyvoice3)（语音） | 本地 | [Fun-CosyVoice3-0.5B](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B)，由节点首次使用时自动下载 | [ComfyUI_Fill-Nodes](https://github.com/filliptm/ComfyUI_Fill-Nodes) |
| [Qwen3-TTS](https://gitee.com/heroofgod_admin/videofreestudio/tree/master/plugins/qwen-tts)（语音） | 本地 | Qwen3-TTS 1.7B 三个仓库（VoiceDesign / Base / CustomVoice），由 `Qwen3Loader` 自动下载 | [ComfyUI-Qwen3-TTS](https://github.com/DarioFT/ComfyUI-Qwen3-TTS) |
| [ACE-Step 1.5](https://gitee.com/heroofgod_admin/videofreestudio/tree/master/plugins/ace-step)（音乐） | 本地 | [ACE-Step/ACE-Step-v1.5](https://huggingface.co/ACE-Step/ACE-Step-v1.5)：turbo、两个文本编码器、VAE | 更新 ComfyUI 核心即可 |
| [MiniMax Music 3](https://gitee.com/heroofgod_admin/videofreestudio/tree/master/plugins/minimax-music)（音乐） | 本地 | [MiniMax-AI/MiniMax-Music3](https://github.com/MiniMax-AI/MiniMax-Music3) 官方项目：DiT、文本编码器、DAV | 更新 ComfyUI 核心即可 |
| [视频后期处理](https://gitee.com/heroofgod_admin/videofreestudio/tree/master/plugins/video-post)（超清/插帧） | 本地 | LTX-2.5 超清套件（放 `models/*/LTX-2.5/` 子目录）、去模糊 LoRA、RIFE（节点自动下载） | ComfyUI-Frame-Interpolation、VideoHelperSuite、KJNodes、Custom-Scripts、Easy-Use、LTXVideo |
| [剪辑 film-studio](https://gitee.com/heroofgod_admin/videofreestudio/tree/master/plugins/film-studio)（成片） | 本地 | 自动字幕用 [whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo)（节点自动下载）；系统需 `ffmpeg` 与 `ffprobe` | [ComfyUI-Whisper](https://github.com/yuvraj108c/ComfyUI-Whisper)、rgthree-comfy |
| [图片分割](https://gitee.com/heroofgod_admin/videofreestudio/tree/master/plugins/image-split) / [创作档案](https://gitee.com/heroofgod_admin/videofreestudio/tree/master/plugins/project-archive) / [AI 制作进度](https://gitee.com/heroofgod_admin/videofreestudio/tree/master/plugins/ai-project-progress) | 工具 | 无模型、无节点依赖 | 无 |
