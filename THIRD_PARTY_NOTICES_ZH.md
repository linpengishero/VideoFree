# 第三方组件与资源说明

[English](THIRD_PARTY_NOTICES.md) · **中文**

videofree 是媒体网关，负责调用用户配置的本地 ComfyUI、ComfyUI 节点、模型和
其他媒体服务。以下内容不因随项目目录提供而自动取得 videofree 的统一授权。

## ComfyUI 与社区节点

ComfyUI 及其社区节点由各自项目作者维护，许可证和版权归各自权利人所有。使用
或分发配套插件时，应同时遵守对应仓库、插件目录和发布包中的许可证文件。

## 模型、LoRA、字体和媒体资源

模型、LoRA、字体、示例素材及其他媒体资源可能具有独立的使用范围、署名要求或
商业限制。请在下载、分发或用于商业项目之前，核对来源页面和随附许可证。

## OpenMontage

OpenMontage 位于 `.agents/skills/openmontage/`，可独立作为技能使用，也是网关可选
基础合成功能的运行依赖；网关启动和其他生成功能不依赖它。其 AGPL-3.0 许可仍独立适用，
videofree 的商业授权不免除第三方许可义务。OpenMontage 目录内的 `LICENSE`、版权声明和
其他来源说明必须与其源码一起保留。使用 OpenMontage 时，以其目录中的许可证和
第三方声明为准。

## 其他依赖

Python、JavaScript、FFmpeg 及其他依赖的许可证以依赖项目自身发布的许可证为准。
依赖清单不代表 videofree 对这些项目拥有版权或再授权权。
剪辑插件通过系统 `PATH` 调用用户自行安装的 FFmpeg/ffprobe；本仓库不提交或分发其
二进制文件。安装来源和验证方式见 `plugins/film-studio/INSTALL.md`。

## Krea 2 提示词扩写模板

`plugins/krea2/collaboration/skills/upstream/krea-2/expansion.txt` 来自 Krea AI 的
Krea 2 官方仓库 `docs/expansion.txt`，按 Apache License 2.0 使用。原始来源与许可链接
记录在同目录 `SOURCE.md`；其版权归 Krea AI 及上游贡献者所有。
