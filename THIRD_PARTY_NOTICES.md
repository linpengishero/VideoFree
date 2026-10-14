# 第三方组件与资源说明

videofree 是媒体网关，负责调用用户配置的本地 ComfyUI、ComfyUI 节点、模型和
其他媒体服务。以下内容不因随项目目录提供而自动取得 videofree 的统一授权。

## ComfyUI 与社区节点

ComfyUI 及其社区节点由各自项目作者维护，许可证和版权归各自权利人所有。使用
或分发配套插件时，应同时遵守对应仓库、插件目录和发布包中的许可证文件。

## 模型、LoRA、字体和媒体资源

模型、LoRA、字体、示例素材及其他媒体资源可能具有独立的使用范围、署名要求或
商业限制。请在下载、分发或用于商业项目之前，核对来源页面和随附许可证。

## OpenMontage

OpenMontage 位于 `.agents/skills/openmontage/`，是可选安装的独立技能和剪辑工具，
不是 videofree 网关的核心运行依赖。OpenMontage 目录内的 `LICENSE`、版权声明和
其他来源说明必须与其源码一起保留。使用 OpenMontage 时，以其目录中的许可证和
第三方声明为准。

## 其他依赖

Python、JavaScript、FFmpeg 及其他依赖的许可证以依赖项目自身发布的许可证为准。
依赖清单不代表 videofree 对这些项目拥有版权或再授权权。
