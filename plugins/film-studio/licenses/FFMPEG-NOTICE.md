# FFmpeg 外部依赖与许可说明

剪辑插件使用用户自行安装的 `ffmpeg` 与 `ffprobe`，通过系统 `PATH` 启动。VideoFree Studio
仓库、源码包和插件目录不提交、下载或再分发 FFmpeg 二进制文件。

## 来源

- FFmpeg 官方网站：https://ffmpeg.org/
- 下载入口：https://ffmpeg.org/download.html
- Windows 构建入口以 FFmpeg 官方下载页列出的提供方为准。
- Linux 建议使用发行版软件仓库；macOS 可使用 Homebrew。

准确安装步骤和验证命令见插件根目录的 [INSTALL.md](../INSTALL.md)。插件不固定某个
FFmpeg 构建版本，但所用构建必须提供 `ffmpeg`、`ffprobe`、H.264/AAC 编解码及常用
滤镜（包括 `xfade`、`acrossfade`、`overlay`、`adelay` 和 `ass`）。

## 许可边界

FFmpeg 的实际许可证取决于用户选择的构建及其编译选项，可能为 LGPL 或 GPL。用户应
阅读所安装构建附带的许可证，并自行确认分发和商业使用条件。VideoFree Studio 仅以独立进程
方式调用这两个命令；VideoFree Studio 自身许可证不覆盖或替代 FFmpeg 的许可证。
