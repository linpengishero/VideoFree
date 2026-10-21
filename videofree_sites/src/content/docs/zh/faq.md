---
title: 常见问题
lead: 安装、连接和生成中最常遇到的问题。先按这里排查，仍解决不了欢迎到社区提问。
order: 8
---

## 提示缺节点怎么办？

对应节点包没装好，或依赖导入失败。检查 ComfyUI 启动日志有没有「导入失败 / IMPORT FAILED」，修好后重启 ComfyUI。各插件需要哪些节点包，见[插件安装](/guide/plugin-install/)。

## 提示缺模型，但我明明下载过了？

检查两点：**文件名**和**所在子目录**必须与插件 `INSTALL.md` 声明完全一致。把模型放错目录、改了文件名、或只下载了仓库里的部分文件，都会报缺模型。最稳妥的办法是让智能体按 `INSTALL.md` 逐项核对。

## 网关在线，但任务一直失败？

网关在线只说明 VideoFree Studio 在运行，不代表 ComfyUI 已连上。打开工作台设置，确认 ComfyUI 地址是 ComfyUI 自己的端口（常见 `8189` 或 `8188`），不是 VideoFree Studio 的 `8765`。

## 显存不足（OOM）怎么办？

先降低分辨率和时长，再考虑换更小的量化文件（int8 / fp8）。不是所有模型和尺寸都能在任意显卡运行。H3、LTX 等视频模型显存需求随量化档位变化很大。

## 局域网其他电脑打不开工作台或 MCP？

- 使用电脑的实际局域网 IP，不要填 `0.0.0.0`。
- 检查网关监听地址（`MEDIA_GATEWAY_HOST`）和 Windows 防火墙放行。
- 对局域网开放时建议设置 `MEDIA_GATEWAY_TOKEN`，不要把免认证服务暴露到公网。

## SageAttention 装不上或装完 ComfyUI 起不来？

SageAttention 必须装进 **ComfyUI 实际使用的 Python 环境**，版本要与 Python、PyTorch、CUDA 和显卡匹配。不要盲目升级 PyTorch/CUDA。把[安装部署第 3 步](/guide/install/)的提示词发给智能体，让它先检查版本再动手。

## 剪辑插件提示找不到 ffmpeg？

`ffmpeg` 和 `ffprobe` 需要自行安装并加入系统 `PATH`，在启动 VideoFree Studio 的同一终端环境执行 `ffmpeg -version` 和 `ffprobe -version` 都能成功才算装好。安装后重启 VideoFree Studio。

## 更新插件后旧任务报错？

任务与协作保存了插件版本快照，插件文件变化后旧任务会拒绝继续。更新插件前先把相关任务跑完或取消，更新后重启网关。

## 模型和素材占的磁盘在哪？

项目素材默认保存在 `data/projects/`，可在「设置 → 基础设置」指定其他目录；修改后只读写新目录，不迁移旧目录。系统设置、项目和任务记录在 `data/media_gateway.db`。
