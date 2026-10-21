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

OpenMontage 位于 `examples/skills/openmontage/`，是随仓库提供的独立智能体技能和剪辑工具，
不是 VideoFree Studio 网关或 `film-studio` 插件的运行依赖。它按自己的 AGPL-3.0 许可证独立授权；
VideoFree Studio 的商业授权不免除其许可证义务。使用或分发 OpenMontage 时，必须保留其目录内的
`LICENSE`、版权声明和其他来源说明，并以该目录中的许可证和第三方声明为准。

## 其他依赖

Python、JavaScript、FFmpeg 及其他依赖的许可证以依赖项目自身发布的许可证为准。
依赖清单不代表 videofree 对这些项目拥有版权或再授权权。
剪辑插件通过系统 `PATH` 调用用户自行安装的 FFmpeg/ffprobe；本仓库不提交或分发其
二进制文件。安装来源和验证方式见 `plugins/film-studio/INSTALL.md`。
