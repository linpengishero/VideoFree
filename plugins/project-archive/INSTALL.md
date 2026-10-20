# 创作档案安装说明

## 依赖

无模型、ComfyUI 节点或外部服务依赖。插件使用 VideoFree 的项目分类上下文、插件文档存储和通用动作/MCP 入口。

## 使用

复制插件目录后重启网关。AI 创建的项目和人工项目都可以使用。“全部素材”展示项目级记录；只有切换到已命名分类时才展示本集信息。默认分类、全部素材和项目资产不作为本集上下文。

概览、故事设定、本集信息和剧本定稿均为无标题纯文本。分镜默认按镜头列表管理；单个镜头内可分别记录画面、关联剧本片段、生图/视频/声音描述、素材与生成结果。提示词作为独立记录保存，并使用镜头或可选镜头组 ID 关联；镜头组没有固定数量上限。

媒体文件不复制到插件目录。文档中只保存 `library_path`、资产 ID、任务 ID 和其他稳定引用。

详细数据格式、版本管理和 MCP 调用方式见 [README.md](README.md)。

## Installation (English)

No model, ComfyUI custom node, or external service is required. Install this plugin
directory and restart the gateway. Both manual and AI projects are supported.
Project overview and category records are isolated; project common settings can
be read from a category. Records and revision snapshots use the platform's
plugin-scoped document storage. See [README.md](README.md) for the action contract.
