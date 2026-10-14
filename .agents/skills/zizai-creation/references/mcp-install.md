# videofree MCP 安装与使用指南

这份文件可单独发送给其他 AI 或 MCP 客户端管理员。MCP 与 REST 使用同一个 videofree 网关，原有 `zizai-creation` REST 调用能力保留。

## 1. 接入地址与前提

| 项目 | 配置 |
| --- | --- |
| 服务名称 | videofree |
| 网关地址 | `http://192.168.50.8:8765` |
| MCP 地址 | `http://192.168.50.8:8765/mcp` |
| 连接方式 | HTTP POST JSON-RPC，支持 JSON 响应的 Streamable HTTP 客户端 |
| 当前认证 | 无需 token，无需设置认证请求头 |

网关电脑启动 `start_gateway.cmd` 即提供 MCP，不需要另开 MCP 进程。AI 所在电脑不必安装 ComfyUI、模型或本项目的 Python 环境，只需能访问网关。

网关需要监听 `0.0.0.0`，防火墙允许 TCP 8765。同一局域网的其他电脑不要使用 `127.0.0.1`、`localhost` 或 `0.0.0.0` 作为连接地址。IP 改变时同步更新客户端配置。不要把当前免认证服务直接暴露到公网。

## 2. 在 AI 客户端中安装连接

在客户端的 MCP 服务设置中新增远程 HTTP 服务，名称填 `videofree`，URL 填上述 MCP 地址，认证留空，保存后连接并刷新工具列表。

对于支持以下 `mcpServers` 格式的客户端，可以使用：

```json
{
  "mcpServers": {
    "videofree": {
      "type": "http",
      "url": "http://192.168.50.8:8765/mcp"
    }
  }
}
```

不同客户端字段不同，此配置不是通用标准。若客户端要求 `streamable-http` 类型，请按其配置说明替换 `type`；若仅支持 `command`/`args` 或旧版 SSE，不能直接套用此配置。

当前实现接受 POST JSON-RPC 并返回 JSON；GET `/mcp` 是信息页面，不是 SSE 事件流。不支持 JSON 响应的客户端需要兼容适配，不能把地址改成 `/sse`。成功连接后应发现 29 个工具，具体参数以实时 `tools/list` 的 `inputSchema` 为准。

只有管理员将来设置了 `MEDIA_GATEWAY_TOKEN` 时，才增加 `X-API-Token` 请求头，其值由管理员提供。

## 3. 可直接交给 AI 的使用规则

1. 先调用 `get_health`、`list_capabilities`、`get_capability`，根据实际返回选择能力、模式、素材角色、比例和分辨率，不猜参数。
2. 项目隔离：调用 `create_project`，保存返回的项目 ID；后续 `submit_generation` 显式携带 `project_id`。创建项目不会自动切换项目。不带项目 ID 时沿用当前工作区项目，未选项目时使用“未归档项目”。这属于资源归属隔离，不是访问权限隔离。
3. 参考素材先用 `upload_reference` 上传，再把返回的 `upload_id` 放入 `inputs`。不要传网关电脑本机路径。
4. 统一生成入口为 `submit_generation`。`prompt_processing=direct` 直接生成；`compile` 检查并忠实转换描述词；`director` 进行完整导演协作。不要为了绕过编译或追问另起直提任务。
5. 返回 `job_id` 后查询任务。返回协作会话时查询该会话；`needs_input` 时向同一个 `submit_generation` 传 `session_id`、`answer` 回答问题。
6. `awaiting_confirmation` 时展示方案，取得用户明确批准后再用 `confirm_collaboration`，传会话 ID 和当前 `revision`。不要自动确认。`get_final_prompt` 可读取双语确认稿。
7. 用 `get_job` 或 `wait_job` 等待；完成后调用 `get_job_artifacts` 获取所有文件。单次等待最多 120 秒，等待超时不代表失败，也不会取消任务。不要因此重复提交。
8. 二采和其他后处理先调用 `get_job_actions`，只执行返回的 `action_id`，使用 `run_job_action` 后继续等待新任务。不要猜 H3 二采是否可用。`regenerate_job` 创建新版本，不删除原任务；修改双语执行稿时同时传匹配的中英文。
9. 不修改或删除预设，不删除项目或资源，不直接调用 ComfyUI，不传节点 ID、工作流路径或模型文件路径。取消任务需符合用户授权。

### 项目与素材示例

以下是工具参数，不是完整 JSON-RPC 信封。示例中的占位 ID 必须替换成实际返回值。

```json
{
  "name": "AI短片项目",
  "description": "独立保存这次短片的素材",
  "content_summary": "山间武侠短片",
  "workspace_id": "video-agent-a"
}
```

上例传给 `create_project`。上传图像时调用 `upload_reference`：

```json
{
  "filename": "character.png",
  "media_type": "image/png",
  "data_base64": "<文件字节的Base64，不带data:前缀>"
}
```

调用 `submit_generation` 的参考输入形状：

