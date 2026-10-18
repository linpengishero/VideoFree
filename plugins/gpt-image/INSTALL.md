# GPT-Image 安装说明

## 模型与 ComfyUI 节点

无。本插件通过 GrisAI 云端接口运行，不使用本地 ComfyUI 工作流。

## 外部服务

在插件设置中配置 GrisAI API Key；默认服务地址为 [https://grsai.dakka.com.cn](https://grsai.dakka.com.cn)，可按服务方提供的兼容地址修改。Key 不随插件分发，也不能写进 `plugin.json`。

插件当前声明 `gpt-image-2` 与 `gpt-image-2.5`。这两项是云端服务模型 ID，没有本地模型文件或 ComfyUI 安装目录。确认账户具有相应权限后，用最小图片请求验证；服务计费、内容政策和模型许可由 GrisAI/对应上游服务决定。
