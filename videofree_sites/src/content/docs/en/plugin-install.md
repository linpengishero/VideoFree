---
title: Install Plugins
lead: "Copy a folder, restart the gateway — the plugin is installed. You don't fetch models one by one either: hand the plugin folder to an AI agent and let it install everything per INSTALL.md. This guide covers installation, model download, and verification, with a quick-reference table for every demo plugin."
order: 2
---

<div class="diagram">
  <div class="dtitle">install flow</div>
  <div class="dflow">
    <div class="dbox"><b>Plugin folder</b><small>plugin.json + INSTALL.md</small></div>
    <div class="darr">→</div>
    <div class="dbox"><b>Copy into plugins/</b><small>the whole folder</small></div>
    <div class="darr">→</div>
    <div class="dbox"><b>Restart the gateway</b><small>scan &amp; register</small></div>
    <div class="darr">→</div>
    <div class="dbox hot"><b>Workspace + MCP</b><small>capability appears automatically</small></div>
  </div>
</div>

## <span class="no">1</span>Where plugins come from

- **Bundled demo plugins**: the image, video, speech, music, and post-production plugins under `plugins/` are demos showing what one plugin can package.
- **Plugins shared by others**: any complete plugin folder installs the same way.
- **Your own plugin**: see [Build Plugins](/en/guide/plugin-dev/).

## <span class="no">2</span>Install: copy the folder, restart the gateway

```text
VideoFree Studio/
└─ plugins/
   └─ your-plugin/     ← copy the whole folder in; plugin.json is the only registration entry
```

After restarting the gateway, the capability appears in the workspace UI and the MCP capability list — no integration code needed. Uninstall = remove the folder and restart.

Even this step is a one-liner for your agent: "Copy [plugin folder] into VideoFree Studio's `plugins/` directory, then restart the gateway."

::note
Only install plugins from sources you trust. Plugins are trusted local code, not a security sandbox.
::

## <span class="no">3</span>Models and nodes: let your agent install per INSTALL.md

Plugins never download models by themselves — and you don't have to fetch them one by one either. Each plugin's `INSTALL.md` declares the exact model filenames, official download URLs, and target directories. Hand the plugin folder to an agent that can operate your computer (Claude Code, Codex, OpenCode, …) and let it read the file and install everything.

Send this prompt, replacing the paths with your own:

> I want to enable a VideoFree Studio plugin: [plugin folder path, e.g. C:\VideoFree Studio\plugins\ltx-2.5]. First read INSTALL.md in that folder and list every model file and ComfyUI node package it requires. My ComfyUI root is: [your ComfyUI path]. Check which files already exist (exact filename and subfolder), download the missing ones from the official URLs declared in INSTALL.md, and place them in the declared directories. Do not rename files or flatten directories. When everything is in place, tell me to restart ComfyUI and list what you downloaded and what you skipped. If a license gate or download failure blocks you, stop and explain.

The Chinese version of this prompt lives on the [插件安装](/guide/plugin-install/) page.

::note
Models carry their own licenses. When a repository requires login, accepting terms, or payment, your agent should stop and let you complete that step yourself — never bypass license restrictions.
::

## <span class="no">4</span>Verify the installation

1. **Restart ComfyUI** — the startup log must show no `IMPORT FAILED`.
2. Run ComfyUI Manager's missing-node check against the node packages the plugin declares.
3. Submit one minimal job in VideoFree Studio (a low-resolution image or a 480P clip). Media out means the plugin is installed.

If you download models manually, three rules: **filenames and subfolders must match `INSTALL.md` exactly** (workflows load files by exact name; renaming or flattening causes "missing model" errors); **download only from the declared official sources**; **restart ComfyUI, then verify**. If VRAM is tight, prefer int8 / fp8 quantized files, lower resolution and duration first, and raise quality only after the pipeline works.

## Appendix: what each plugin needs

The table below is a quick index; **the plugin's own `INSTALL.md` is always the authoritative list**.

