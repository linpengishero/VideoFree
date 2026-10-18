# 内置 FFmpeg 构建来源与许可说明

成片插件自带 FFmpeg 与 FFprobe，合成时只调用插件目录内的这两个程序，
不查找系统 `PATH`，也不要求用户另外安装。当前只随包发布 Windows x64 构建，
其它平台在未补包前会直接报错，不会静默改用系统版本。

## 随包文件

| 插件内路径 | 说明 |
| --- | --- |
| `binaries/windows-x64/ffmpeg.exe` | 合成、拼接、混音 |
| `binaries/windows-x64/ffprobe.exe` | 素材与成片校验 |
| `licenses/LICENSE.txt` | GNU GPL v3 全文（构建包内 `LICENSE`） |
| `licenses/README.txt` | 构建包自带的构建配置与版本说明 |

## 版本与来源

- 构建：`9.0.2-essentials_build-www.gyan.dev`（64 位静态 Windows release-essentials 构建）
- 发布者：Gyan Doshi，https://www.gyan.dev/ffmpeg/builds/
- 官方镜像：https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2
- FFmpeg 源码提交：https://github.com/FFmpeg/FFmpeg/commit/946fcce07b
- 构建配置：见 `licenses/README.txt`（含 `--enable-gpl --enable-version3 --enable-static --enable-libx264` 等）
- 运行要求：Windows 10 或更高版本

## 校验值

下载包与包内文件均按下列值核对后才纳入插件，任何一项不符都不得发布：

| 文件 | 字节数 | SHA-256 |
| --- | --- | --- |
| `ffmpeg-9.0.2-essentials_build.zip` | 114,768,076 | `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba` |
| `ffmpeg-9.0.2-essentials_build.7z` | 35,430,500 | `4705843ccaaf54257c16ad90f3e952ece33c17df964ecf7bfdbb0f49c7171077` |
| `bin/ffmpeg.exe` | 105,423,872 | `3256173f3f8bffd7df12227c68adf68025edb1832273a9530688a7bb1ed8edec` |
| `bin/ffprobe.exe` | 105,221,120 | `f0d36ecbbdd3bcfac3efa078c96c7271c2e68b3810595552ac3b7f17e9a65c52` |
| `LICENSE`（GPL v3 全文） | 35,147 | `8ceb4b9ee5adedde47b31e975c1d90c73ad27b6b165a1dcd80c7c545eb65b903` |
| `README.txt` | 41,577 | `0342de6bb39dd421cbec2c00d89ad274b640d75ad3f2cab09ffd647ce2d8f949` |

ZIP 的 SHA-256 与 GitHub Release 资产官方 digest 一致；7z 的 SHA-256 与 gyan.dev
公布的 `ffmpeg-release-essentials.7z.sha256` 一致。两个包来自同一官方发布，
插件内的 exe 取自 ZIP（本机解压器不支持 7z 的 BCJ2 过滤器）。

## 许可

FFmpeg 及其构建以 GNU GPL v3 发布，全文见 `licenses/LICENSE.txt`。这两个程序作为
**独立、未修改的第三方可执行文件**随插件分发，插件只通过参数数组启动进程并与之交换
文件，不与本项目代码链接或合并，因此本仓库其余代码的许可（见根目录 `LICENSE`、
`COMMERCIAL_LICENSE.md`）不受影响。再分发时必须同时附带 GPL v3 文本与来源说明，
本目录即为该义务的实现。

## 更换或补其他平台

1. 从 https://www.gyan.dev/ffmpeg/builds/ （Windows）或 FFmpeg 官方/发行版渠道获取对应平台构建。
2. 核对发布方公布的校验值，确认是未修改的官方构建。
3. 把可执行文件放入 `binaries/<平台目录>/`，平台目录名由 `render.platform_tag()` 生成，
   例如 `windows-x64`、`linux-x64`、`macos-arm64`。
4. 更新本文件的版本、字节数与 SHA-256，并把新文件加入 `plugin.json` 的 `assets`，
   发布自检会校验它们存在且不越出插件目录。
