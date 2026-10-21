---
title: FAQ
lead: The most common installation, connection, and generation problems. Check here first — and if you are still stuck, ask in the community.
order: 8
---

## It says nodes are missing. What now?

A node package is not installed or its import failed. Check the ComfyUI startup log for `IMPORT FAILED`, fix it, and restart ComfyUI. Each plugin's required node packages are listed in [Install Plugins](/en/guide/plugin-install/).

## It says a model is missing, but I downloaded it.

Check two things: the **filename** and the **subfolder** must match the plugin's `INSTALL.md` exactly. Wrong folder, renamed file, or a partially downloaded repository all produce "missing model". The safest fix is letting an agent verify every entry against `INSTALL.md`.

## The gateway is online but jobs keep failing.

Gateway health only means VideoFree Studio runs — it does not mean ComfyUI is connected. Open workspace Settings and confirm the ComfyUI address uses ComfyUI's own port (commonly `8189` or `8188`), not VideoFree Studio's `8765`.

## Out of VRAM (OOM)?

Lower resolution and duration first, then consider smaller quantizations (int8 / fp8). Not every model and size runs on every GPU. H3 and LTX video requirements vary a lot by quantization tier.

## Other LAN machines cannot reach the workspace or MCP?

- Use the machine's real LAN IP, never `0.0.0.0`.
- Check the gateway bind address (`MEDIA_GATEWAY_HOST`) and open the Windows firewall.
- When exposing to the LAN, set `MEDIA_GATEWAY_TOKEN`; never expose an unauthenticated gateway to the public internet.

## SageAttention fails to install, or ComfyUI stops starting after installing it?

SageAttention must be installed into **the Python environment ComfyUI actually uses**, with versions matching Python, PyTorch, CUDA, and your GPU. Do not blindly upgrade PyTorch/CUDA. Send the agent the prompt from [Installation step 3](/en/guide/install/) and let it check versions before acting.

## The editor says ffmpeg cannot be found?

Install `ffmpeg` and `ffprobe` yourself and put them on the system `PATH`. Both `ffmpeg -version` and `ffprobe -version` must succeed in the same terminal environment that launches VideoFree Studio. Restart VideoFree Studio afterwards.

## Old jobs error out after I updated a plugin?

Jobs and collaborations store a plugin version snapshot; old jobs refuse to run once plugin files change. Drain or cancel related jobs before updating a plugin, then restart the gateway.

## Where do models and media live on disk?

Project media defaults to `data/projects/`; you can point to another directory in Settings → Basic. After switching, only the new directory is read and written — old files are not migrated. System settings, projects, and job records live in `data/media_gateway.db`.