```json
{
  "capability_id": "<get_capability核实的能力ID>",
  "project_id": "<创建项目返回的ID>",
  "workspace_id": "video-agent-a",
  "prompt": "<用户的完整创作需求>",
  "prompt_processing": "compile",
  "inputs": [
    {"type": "image", "upload_id": "<上传返回的ID>", "role": "reference"}
  ],
  "settings": {
    "ratio": "<能力支持的比例>",
    "resolution": "<能力支持的命名分辨率>",
    "duration": 5,
    "variant": "<能力支持的模式>"
  },
  "idempotency_key": "<本次逻辑提交的唯一标识>"
}
```

`role` 按能力调整；纯文生时 `inputs` 可为空。重试同一次提交复用同一幂等键，新创作换新键。Base64 会放大数据量，大文件可沿用 REST 上传，再在 MCP 中使用返回的 ID，无须把文件内容塞入模型对话。

## 4. 声音生成

| 工具 | 必要参数 | 服务端模型 |
| --- | --- | --- |
| `list_voices` | 无 | 查询预设 ID、描述及 `ready` |
| `speech_preset` | `preset_id`、`text` | CosyVoice3 |
| `speech_describe` | `voice_description`、`text` | Qwen3-TTS |
| `speech_clone` | `reference_upload_id`、`text` | CosyVoice3 |

三种生成都支持可选 `speed`，范围 0.5–2.0，默认 1.0。中文正常约 4–5 字/秒，可用 `字数 / (4.5 × speed)` 粗估时长，不能保证逐秒精确。预设必须 `ready=true`；克隆先上传获得授权的参考音频，参考长度不超过 30 秒，建议 3–10 秒。

语音专用工具没有 `project_id` 参数。先用 `set_current_project` 携带项目 ID 和自己的 `workspace_id`，随后语音工具携带同一 `workspace_id`。不同 AI 使用不同工作区 ID，避免相互切换项目；默认工作区是 `mcp-default`。

语音工具应直接返回生成任务，不应产生协作会话。没有任务 ID 或意外返回确认会话时报告原始响应并交人工处理，禁止兜底自动确认。

## 5. 工具清单

| 用途 | 工具 |
| --- | --- |
| 项目，4个 | `list_projects`、`create_project`、`get_current_project`、`set_current_project` |
| 服务与能力，3个 | `get_health`、`list_capabilities`、`get_capability` |
| 只读预设，5个 | `list_voices`、`list_image_styles`、`list_music_styles`、`list_music_singers`、`list_music_voice_textures` |
| 上传与生成，2个 | `upload_reference`、`submit_generation` |
| 语音，3个 | `speech_preset`、`speech_describe`、`speech_clone` |
| 协作，5个 | `create_director_collaboration`、`get_collaboration`、`send_collaboration_message`、`get_final_prompt`、`confirm_collaboration` |
| 任务与结果，4个 | `get_job`、`wait_job`、`get_job_artifacts`、`cancel_job` |
| 后处理与重生成，3个 | `get_job_actions`、`run_job_action`、`regenerate_job` |

新请求优先使用统一生成入口；`create_director_collaboration` 和 `send_collaboration_message` 为已有协作客户端保留，不必两条路径混用。

## 6. 获取生成结果

工具正常响应的 `content` 中包含 `type=text` 项，其 `text` 是 JSON 字符串，需要解析后读取任务或产物字段。JSON-RPC 返回 `error` 时不能当作成功提交。

用 `get_job_artifacts` 返回的 URL 下载图片、视频、音频等所有产物。若 URL 是相对路径，以 `http://192.168.50.8:8765` 拼接，不要拼客户端的 localhost，也不要把网关磁盘路径当下载地址。完成任务的最终文件由网关归档到项目资源库，AI 不需要同步 ComfyUI 输出目录。

## 7. 连接诊断

在 AI 客户端所在电脑执行以下 PowerShell 命令，仅检查工具发现，不提交生成：

```powershell
$url = 'http://192.168.50.8:8765/mcp'
$headers = @{ Accept = 'application/json, text/event-stream' }
$body = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"connection-check","version":"1.0"}}}'
Invoke-RestMethod -Uri $url -Method Post -Headers $headers -ContentType 'application/json' -Body $body
$body = '{"jsonrpc":"2.0","method":"notifications/initialized"}'
Invoke-RestMethod -Uri $url -Method Post -Headers $headers -ContentType 'application/json' -Body $body
$body = '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
$result = Invoke-RestMethod -Uri $url -Method Post -Headers $headers -ContentType 'application/json' -Body $body
$result.result.tools | Select-Object name
```

- 连接拒绝或超时：检查网关启动状态、监听地址、IP、防火墙及容器到局域网的网络访问。
- HTTP 401：管理员可能启用了 token，按实际配置添加认证头。
- 浏览器能打开但 MCP 连不上：检查客户端是否支持 POST JSON 响应，而非仅支持旧版 SSE。
- 少于预期工具：确认网关已更新并重启，再让客户端重新连接、刷新 schema；不要重启正在执行任务的服务。
- 网关在线但本地生成失败：网关与 ComfyUI 是不同服务，查看 `get_health` 和任务错误。云端生成不需要客户端安装 ComfyUI。
- 任务失败：保留 `error_info` 中错误码、缺失项、处理建议与原始错误，向用户报告具体缺失节点或模型，不盲目反复提交。

REST 技能依旧可用；远程 REST 客户端设置 `ZIZAI_API_URL=http://192.168.50.8:8765`，不要把 `/mcp` 当作 REST API 根地址。
