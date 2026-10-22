# VideoFree Studio 局域网 MCP 接入

## 插件能力发现

`list_capabilities` 从已安装插件自动发现能力，支持 `kind` 和 `category` 过滤。
`category` 是插件主分类 ID，区别于项目内素材的 `category_id`。
按返回的 `processing_modes` 选择 `prompt_processing`，自定义值放入 `parameters`。
用同一个 `submit_generation` 调用内置或第三方能力，无需每插件安装专门的 MCP。
H3 的 direct、compile、director 也是普通注册模式；其他插件不必提供同名模式。
等待追问并回答，确认稿必须按原有授权规则显式确认，不得默认自动确认。

`list_public_assets(project_id)` 只读查询项目公共资产，返回资产名称、类型、详细描述和媒体文件URL。
人物可包含角色板（role=character_sheet）和角色声音（role=character_voice，transcript为声音对应文字）；场景/道具为图片；配乐/音效为音频。按能力单独选择文件，下载后走正常上传引用流程，不自动同时附加角色板和声音。
公共资产不是分类，不要把公共资产ID或 `@public` 当 `category_id` 提交；生成结果先归原分类，再由工作台显式归档。

可单独转发给其他 AI 的安装与使用文件见 [mcp-install.md](mcp-install.md)。

videofree 网关同时提供一个面向局域网 AI 的 MCP JSON-RPC 入口。原有
`videofree_api.py` REST 调用仍然保留。MCP 的生成、语音和后处理委托同一套
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
2. `create_project`：创建并返回项目 ID，不自动切换；后续生成显式携带 `project_id`，或用 `set_current_project` 切换当前项目。
3. `get_current_project`：确认后续任务的归属。未选择项目时接口会明确报错，应先创建或选择项目。

需要项目内分类时，使用 `list_project_categories` 并传入 `project_id` 获取分类 ID。
生成、语音和导演任务可携带 `category_id`；省略或传空字符串均归入默认分类。
二采、增强、分割等派生任务继承来源素材当前的分类，不跟随工作台选中的分类。
AI 可通过 `create_project_category` 和 `update_project_category` 创建、改名分类；删除仍在工作台管理。

管理与发现工具还包括 `list_jobs`、`list_library`、`list_collaborations`、
`cancel_collaboration`、`update_project`、`create_public_asset`、
`update_public_asset`、`attach_public_asset_media`、`list_plugins` 和 `list_plugin_presets`。
任务与素材查询支持项目筛选。系统是单用户单安装，不声明或接受 `workspace_id`；并行测试应始终显式传 `project_id`。
`list_plugin_presets(plugin_id)` 通用发现插件选项、音色与相关创作预设，无需为新插件增加专用工具。

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

当前项目由整个网关实例共享；导演协作、直接生成和确认生成应显式传入项目 ID，
避免依赖可被其他调用切换的当前项目。任务提交后会固定项目归属，二采、
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
python scripts/videofree_api.py upload C:\media\reference.png
```

然后在 `create_director_collaboration` 的 `inputs` 中传入上传回执的素材对象，
例如：

```json
[
  {
    "type": "image",
    "upload_id": "<upload_id>",
    "role": "reference"
  }
]
```

详细的素材角色和能力限制以 `get_capability` 返回值为准。

## 安全边界

- 不向外部 AI 暴露 ComfyUI 地址、节点 ID、工作流文件或模型路径。
- 不把 `C:\`、`E:\` 等本机路径发送给 MCP 客户端。
- token 应只保存在客户端的安全配置中，不写进公开提示词或项目代码。
- 不提供删除项目、删除资源、写入或删除任何预设的工具；音色预设归插件管理。
- 生成与后处理须符合用户的创作授权；不自动确认导演协作稿。

## 与最小 AI 接口同步的工具

- `submit_generation`：参数沿用 `/api/v2/generations`，支持 `prompt_processing=direct|compile|director`、`project_id`、`session_id`、`answer`、`settings` 与 `inputs`。返回生成任务或协作会话；`needs_input` 时用同一工具携带 `session_id`、`answer` 回答，不另起直提任务。
- `list_voices`：只读查询音色描述及 `ready`，只有就绪音色才可使用。
- `list_plugin_actions` / `get_plugin_action`：查询插件明确允许 AI 使用的动作及 input_schema；按 scope、source_job_id 筛选。外部素材可按 source_kind 预查；include_unavailable=true 可查看 available/reason。以服务端筛选为准，不自行假设所有视频支持 H3 二采。
- `run_plugin_action`：传 action_id、可选 project_id/source_job_id，以及符合 schema 的 inputs；外部素材上传后传 source_upload_id（与 source_job_id 互斥），可指定 category_id。不为每个插件单独注册工具，提交时会重新校验源素材及辅助文件。
- 声音动作 `speech_preset` 的 inputs 为 preset_id、text、可选 speed；`speech_describe` 为 voice_description、text、可选 speed；`speech_clone` 为 reference_upload_id、text、可选 speed，先用 upload_reference 上传音频。
- 三种语音操作直接返回任务，不应进入协作确认流程。异常会话返回需交人工，不允许自动确认。`speed` 为 0.5–2.0；普通中文约4–5字/秒，估算时长为字数除以 `4.5 × speed`，不保证精确时长。
- `get_health`、`list_image_styles`、`list_music_styles`、`list_music_singers`、`list_music_voice_textures`：状态与预设只读发现。
- 后处理使用相同动作工具，以 scope=resource、source_job_id 查询，只执行实际公布的动作。inputs.parameters 传插件参数；二采通过 inputs.width/height/upscaler 传规格。新任务继承源项目和分类；没有已安装操作时列表为空。生成动作返回 job_id；即时动作返回 status=completed 和 result，不要无条件等待任务。
- `regenerate_job`：保留原任务并生成新版本；修改双语执行稿时同时传中英文。
- `get_job` / `wait_job`：失败时返回 `error_info`，含错误码、缺失项、处理建议与原始错误。

生成任务和插件动作均可携带 `project_id` 明确项目归属；不传时资源动作继承源项目，其他动作沿用当前项目。
接口不支持的额外字段不会被解释成模型或工作流参数。
