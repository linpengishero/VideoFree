# 局域网 MCP 接入

可单独转发给其他 AI 的安装与使用文件见 [mcp-install.md](mcp-install.md)。

videofree 网关同时提供一个面向局域网 AI 的 MCP JSON-RPC 入口。原有
`zizai_api.py` REST 调用仍然保留。MCP 的生成、语音和后处理委托同一套
AI API v2，不直接调用 ComfyUI。

## 连接地址

本机局域网地址为 `192.168.50.8`，网关默认端口为 `8765`：

```text
http://192.168.50.8:8765/mcp
```

请求需要携带网关配置的 token：

```http
X-API-Token: <MEDIA_GATEWAY_TOKEN>
```

如果网关没有设置 `MEDIA_GATEWAY_TOKEN`，局域网内无需 token，但生产或共享
网络中不建议关闭认证。

## MCP 客户端配置

支持自定义 Streamable HTTP / JSON-RPC MCP 服务的客户端，可填写：

```json
{
  "name": "videofree 媒体网关",
  "url": "http://192.168.50.8:8765/mcp",
  "headers": {
    "X-API-Token": "<MEDIA_GATEWAY_TOKEN>"
  }
}
```

客户端必须能够访问 `192.168.50.8:8765`。如果连接失败，先确认网关使用
`0.0.0.0` 监听、Windows 防火墙允许 8765 端口，以及客户端与本机位于同一
局域网。

## 工具使用顺序

先使用项目工具：

1. `list_projects`：列出项目。
2. `create_project`：创建并返回项目 ID，不自动切换；后续生成显式携带 `project_id`，或用 `set_current_project` 切换工作区项目。
3. `get_current_project`：确认后续任务的归属。未选择时使用“未归档项目”。

项目选定后使用创作工具：

1. `list_capabilities`：发现能力，不要猜模型、模式、分辨率或参考图数量。
2. `get_capability`：读取指定能力的输入限制与协作模式。
3. `create_director_collaboration`：把普通描述交给导演管线。默认只产出
   协作结果，不自动提交视频。
4. `get_collaboration`：查询状态、问题、进度和中间结果。
5. `send_collaboration_message`：回答追问或补充素材职责、动作和结尾要求。
6. `get_final_prompt`：读取最终英文执行稿和中文确认稿，供用户审核。

已经得到用户明确确认后，可以继续使用：

7. `confirm_collaboration`：按协作版本确认并提交实际生成任务。
8. `upload_reference`：上传 Base64 图片、视频或音频并取得 `upload_id`。
9. `submit_generation`：直接提交已经准备好的生成请求。
10. `get_job`：查询任务状态。
11. `wait_job`：等待任务更新；超时不会取消任务。
12. `get_job_artifacts`：获取最终媒体产物的网关下载 URL。
13. `cancel_job`：取消仍在排队或运行中的任务。

项目上下文按 `workspace_id` 隔离，选择一次后，后续导演
协作、直接生成和确认生成都自动归入该项目。任务提交后会固定项目归属，二采、
重生成和后处理继承父任务项目。最终文件进入网关自己的
`data/projects/<项目>/images|videos|audio|music`，不依赖 ComfyUI 输出目录同步。

六宫格图片分割使用 `image.split_6` 能力，输入一张 3×2 宫格图，完成后会
返回六个独立图片产物；四宫格仍使用 `image.split`。

推荐状态流程：

```text
list_capabilities
  -> get_capability
  -> create_director_collaboration
  -> get_collaboration
  -> send_collaboration_message（仅在 needs_input 时）
  -> get_final_prompt
```

`awaiting_confirmation` 表示提示词已经完成但等待用户审核，不代表生成失败。
`confirm_collaboration` 和 `submit_generation` 会产生实际生成任务，只能在用户
明确确认后调用。生成完成后，`get_job_artifacts` 返回的 `url` 可以由其它 AI
下载或交给用户；任务长时间运行时重复调用 `wait_job` 即可。

## 参考素材

可用 `upload_reference` 上传 Base64 素材；大文件也可通过 REST 上传。
外部 AI 不能传入网关本机任意路径。使用 REST 技能客户端上传时：

```powershell
python scripts/zizai_api.py upload C:\media\reference.png
```

然后在 `create_director_collaboration` 的 `references` 中传入对应素材对象，
例如：

```json
[
  {
    "kind": "image",
    "name": "character.png",
    "media_type": "image/png",
    "data_url": "upload:<upload_id>"
  }
]
```

详细的素材角色和能力限制以 `get_capability` 返回值为准。

## 安全边界

- 不向外部 AI 暴露 ComfyUI 地址、节点 ID、工作流文件或模型路径。
- 不把 `C:\`、`E:\` 等本机路径发送给 MCP 客户端。
- token 应只保存在客户端的安全配置中，不写进公开提示词或项目代码。
- 不提供删除项目、删除资源、写入或删除任何预设的工具；预设由工作台管理。
- 生成与后处理须符合用户的创作授权；不自动确认导演协作稿。

## 与最小 AI 接口同步的工具

- `submit_generation`：参数沿用 `/api/v2/generations`，支持 `prompt_processing=direct|compile|director`、`project_id`、`session_id`、`answer`、`settings` 与 `inputs`。返回生成任务或协作会话；`needs_input` 时用同一工具携带 `session_id`、`answer` 回答，不另起直提任务。
- `list_voices`：只读查询音色描述及 `ready`，只有就绪音色才可使用。
- `speech_preset`：`preset_id`、`text`、可选 `speed`。
- `speech_describe`：`voice_description`、`text`、可选 `speed`。
- `speech_clone`：`reference_upload_id`、`text`、可选 `speed`；先用 `upload_reference` 上传音频。
- 三种语音操作直接返回任务，不应进入协作确认流程。异常会话返回需交人工，不允许自动确认。`speed` 为 0.5–2.0；普通中文约4–5字/秒，估算时长为字数除以 `4.5 × speed`，不保证精确时长。
- `get_health`、`list_image_styles`、`list_music_styles`、`list_music_singers`、`list_music_voice_textures`：状态与预设只读发现。
- `get_job_actions`、`run_job_action`：查询并执行现有任务支持的后处理。
- `regenerate_job`：保留原任务并生成新版本；修改双语执行稿时同时传中英文。
- `get_job` / `wait_job`：失败时返回 `error_info`，含错误码、缺失项、处理建议与原始错误。

生成任务携带 `project_id` 可显式隔离项目；语音专用接口沿用当前工作区项目，
可先用 `set_current_project` 设置对应 `workspace_id`，随后语音工具携带同一工作区 ID。
接口不支持的额外字段不会被解释成模型或工作流参数。