| Plugin | Type | Model sources | ComfyUI nodes |
| --- | --- | --- | --- |
| [Krea2](https://github.com/linpengishero/VideoFreeStudio/tree/main/plugins/krea2) (image) | Local | [Comfy-Org/Krea-2](https://huggingface.co/Comfy-Org/Krea-2): `krea2_turbo_fp8_scaled`, `qwen3vl_4b_fp8_scaled`, `qwen_image_vae`; identity views also need `krea2_identity_edit_v1_2` ([comfyui-krea2edit](https://github.com/lbouaraba/comfyui-krea2edit)); upscale also needs [OmniSR_X4_DIV2K](https://openmodeldb.info/models/4x-OmniSR) | comfyui-krea2edit, ComfyUI-Easy-Use, rgthree-comfy, ComfyUI_essentials, ComfyUI_UltimateSDUpscale |
| [Qwen Image 2.1](https://github.com/linpengishero/VideoFreeStudio/tree/main/plugins/qwen-image) (image) | Local | [QwenLM/Qwen-Image-2.1](https://github.com/QwenLM/Qwen-Image-2.1): `qwen_image_2.1_int8_convrot` (into `models/diffusion_models/Qwen/`), `qwen3vl_8b_int8_convrot`, `qwen_image_2.1_vae_bf16` | Up-to-date ComfyUI core |
| [GPT-Image](https://github.com/linpengishero/VideoFreeStudio/tree/main/plugins/gpt-image) (cloud image) | Cloud | No local models; configure a GrisAI API key in plugin settings | None |
| [MiniMax H3](https://github.com/linpengishero/VideoFreeStudio/tree/main/plugins/minimax-h3) (video) | Local | [MiniMax-AI/MiniMax-H3](https://github.com/MiniMax-AI/MiniMax-H3) official project: fl2va / ref2va backbones, `qwen3vl_32b_minimax_h3_nvfp4_awq`, video & audio VAEs, turbo LoRAs, latent upscaler; the LTX refine stage also needs the full LTX-2.5 set | Up-to-date ComfyUI core; LTX refine needs [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo) |
| [LTX 2.5](https://github.com/linpengishero/VideoFreeStudio/tree/main/plugins/ltx-2.5) (video) | Local | [Lightricks/LTX-2.5](https://huggingface.co/Lightricks/LTX-2.5): int8 transformer, Gemma text encoder, video/audio VAEs, spatial upscaler, multi-reference LoRA | [ComfyUI-LTXVideo](https://github.com/Lightricks/ComfyUI-LTXVideo), VideoHelperSuite, KJNodes |
| [CosyVoice3](https://github.com/linpengishero/VideoFreeStudio/tree/main/plugins/cosyvoice3) (speech) | Local | [Fun-CosyVoice3-0.5B](https://huggingface.co/FunAudioLLM/Fun-CosyVoice3-0.5B), auto-downloaded by the node on first use | [ComfyUI_Fill-Nodes](https://github.com/filliptm/ComfyUI_Fill-Nodes) |
| [Qwen3-TTS](https://github.com/linpengishero/VideoFreeStudio/tree/main/plugins/qwen-tts) (speech) | Local | Qwen3-TTS 1.7B repos (VoiceDesign / Base / CustomVoice), auto-downloaded by `Qwen3Loader` | [ComfyUI-Qwen3-TTS](https://github.com/DarioFT/ComfyUI-Qwen3-TTS) |
| [ACE-Step 1.5](https://github.com/linpengishero/VideoFreeStudio/tree/main/plugins/ace-step) (music) | Local | [ACE-Step/ACE-Step-v1.5](https://huggingface.co/ACE-Step/ACE-Step-v1.5): turbo, two text encoders, VAE | Up-to-date ComfyUI core |
| [MiniMax Music 3](https://github.com/linpengishero/VideoFreeStudio/tree/main/plugins/minimax-music) (music) | Local | [MiniMax-AI/MiniMax-Music3](https://github.com/MiniMax-AI/MiniMax-Music3) official project: DiT, text encoder, DAV | Up-to-date ComfyUI core |
| [Video post-processing](https://github.com/linpengishero/VideoFreeStudio/tree/main/plugins/video-post) (upscale/interpolation) | Local | LTX-2.5 upscale set (into `models/*/LTX-2.5/` subfolders), deblur LoRA, RIFE (auto-downloaded by the node) | ComfyUI-Frame-Interpolation, VideoHelperSuite, KJNodes, Custom-Scripts, Easy-Use, LTXVideo |
| [Editor film-studio](https://github.com/linpengishero/VideoFreeStudio/tree/main/plugins/film-studio) (final cut) | Local | Auto subtitles use [whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) (auto-downloaded by the node); system needs `ffmpeg` and `ffprobe` | [ComfyUI-Whisper](https://github.com/yuvraj108c/ComfyUI-Whisper), rgthree-comfy |
| [Image split](https://github.com/linpengishero/VideoFreeStudio/tree/main/plugins/image-split) / [Project archive](https://github.com/linpengishero/VideoFreeStudio/tree/main/plugins/project-archive) / [AI progress](https://github.com/linpengishero/VideoFreeStudio/tree/main/plugins/ai-project-progress) | Tool | No models, no node dependencies | None |
