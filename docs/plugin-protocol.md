# videofree 插件协议 v1

[English version](plugin-protocol.en.md) · **中文**

本协议用于把本地 AI 模型和零散工作流封装为稳定产品能力：工作台用户选择功能而不是编辑节点，Agent 调用能力 Schema 而不是猜测工作流结构。插件拥有模型专用工作流、提示词规则、UI 和固定资源；框架只提供通用项目、任务、素材、协作与接口能力。

## 安装与边界

### 模型依赖文件归档

插件需要保留 latent、特征、缓存或其他二进制依赖时，使用 `PluginRuntime`：

```python
record = runtime.save_job_file(job, "model-state", source=local_path,
    metadata={"format": "my-model-state", "version": 1})
# 或 output={"filename": "state.bin", "subfolder": "model", "type": "output"}
# source 与 output 必须二选一；可传 sha256、size 进行预期完整性校验。
record = runtime.job_file(job, "model-state")  # 不存在时返回 None
with runtime.materialize_job_file(job, "model-state") as path:
    consume(path)  # 仅在 with 范围内读取，不修改归档文件
runtime.link_job_file(source_job, "model-state", target_job)
runtime.restore_job_file(target_job, "model-state", "model/state.bin")
```

逻辑名为 1–128 位字母、数字、下划线、点或短横线，首位为字母或数字。
同一任务同一逻辑名不可换成不同内容；多份状态使用不同逻辑名。任务须已持久化，
且归属当前插件与项目；禁止跨项目或跨插件链接。插件决定格式、版本和恢复目的路径，
不得把模型专用解释逻辑加入框架。恢复默认到 ComfyUI output，也可显式指定 `destination="input"`。

返回记录包含 plugin_id、project_id、job_id、name、object_key、sha256、size、metadata。
字节归项目 StorageProvider，SQLite 仅保存索引；`.internal/files/` 不作为用户素材展示或提供媒体直链。
保存和读取校验 SHA256，使用流式磁盘暂存，不能假设工作节点缓存永久存在。
归档保存、链接和删除使用独立文件锁，不在全局状态锁内复制大文件。
插件可在校验本地工作节点缓存的大小与归档 SHA256 一致后复用缓存，否则从归档恢复。
恢复收到 HTTP 413 时，需增大 ComfyUI 的 `--max-upload-size` 并重启；使用反向代理时也需检查其限制。
删除任务/分类按引用清理，最后一个引用删除才移除对象，删除项目清理整个项目。
子任务应在依赖被使用前建立链接；恢复应在消费任务执行期间进行，任务生命周期阻止并发删除。
若排队期间尚未链接，插件的 delete 钩子必须阻止源任务提前删除。
现有输入副本、参数和工作流快照由任务包保存，不应再复制为依赖文件。
本接口只提供单机存储基础，不代表多节点执行或租户鉴权已经实现。

一个插件就是 `plugins/<plugin-id>/` 下一个完整文件夹。`plugin.json`、`INSTALL.md`、工作流、专用 Python 编译器、协作处理器和技能文件随文件夹一起分发，无需复制到项目其他目录。内置插件遵守同一协议。

平台负责 HTTP/MCP、项目归档、任务队列、ComfyUI 上传/提交/轮询/下载，以及协作会话、追问和确认；插件负责声明能力、节点绑定、模型专用准备和提示词处理。平台的公共集成适配器可以复用，不能在插件里另起网关或直接改平台数据库。

安装/升级：等待该插件的生成和协作任务结束，复制完整文件夹，重启网关，刷新工作台。禁用可设置 `enabled: false`。不要运行中删除正在执行任务依赖的插件。扫描会隔离无效插件，在 `GET /api/v2/plugins` 的 `errors` 中报告；不保证在线热卸载。

Python 处理器以网关权限运行，**不是安全沙箱**。只安装可信来源的插件。插件不会自动安装模型、ComfyUI 节点、Python 包。缺少依赖应在使用时报告，不能在导入时下载或启动服务。

`INSTALL.md` 是强制安装契约。它必须列出工作流实际使用的所有模型和 ComfyUI 节点包，并为每项给出必需性、准确名称、可信下载地址和相对 ComfyUI 根目录的安装位置；同时列出 Python/系统依赖、外部服务、自动下载行为和许可证限制。没有某类依赖也必须明确写“无”。禁止写开发机绝对路径。开发者更新工作流、模型文件名或节点类时必须同步更新该文件。

用户授权 Agent 安装依赖时，Agent可以按 `INSTALL.md` 下载到对应目录并验证；插件自身仍不得在导入或启动阶段联网安装。原始工作流中的 `properties.cnr_id`、`properties.models` 等元数据仅用于发现线索，最终地址必须以节点/模型官方来源为准。

插件目录在启动期间注册到 ApplicationContext 的共享快照，后续能力与动作发现不再重新扫描清单。安装、删除或更新插件前先排空任务，再重启网关；执行时会检查文件版本，不允许用已修改的插件执行旧快照任务。

## 最小声明示例

目录：

```text
plugins/example-image/
  plugin.json
  INSTALL.md
  workflow.json
```

`workflow.json` 使用 ComfyUI 导出的 API 格式。下面的节点 ID 仅为示例，必须换成自己的节点：

```json
{
  "schema_version": 1,
  "id": "example-image",
  "version": "1.0.0",
  "name": "示例图像插件",
  "categories": [{"id": "design", "name": "设计生成", "icon": "solar:gallery-linear"}],
  "modes": [{"id": "direct", "name": "直接生成"}],
  "ui_models": [{
    "id": "example-model",
    "name": "示例模型",
    "category": "design",
    "functions": [{"capability_id": "example.image.create", "name": "文生图"}]
  }],
  "capabilities": {
    "example.image.create": {
      "name": "示例文生图",
      "category": "design",
      "kind": "image",
      "mode": "text_to_image",
      "model_family": "example",
      "file": "workflow.json",
      "compiler": "declarative",
      "processing_modes": ["direct"],
      "references": {"image": {"min": 0, "max": 0}},
      "prompt_bindings": [{"node": "6", "input": "text"}],
      "parameters": {"guidance": {"type": "number", "label": "引导强度", "default": 4, "minimum": 0, "maximum": 20}},
      "ui": {
        "version": 1,
        "fields": [
          {"bind": "prompt", "component": "textarea", "label": "描述词", "section": "body", "required": true},
          {"bind": "settings.ratio", "component": "select", "label": "比例", "options": [{"value": "16:9", "label": "16:9 横屏"}], "default": "16:9"},
          {"bind": "settings.resolution", "component": "select", "label": "分辨率", "options": [{"value": "1K", "label": "1K"}], "default": "1K"},
          {"bind": "parameters.guidance", "component": "number", "label": "引导强度", "default": 4, "minimum": 0, "maximum": 20}
        ]
      },
      "parameter_bindings": {
        "width": [{"node": "5", "input": "width"}],
        "height": [{"node": "5", "input": "height"}],
        "seed": [{"node": "3", "input": "seed"}],
        "guidance": [{"node": "3", "input": "cfg"}]
      },
      "output_nodes": ["9"],
      "prune_to_outputs": true,
      "output_bindings": [{"node": "9", "input": "filename_prefix"}]
    }
  }
}
```

## 字段规则

### 能力身份与执行钩子

能力的 `name`、`model_id`、`model_name`、`provider_name` 由插件声明，平台不维护内置模型名称表。
`model_family` 用于内部工作流匹配；`model_id` 是对外身份。`model_aliases`、`mode_aliases` 可声明
协作输入别名，`skill_model`、`skill_mode` 指定插件内的技能目录名。不声明时使用模型族和请求模式。
比例、分辨率选项来自 `ui.fields` 的选项；`duration: {"min":1,"max":15,"default":5}` 声明时长约束，
也可由 `settings.duration` 字段的 minimum、maximum、default 推导。不要在框架里添加模型特判。

所有 Python 钩子都使用插件内的 `文件.py:函数名`，支持相对导入，禁止路径越界。

| 声明 | 调用契约 |
| --- | --- |
| compiler_handler | `prepare(workflow, config, request, media, job_id, prompt, runtime=None)`，原地修改工作流；显式声明 runtime 才注入系统服务 |
| executor_handler | `execute(context)`，同步返回 `NativeExecutionResult`；所有非 comfyui 执行器必须声明，无供应商白名单 |
| speech_handler | `prepare_speech(request, preset, runtime)`，返回 `TTSRequest`，用于选择插件音色参考样本 |
| confirmation_handler | `confirmation(source, result, runtime)`，返回 settings、parameters、lyrics 的可选覆盖；需要时可返回 capability_id，但框架只允许切换到同一插件注册的生成能力 |

原生执行契约从 `backend.integrations.native` 导入。`NativeExecutionContext` 提供 job_id、config、
prompt、references、params、api_key、output_dir、media_loader 和 cancelled；执行器应检查取消，
取消时抛 `NativeExecutionCancelled`。返回的 paths 必须非空、全部存在且位于 output_dir 内；
可返回 width、height。插件配置只在执行时注入，不写入任务配置快照。

`runtime.comfyui_request` 调用系统配置的 ComfyUI，`runtime.voice_sample(preset)` 只读定位声音样本。
协作的 `runtime.repair_result` 可接受插件 validator，模型专用格式校验应留在插件。
确认钩子不能替换项目或会话身份，也不代表自动同意用户确认。能力切换必须显式返回 capability_id，并限制在同一插件内已注册的生成能力。

### 当前迁移边界

生成界面、能力发现、模型名称、云端执行器、工作流专用编译与协作规则已使用插件注册。
H3 latent 检查点的持久化、删除与启动恢复已迁入 minimax-h3 插件，通过通用
resource_lifecycle 钩子调度。框架不识别 checkpoint 格式和具体模型的二采条件。
框架仍提供固定的媒体类型和通用尺寸约定，不支持任意新增媒体数据类型。
应用插件推荐使用插件自己的独立 UI bundle；复制插件并重启网关即可加载，不需要重新构建主前端。
只有使用旧式 `application.entry` / `resource_entry` 源码入口的插件才需要随主前端一起构建。

### 操作栏层级

生成插件必须用 `ui_models` 显式声明“主分类 → 模型 → 子功能”，框架不从能力名称或模型 ID 猜菜单。
每个模型包含插件内唯一的 `id`、显示 `name`、已注册的 `category` 和非空 `functions`。`selector_order`
决定同一主分类中模型的排列，数值越小越靠前；每个主分类可有且仅有一个模型声明
`default: true`，工作台首次进入时选中它。未声明默认项时按 `selector_order` 的最小值选择。
每个子功能包含 `capability_id` 和显示 `name`，必须引用同分类的生成能力，不得重复引用或引用后处理能力。
一个插件可注册多个模型，各模型的子功能、参数、参考素材限制和处理模式可以不同。

底部第一个选择主分类，第二个选择模型；左上角以展开标签切换该模型的子功能，与右侧提示词处理模式平级。
每个能力必须声明 `ui: {"version": 1, "fields": [...]}`，所有内置与第三方插件共用同一渲染器。
不再读取 `ui_controls` / `ui_control_config`，也没有按模型名称选择的专用表单。
`parameters` 负责业务参数类型和执行约束；`ui.fields` 负责控件、排列、默认值和提交绑定。
资源编辑和后处理同样读取这些声明。

### 声明式表单

每个字段必须包含唯一的 `bind`、`component`、`label`。`section` 可为 `body`（正文区）、
`settings`（底部设置区，默认）、`submit`（发送按钮旁）。字段顺序就是同一区域的显示顺序。

| component | 用途 | 主要声明 |
| --- | --- | --- |
| textarea / text | 多行 / 单行文字 | placeholder、rows、required、maxLength |
| number | 数字输入框 | minimum、maximum、step、default |
| select | 下拉选项 | options: [{value,label}]、default |
| checkbox | 开关 | default: true / false |
| media | 参考素材加号和预览 | media: image / video / audio |
| voice | 插件音色选择及样本播放 | 音色来源为当前插件的只读目录 |
| style | 共享风格库选择器 | 绑定 settings.style_id |
| dimensions | 按源画面比例选择目标尺寸 | 仅用于后处理，alignment、presets |

绑定根字段可用 `prompt`、`lyrics`；通用生成参数绑定 `settings.<字段名>`，例如 ratio、
resolution、duration、variant、voice_id、voice_speed、instruction、native_model、h3_camera_lora。
插件自有参数绑定 `parameters.<已注册参数名>`，其值传给工作流的 parameter_bindings。
`settings` 可扩展，不由框架维护模型专用字段白名单。插件声明的非素材设置字段会经过表单校验，
再传入执行参数；字段缺省值、选项和取值范围必须由插件声明。
声音语速可声明 `normal_chars_per_second: 4.5`，界面据字数与速度显示粗略时长。
参考素材字段固定绑定 `settings.reference_image` / `settings.reference_video` / `settings.reference_audio`，
由渲染器转换为请求的 `inputs`，不会作为 settings 参数发给执行器。
只要 references 对某种输入声明 max > 0，生成能力就必须提供对应 media 字段，避免漏掉上传入口。
有位置含义的素材必须同时声明 input_roles，例如 image: ["first_frame", "last_frame"]。
生成操作栏将所有 media 字段合并为一个无文字的“＋”入口，点击后通过共享素材弹框管理。
弹框按字段 label、media 及 references 的数量限制分组，支持上传、移除、预览和 input_roles 用途选择；插件无需提供专用弹框。
前后端共用字段声明：服务端只为未传入字段填默认值，并校验必填、枚举和数值范围。

```json
"ui": {
  "version": 1,
  "fields": [
    {"bind": "prompt", "component": "textarea", "label": "语音文本", "section": "body", "required": true},
    {"bind": "settings.reference_audio", "component": "media", "media": "audio", "label": "参考声音", "section": "body"},
    {"bind": "settings.voice_speed", "component": "number", "label": "语速", "section": "submit", "minimum": 0.5, "maximum": 2, "step": 0.1, "default": 1, "normal_chars_per_second": 4.5}
  ]
}
```

需要由预设组合描述词时，在 `ui.prompt_template` 声明 `fields: ["settings.music_style_id", ...]`
和可选的 `suffix`。被引用的选项除 value、label 外必须有 prompt。服务端在未填写 prompt 时拼接选项的 prompt，
已有描述词不会被覆盖。音乐曲风、演唱方式与音色质感都由插件声明，不由前端常量补充。
扩展已有控件类型的表单无需修改前端；新增控件类型或全新执行器仍需平台支持，不能仅靠 JSON 执行任意功能。
`processing_modes` 是独立的提示词处理方式（例如直接生成、H3 转换、导演协作），不与生成子功能混为一层。

生成能力必须列入 `ui_models`；仅供 API 调用的隐藏能力须显式声明 `ui_hidden: true`，不得同时列入菜单。
隐藏能力仍可经 HTTP/MCP 按能力 ID 使用，但不出现在生成操作栏，适合保留调用别名。
漏配菜单会在启动注册时报告错误，不再静默隐藏。`ui_hidden` 必须为布尔值。
纯后处理插件无需声明 `ui_models`。能力目录返回 `selector_model` 和 `mode_name`，供界面渲染；
提交仍使用原 `capability_id`，没有另一套 UI 专用生成接口。

- `schema_version` 固定 1；插件 ID、版本、能力 ID、分类和模式 ID 使用字母、数字、点、下划线、连字符，最多 120 字符，以字母或数字开头。
- 能力 ID 全局唯一。多个插件可加入同一主分类，但分类声明必须一致。主分类可任意新增；`kind` 仍是媒体执行类型：image、video、tts、music、audio，不等于主分类。
- `file`、variant 的工作流、处理器都相对于插件目录，不能逃出目录。工作流支持 JSON/PNG，推荐 API JSON，避免依赖前端专用节点转换。
- `compiler` 默认 declarative；专用图变换通过 `compiler_handler` 交给插件，框架不按模型猜测工作流。
- 比例采用正整数 `宽:高`，如 `32:9`；分辨率采用 `900P`、`1.5K`、`4K` 等格式，K 按 1024 像素换算。
  图片按宽度解析；视频 P 按短边、K 按长边解析。最终尺寸仍须满足接口范围与插件节点的对齐要求。
  选项由插件声明，不受框架比例或分辨率名称白名单限制。
- 语音任务同样保存显式能力 ID、`plugin_parameters` 与 `api_settings`，执行和重新生成不得改按模型名称猜能力。
  声音插件可以使用声明式 ComfyUI 工作流或原生执行器；参考音频会随任务保存并在恢复时重建。
- 每插件声明一个 direct 模式。能力的 `processing_modes` 引用该插件声明的模式 ID；未指定时仅 direct。模式名字没有平台特殊含义，H3 的 compile/director 也是普通注册。
- `parameters` 仅支持 string、boolean、integer、number；可用 default、required、enum、minimum、maximum、maxLength、label。未知参数、类型或范围不匹配会拒绝。不要声明平台保留名：width、height、duration、fps、seed、latent_checkpoint、latent_sha256、music_bpm、music_key、music_timesignature；这些在 parameter_bindings 中直接引用平台值。
- `references` 按 image/video/audio 声明 min/max；`input_roles` 可限定每个输入的角色名。`media_bindings` 按媒体类型列出 `{node,input,source_index}`，默认将上传文件名写入输入。`connect:true` 则创建标准加载节点并连接其 `output`（默认 0）。复杂输入由专用编译器处理。
- `prompt_bindings` 默认绑定最终 prompt，也可 `source` 指向参数、`append:true` 追加到原值。只有显式声明的目标被绑定，不会把负向描述词当正向描述词覆盖。工作流字符串内的 `{{prompt}}` 同样支持替换。
- `output_nodes` 声明最终输出；`prune_to_outputs:true` 保留其依赖图。`output_bindings` 把项目输出前缀写入自定义保存节点。标准保存节点由平台统一设置前缀，最终产物再由平台归档。
- `variants` 为 ID 到配置覆盖的映射，`public_variants` 可限制对外展示档位；`duration` 是 `{min,max,default}`。当前统一接口时长范围 1–360 秒，分辨率与比例使用能力返回的列表。
- `execution_plane` 默认 local，进入本地受控队列；cloud 直接走云端调度。**声明 cloud 不等于实现云端供应商**：目前复用已注册 native 适配器，新增 HTTP 供应商还需平台集成适配，不能凭一个 JSON 地址自动执行。

## 插件音色

声音插件可以在清单顶层声明 `"voice_presets": "voices.py:presets"`。
同步无参数函数返回 `{预设ID: {"display_name": "名称", "instruction": "音色描述"}}`。
预设 ID 全局唯一，遵守插件 ID 的字符规则。可选 `model` 指定注册的模型族，默认使用插件 ID；
`sample_file` 指向插件内现成的参考音频，路径不得离开插件文件夹。
未设置时不提供参考音频，不回退到框架缓存。内置 MP3 等固定资源必须随所属插件分发，
例如 `plugins/cosyvoice3/samples/`；用户上传和生成结果才放入 `data/`。
固定资源在清单顶层 `assets` 数组中逐一列出相对文件路径；插件扫描和发布自检校验存在性与路径边界，
资源修改也会更新插件版本快照，缺失资源的插件不会注册。
工作台和 AI 只读这些定义，不提供全局新增、编辑、删除、训练预设的操作入口。
内置个人音色 `my_voice` 不再分发；旧数据库记录及缓存不参与插件目录，也不自动删除用户文件。

`GET /api/v2/plugins/{plugin_id}/presets` 和 MCP `list_plugin_presets` 统一返回插件声明的
字段选项、该插件音色及所属主分类的用户创作预设；新增插件无需新增专用 MCP 工具。

生成主分类和能力选择由目录自动加载；安装到现有分类的新能力同样直接出现，无需额外打开插件弹框。
所有能力使用统一声明式表单，按能力 ID 提交。

## 插件动作与后处理

能力声明“可以生成什么”；动作声明“如何调用插件业务”。动作统一注册在 `plugin.json` 顶层的 `actions`，不再在 capability 内声明 `postprocess`。生成工作流能力仍可标记 `operation: "postprocess"`。

```json
"actions": [{
  "id": "example.normalize_audio",
  "name": "音量标准化",
  "scope": "resource",
  "automation": true,
  "capability_id": "example.audio.normalize",
  "source_types": ["tts", "music", "audio"],
  "description": "统一声音响度",
  "input_schema": {
    "type": "object",
    "properties": {"parameters": {"type": "object"}},
    "additionalProperties": false
  },
  "ui": {"version": 1, "fields": []}
}]
```

示例需自行提供同插件内的 `example.audio.normalize` 能力和工作流；平台不内置该算法。

- `id` 全局唯一，`name` 必填，`description` 由插件提供。工作台在后处理操作下显示说明。会生成任务的动作可声明 `model_name` 覆盖任务快照中的工作流/算法名称；任务功能名自动使用动作 `name`。
- `scope` 为 `resource`（源素材操作）、`workspace`（工作台动作范围）或 `automation`（便捷自动化调用）。这里的 `workspace` 只是动作分类，不是项目隔离或多租户概念；范围是调用分类，不会凭空创建完整应用页面。
- `automation` 默认 false；只有显式为 true 的动作才会通过 MCP 被发现和执行。插件预设管理不因此向外部 AI 开放。
- `input_schema` 使用 JSON Schema 2020-12，根类型必须为 object，可验证嵌套对象、数组、必填项和数值范围；仅支持文档内 `#` 引用，禁止远程 schema 引用。注册时检查引用目标，悬空引用会禁用该插件并记录原因，不影响其他插件。推荐 `additionalProperties: false`。省略时为不限制属性的 object。
- `capability_id` 如提供，必须属于当前插件；`handler` 如提供，必须为插件内的 `文件.py:函数`。两者至少一个。会生成任务的处理器须声明 capability_id。
- `resource` 必须声明 `source_types`，支持 image/video/tts/music/audio，执行时要求已完成且类型匹配的源素材。可通过 `source_schema`（与 input_schema 相同的 JSON Schema 规则）进一步限制来源、格式和元数据；需检查文件或专用状态时使用插件内 `availability_handler: "文件.py:函数"`。不再支持模型专属的 requires_latent/preview_only 字段。
- `ui` 可选，用于现有后处理表单；支持 `parameters.<参数名>`、`upscaler`、`target_size`，不是任意应用 UI 引擎。

### 唯一发现和执行入口

```text
GET  /api/v2/plugin-actions?scope=resource&source_job_id=<job_id>&automation=true
GET  /api/v2/plugin-actions/<action_id>
POST /api/v2/plugin-actions/<action_id>/execute
```

执行体统一为 `{"project_id":"可选项目ID","source_job_id":"源任务ID","inputs":{...}}`。
外部素材先上传，再以 `source_upload_id` 替代 source_job_id，两者互斥；外部素材可传 category_id，源任务后处理则保持原分类。外部类型按上传文件识别，不接受客户端伪造模型来源或检查点。
外部素材的动作预查可用 `source_kind=image|video|audio`；只是预查，提交时仍会校验真实源文件。`include_unavailable=true` 可用于诊断，返回类型与 source_schema 匹配但暂不可用的动作及 available/reason；不返回来源不匹配的动作。工作台使用默认过滤，隐藏不可用动作。
MCP 仅提供三个固定工具 `list_plugin_actions`、`get_plugin_action`、`run_plugin_action`，参数采用相同字段；不为每个插件增加工具。
客户端先发现动作，再按返回的 input_schema 传 inputs，不推测动作 ID。HTTP 的 automation 查询仅过滤列表；MCP 的查询和执行都会强制检查 automation 标记。

未带 project_id 时继承源任务项目，无源任务时使用当前项目；显式项目必须存在且活跃，不能通过动作把源资源移动到另一项目。系统是单用户单安装，不提供工作区、多租户或 `workspace_id` 隔离参数；HTTP、MCP 和工作台共享同一项目列表。
生成动作返回 `action_id/status/job_id/job_url/wait_url`，继续使用框架任务查询与等待；即时动作返回 `action_id/status:completed/result`，没有 job_id。不要把即时结果当生成任务，也不要把返回会话自动确认。

### 插件处理器

```python
async def inspect(request, runtime):
    # request: {action: 注册声明, source: 源任务或None, inputs: 已校验输入}
    return {"project_id": runtime.project_id, "value": request["inputs"]["value"]}
```

同步函数同样支持，在线程中执行。处理器可返回可 JSON 序列化的字典，或 `(kind, GenerateRequest/TTSRequest)`；后者的 kind 必须与注册能力一致，由框架统一提交、排队、恢复和归档，插件不自行启动生成队列。无 handler 的资源动作由框架将源产物暂存为上传引用，再提交声明的工作流能力。
runtime 提供 `project_id`、插件 `configuration`、`job_request(job)`、当前项目内 `jobs()`、只读 `voice_preset(id)`、`reference(upload_id, media)` 及安全解析 `comfyui_output_file(relative)`。插件不接触平台数据库或目录布局。
仅有动作的插件可声明 `categories: []`、`capabilities: {}`，不需要伪造生成模式或操作栏模型。

### 资源可用性与辅助文件生命周期

```python
def available(request, runtime):
    # request = {action, source}; no submission or other side effects here.
    return {"available": True}
```

availability_handler 必须是同步、只读、轻量函数，只使用注册信息、素材元数据或本地状态，不得探测 ComfyUI、请求网络或扫描模型。不可用时返回 `{"available": false, "reason": "原因"}`，异常或非法返回值按不可用处理。列表发现和正式执行共用此校验；实际文件、检查点和后端依赖由执行处理器在提交时严格验证。H3 列表检查原生初稿来源、采样模式与检查点元数据，提交时确认检查点文件存在；其他模型不能冒用其二采能力。

availability、application startup 和 resource_lifecycle 钩子的 runtime.configuration 均为该插件当前配置，和普通执行处理器保持一致。

插件可在 plugin.json 顶层声明：

```json
"resource_lifecycle": {
  "completed": "resources.py:completed",
  "recover": "resources.py:recover",
  "delete": "resources.py:delete"
}
```

同步签名均为 `(event, runtime)`；event 含 job/request/config，无对应对象时为 null。completed 在生成成功、发布产物前执行；recover 在启动加载任务后执行；delete 在任务、分类或项目删除源产物前执行。身份明确时仅分发给资源所属插件；旧任务缺少插件身份时由处理器自己判断所有权。恢复处理器必须可重复执行，不得访问网络或要求可选后端在线。

通过 `runtime.comfyui_output_files(directory, pattern, detect=False)` 本地查找辅助文件，`runtime.update_job_parameters(job, parameters, **metadata)` 持久化结果参数，`runtime.free_comfyui_memory()` 按需释放显存。输出目录在线探测有缓存；启动恢复必须禁用探测。路径解析限制在输出根目录内。

完成/恢复钩子异常记录日志，不抹掉已生成媒体；删除钩子异常阻止继续删除该素材。插件应校验所有权及活跃任务引用，禁止删除子任务借用的父级辅助文件。框架继续发布工作流返回的全部最终产物，输入类型和输出类型不要求相同，也不限制只能返回一个产物；具体输出类型由能力和产物声明确定。

### 二采和声音动作

H3 的处理器为 `handler: "postprocess.py:prepare"`，遵循相同 `(request, runtime)` 签名。目标尺寸和放大器由 action.ui 声明。
dimensions 字段例：`{"bind":"target_size","component":"dimensions","label":"目标分辨率","required":true,"alignment":32,"presets":[{"edge":720,"label":"720P"},{"edge":2048,"label":"2K","long_edge":true}]}`。
edge 默认短边，long_edge 为 true 时为长边；界面计算 width、height。AI 在 inputs 传 width、height 和可选 upscaler；需要尺寸的动作缺少尺寸返回 422。
声音插件提供 speech_preset、speech_describe、speech_clone 三个动作，输入以实时 schema 为准；三个动作均直接生成任务，不创建协作确认会话。
旧模型生成、`/v1/jobs/{job_id}/refine`、`/api/v2/tts/*`、`/v1/agent/*` 已移除，调用返回 404。生成使用 `/api/v2/generations` 并指定 `capability_id`；插件操作统一使用动作执行入口。H3 直接译稿由 minimax-h3 插件声明的 `h3_translate` 动作提供，通过 PluginRuntime 调用系统 LLM。协作生命周期使用 `/api/v2/collaborations`；素材使用 `inputs: [{type, upload_id, role}]`，分镜使用 `settings.shots`，不再映射旧字段。

## 专用编译器

能力可声明 `compiler_handler: "compiler.py:prepare"`，对应：

```python
def prepare(workflow, config, request, media, job_id, prompt):
    # 原地修改本次工作流；不提交任务，不下载结果。
    pass
```

调用顺序：加载工作流、占位符/固定指令、输入覆盖、上传媒体、媒体绑定、提示词绑定、参数绑定、专用编译器、输出绑定、裁剪和标准化、持久化执行快照、提交。
`media` 为已上传的 image/video/audio 文件名列表；`request` 通常为 GenerateRequest，内置 TTS 走 TTSRequest。专用内置编译器可能复用平台已有的模型集成适配器，不要求第三方复制这些适配器。

## 多处理模式与协作

插件可以任意注册多个模式：

```json
{"id":"review","name":"描述词审核","handler":"collaboration/handler.py:review"}
```

```python
async def review(request, runtime):
    return await runtime.single(request)
```

处理器收到 AgentChatRequest 和平台定义的 `PluginRuntime`。公开能力为：

- `await runtime.single(request)`：复用系统单阶段智能协作。
- `runtime.call_model(messages, max_tokens)`：调用系统 LLM；插件不能读取系统 LLM 密钥。
- `runtime.configuration`：当前插件在自己的 `.env` 中保存、并由声明映射出的运行配置。
- `runtime.session()` / `runtime.save_session()`：使用平台管理的临时协作会话。
- `runtime.start_progress()`、`update_progress()`、`finish_progress()`、`fail_progress()`：写入统一协作进度。

插件不得直接读取平台数据库、HTTP 路由或 `ApplicationContext`。后续系统能力只能通过 `PluginRuntime` 增加，避免插件绑定框架内部实现。复用 single 时，技能放在插件自己的 `collaboration/skills/system.md`、`models/<model_family>/model.md` 和 `modes/<生成mode>.md`；可用能力的 skill_model/skill_mode 覆盖路径。所有调用仍经统一协作调度，框架不会读取根目录技能文件。

### 插件自有协作界面

需要追问、确认或展示模型专用阶段的能力，可以在能力声明中指定插件目录内的 Vue 组件：

```json
{"collaboration_ui": "ui/Collaboration.vue"}
```

`collaboration_ui` 必须是当前插件目录下 `ui/` 目录内的 `.vue` 文件。扫描器会拒绝目录外文件、非 Vue 文件和不存在的文件；能力发现会返回 `plugin_folder` 与 `collaboration_ui`，工作台据此动态加载组件。组件由插件自己维护模板、样式和模型专用交互，框架不根据模型名称渲染协作 DOM，也不在框架中保留旧版协作面板。

组件接收只读属性 `session`、`busy`、`pending`、`answer`，可发出 `update:answer`、`answer`、`confirm`、`new-task` 事件。框架仍负责协作 API、轮询、恢复、版本校验和任务生命周期；插件组件不得直接调用 HTTP 路由或读取数据库。未声明组件时仅显示状态文本。

## 插件配置

只有需要专属参数的插件才声明 `settings`。设置页会自动在左侧增加该插件，不声明则不显示：

```json
{
  "settings": {
    "title": "GPT-Image",
    "description": "云端图片服务",
    "fields": [
      {"key":"SERVICE_API_KEY","label":"API Key","type":"secret","required":true,"runtime_key":"api_key"},
      {"key":"SERVICE_BASE_URL","label":"API 地址","type":"url","runtime_key":"base_url"}
    ]
  }
}
```

支持 `string`、`secret`、`url`、`boolean`、`number`、`select`。字段值写入插件目录的 `.env`，不会写入系统数据库，也不会通过能力目录或 MCP 暴露。`runtime_key` 决定插件运行时可见的名称；密钥只在任务执行时注入。系统配置（ComfyUI、资源目录、公共 LLM）仍写入数据库。

返回值必须是字典：
- `status: needs_input`：同时返回 session_id、questions，保留会话上下文，用户答复后继续该会话。
- `status: ready`：返回 optimized_prompt（执行稿）、optimized_prompt_zh（中文确认稿），以及需要的 generation_payload。沿用现有平台契约，可参考内置插件处理器；不要自己提交生成任务。

平台把处理结果投影为 awaiting_input/awaiting_confirmation 等公共会话状态。外部 AI 不能自行绕过确认或修改预设。插件版本快照在协作继续、确认和排队执行时检查，文件已变更会拒绝旧任务，避免无提示地套用新工作流。

## UI、REST 与 MCP

### 插件边界与固定资源

模型专用提示词、工作流节点识别和图改写必须留在插件目录。公共系统提示词不包含具体模型或模式规则；插件不得导入 `backend.bootstrap.context` 或 generation service 获取全局状态，应使用传入的 `PluginRuntime`。`runtime.style_items()` 提供只读风格目录。

插件固定资源用清单顶层 `assets` 声明相对路径，缺少资源时拒绝注册，不能从框架缓存补齐。用户上传、生成产物与数据库仍归 `data/`。

`parameter_bindings` 的平台内置来源仅有 `width`、`height`、`duration`、`fps`、`seed`；其他来源从已校验的 `plugin_parameters`、内部请求参数读取，未提供时使用绑定中的 `default`，否则报错。音乐、检查点等专用默认值必须由插件声明，例如：

```json
{"parameter_bindings":{"tempo":[{"node":"4","input":"bpm","default":120}]}}
```

可在插件顶层或单个能力声明 `prompt_translation_action`，引用本插件的非 resource 动作。任务编辑器仅在存在该声明时显示直接翻译；动作接收 `text`、`mode`，结果返回 `english_prompt`。框架不维护模型专用动作 ID。

图片风格必须由插件自己提供，声明顶层 `style_library` 的 `directory` 指向插件目录内包含风格 JSON 的文件夹，并用稳定的 `default_id` 指定默认风格。风格提示词、预览图和其它固定素材均随插件放在该目录并列入顶层 `assets`；框架只负责按插件隔离发现、展示和套用，不扫描 ComfyUI 安装目录、环境变量或运行数据中的风格。插件未声明风格库时返回空目录，不会回退到其它插件的风格。

### 工作台应用插件

应用可声明 `requires_project_flags`，框架只在当前项目满足所有标记时返回入口；例如 AI 进度应用使用 `["ai_created"]`。该项目字段默认 `0`，MCP 创建项目时为 `1`，人工创建时为 `0`。

应用不必注册生成能力，也不必进入底部操作栏。声明 `application` 后顶部项目导航自动出现入口；业务实现和页面都留在插件内，例如 `plugins/film-studio/`。需要在分类栏右侧提供轻量项目工具时，声明 `project_tool`；它只打开悬浮工具面板并继承当前项目/分类上下文，不是独立应用：

`project_tool.dialog` 可配置通用容器尺寸，例如 `{"width":860,"height":740}`。
宽高分别接受 `1..4096` 的像素整数或 `"auto"`（由内容决定），省略时默认
`560 × 680`。框架始终将尺寸限制在宿主可用区域内，并隐藏外层滚动条但保留滚动。
插件应设置 `min-width:0` 并自行安排内部内容布局、换行和滚动，不能通过框架选择器修改业务页面。

```json
{
  "application": {
    "name": "成片",
    "icon": "ui/icon.png",
    "entry": "ui/FilmStudio.vue",
    "scope": "project",
    "order": 100,
    "resource_entry": "ui/FilmSelection.vue",
    "source_types": ["video"],
    "selection_label": "已入选成片",
    "library_outputs": {"directory":"films","filenames":["final.mp4"]},
    "startup": "actions.py:startup"
  }
}
```

`entry` 必填，其他字段可选。`scope` 可为 `workspace`、`project`、`category` 或 `resource`，默认是 `project`。`category` 应用必须在当前分类上下文中工作，不得把“全部分类”当作默认数据源。`order` 用于顶部入口排序，未声明时为 1000，再按插件 ID 排序。

`icon` 应是插件目录内的 `.png`、`.jpg`、`.jpeg`、`.webp` 或 `.gif`，例如 `ui/icon.png`。前端从插件目录加载该图片；没有图片时框架使用应用名称的第一个字符。旧的 `solar:`、`mdi:` 和 `lucide:` 图标名仍兼容，但新插件不应依赖框架图标库。

两个 UI 入口必须是插件目录内实际存在的 `.vue` 文件。当前构建扫描 `plugins/*/ui/*.vue`，入口放在该层；安装或修改 Vue/JS 后运行 `cd frontend; npm run build`。这不是远程脚本或运行时任意代码安装器。仅修改声明和 Python 后重启网关即可，已有已构建页面无需重复构建。

页面收到 `project`、`category`、`categoryId`、`categories`、`jobs` 和应用声明中的 `scope`。`categoryId` 为 `null` 表示项目级总览，空字符串表示默认分类，`@public` 不会作为普通分类传给插件。框架在所有应用页面上方提供统一的分类选择器，切换分类会重新挂载应用页面。

应用文档使用分类隔离存储：`runtime.application.documents(project_id, category_id=None)`、`document(...)`、`delete(...)` 均支持分类；当运行时带有 `category_id` 时省略参数即使用当前分类。`save()` 会校验项目和分类归属，并将 `document.category_id` 写入平台表。插件不得只把分类 ID 放在 JSON 的自定义字段里来代替这个字段。

应用插件可以声明 `application_lifecycle` 删除钩子：`project_delete` 和 `category_delete`。钩子处理器签名为 `(event, runtime)`，其中 `event` 包含 `project_id`、`category_id`（项目删除时为 `null`）和 `reason`。钩子失败会阻止删除，插件应在其中清理外部资源和自定义索引；平台随后删除统一文档数据。插件文件应通过 `runtime.application.directory(project_id)` 保存，该目录已按插件 ID 隔离；分类专属文件使用 `category_directory()`。

应用 UI 支持独立构建模式。清单可声明 `application.ui.entry`，入口必须位于插件的 `ui/dist/` 下，例如 `ui/dist/index.js`。该模块默认导出 Vue 组件，或导出可被 Vue 识别的组件对象；框架通过 `/api/v2/plugins/<plugin-id>/ui/...` 动态加载它。独立 UI 的 JS、CSS 和图片均由插件自行打包，主前端不再需要重新构建。未声明 `application.ui` 的插件继续使用传统 `application.entry` 兼容模式。

应用文档会自动带有 `schema_version`（默认为 `1`）。插件升级数据格式时必须递增该字段，并在读取时兼容或迁移旧版本；平台不会猜测插件 JSON 的业务结构。

页面可复用 `@framework` 下的 API、`PluginDialog` 和 `MediaDialog` 等公共组件，框架不导入具体应用名。`PluginDialog` 用于插件自己的业务弹框，统一处理遮罩、ESC、关闭、忙碌态、焦点恢复和内容滚动；插件只负责弹框内容，不要重复实现外层容器。`MediaDialog` 是同一基础组件的媒体场景别名。素材扩展收到 `manifest`、`disabled`，可发送 `notice` 和 `changed` 事件。

插件统一通过 `@framework/services/notifications` 的 `notify(message, options)` 显示通知，通过 `dismissNotification(id)` 关闭，不使用浏览器 `alert()`。`options.type` 支持 `error`（默认）、`success`、`info`，可传 `title`；`duration` 默认为 4500 毫秒，0 为常驻。`notify()` 返回通知 ID，框架最多显示 5 条，支持手动关闭；通知不会阻塞操作，不代替确认框。独立 bundle 构建时须配置 `@framework` 别名指向 `frontend/src` 并打包该服务；通知通过同窗口 DOM 事件跨 bundle 传递，不要求插件共享 Vue 实例。示例：

```js
import { notify, dismissNotification } from '@framework/services/notifications';
notify('素材已保存', { type: 'success' });
const id = notify('正在处理', { type: 'info', duration: 0 });
dismissNotification(id);
```
确认操作使用同一窗口的异步确认服务，插件不应使用浏览器 `confirm()`：

```js
import { confirmAction } from '@framework/services/confirmations';
if (await confirmAction('删除这份记录？', { title: '删除记录', confirmText: '删除' })) {
  // 用户明确确认后才执行插件自己的删除动作。
}
```

返回 `Promise<boolean>`；取消、ESC、关闭或宿主卸载均返回 `false`。多次请求按顺序显示；`danger` 默认 `true`，普通操作可设为 `false`。独立 bundle 需与通知服务一样配置并打包 `@framework` 别名。请求确认前记录目标 ID，确认后校验当前上下文，避免异步等待时误操作其他项目。

公共 UI 可复用 `@framework/components/SelectMenu.vue`（`options/modelValue`、`ariaLabel`）和 `MediaPreview.vue`（`media`、`close` 事件）；前者统一键盘操作、外部点击关闭和视口定位，后者支持图片、视频、音频与 `media.items` 多图预览。菜单定位基础组件为 `PopoverPanel.vue`，传入 `open`、锚点 DOM `anchor` 并监听 `close`。独立构建使用 Vue 组件时仍须遵守本文的 Vue 外部依赖约定，不能打包第二个 Vue 运行时。

框架提供 `ui-button`（可叠加 `is-primary/is-danger`）和 `ui-feedback`（`is-error/is-success/is-info`）样式，以及 `--line-strong`、`--surface-raised`、`--danger`、`--success`、`--info`、`--radius-control`、`--focus-ring` 等令牌。它们由主前端加载，插件无需复制全局样式。业务布局、配色细节和内容滚动仍由插件自己的 scoped 样式负责；框架不得通过插件内部类名调整业务 UI。协作内容须撑满宿主可用高度，消息区滚动，输入区保持底部。

应用及协作入口由框架统一处理加载中、加载/运行失败和重试；插件仍须捕获自己的网络请求错误并给出业务提示。API 请求复用 `@framework/services/api` 的 `gateway`，读取受网关认证保护的媒体使用 `readMediaBlob(url)`，以共享错误解析和令牌过期通知。
`source_types` 控制哪些已完成素材显示扩展，`selection_label` 根据通用任务 `application_marks` 展示角标。`library_outputs` 声明项目子目录只将这些最终文件纳入素材库，过程文件仍保留在磁盘；目录和文件名仅允许单层名称。

应用通过同一顶层 `actions` 声明 JSON Schema 和处理器，经通用 HTTP/MCP 动作入口调用；不会自动生成专用路由或 MCP 工具。不要把异步业务状态和动作返回外层 `status` 混淆。
应用插件后端调用其他插件动作时使用 `await runtime.execute_action(action_id, inputs, source_job_id=..., project_id=..., category_id=...)`，仍由统一动作执行器完成 Schema、来源素材、项目归属、可用性和任务提交校验。提交基础生成能力使用 `await runtime.invoke_capability(capability_id, prompt, inputs=[...], settings={...}, parameters={...}, project_id=..., category_id=..., idempotency_key=...)`；只允许 direct 执行，输入和设置继续按能力实时 Schema 校验。两种调用都禁止插件之间直接导入内部代码。
`runtime.application` 提供按插件 ID 和项目隔离的 `documents/document/save/delete`、`job/jobs/mark/selected`、项目目录、缓存失效、`start` 后台任务和 `semaphore`。`save` 显式提交引用任务 ID 及 active 标记，用于防止运行中删除来源；完成、失败或取消都应清除 active。平台仅存储文档 JSON，不解析成片内容。
启动前重置进程级占用；可选 `startup(runtime)` 异步钩子恢复插件业务状态。任务由 ApplicationContext 统一回收，禁用插件隐藏其入口和动作但保留数据。Python/Vue 插件为可信本地代码，不是权限沙箱。

外部 AI 推荐统一使用 MCP 作为入口，无需同时安装直接 HTTP 调用技能。HTTP 接口仍作为工作台及 MCP 的底层协议保留，两种入口共用同一能力目录、校验和任务服务，不是两套生成实现。

默认扫描项目根目录 `plugins/`；需要自定义位置时设置 `MEDIA_GATEWAY_PLUGINS`。不再扫描旧的 `workflows/plugins/`，也不读取旧环境变量 `MEDIA_GATEWAY_WORKFLOWS`。

`GET /api/v2/plugins` 返回插件、主分类、模型注册及扫描错误；`GET /api/v2/capabilities?category=design` 返回能力、ui 和公开参数。所有插件共用分类、模型和子功能层级，不再提供单独的“插件能力”入口。

统一生成示例：

```json
{
  "capability_id": "example.image.create",
  "prompt": "一张写实场景图",
  "prompt_processing": "direct",
  "parameters": {"guidance": 4},
  "settings": {"ratio": "16:9", "resolution": "1K"},
  "project_id": "从项目接口获取的ID"
}
```

提交 `POST /api/v2/generations`。非 direct 模式使用同一入口，遇到问题携带 session_id/answer 继续；确认沿用会话确认接口。MCP 的 list_capabilities / submit_generation 直接复用同一能力目录和契约，不按插件生成新工具，避免工具数量无限增长。

资源编辑使用同一 UI 声明和参数绑定。重新处理提示词时可传 `parent_job_id`，平台固定继承原任务的项目和分类，确认生成后仍保留父任务关系，不能借此跨项目移动资源。
工作台通过 `GET /api/v2/collaborations?project_id=<ID>` 查询未结束会话，通过 `POST /api/v2/collaborations/<ID>/cancel` 取消。框架负责恢复、轮询和调用这些接口；提问、进度、确认和错误的界面由能力所属插件的 `collaboration_ui` 组件实现，不另外保留按模型提交的框架协作界面。

保留仍在使用的能力 ID、V1 界面入口和任务结构；能力注册唯一来源是 `plugins/*/plugin.json`，不再读取 `workflows/registry.json`。处理模式完全由插件声明，不根据模型名称推断。Python 处理器支持插件内部相对导入，每个插件版本隔离加载。

## 无限画布节点插件

无限画布节点是与普通应用/生成插件分开的扩展类型，只由无限画布宿主发现；不得写入普通 `plugins/<plugin-id>/plugin.json`，也不会出现在工作台插件栏、普通插件目录或 MCP 插件列表。节点包位于 `plugins/canvas-nodes/<package-id>/`，必须包含 `plugin.json`、`INSTALL.md` 和清单引用的本地处理器/资源。它们是受信任的本地 Python 代码，不是安全沙箱。

最小清单：

```json
{
  "schema_version": 1,
  "plugin_type": "canvas_node",
  "id": "project-tools",
  "version": "1.0.0",
  "name": "项目资源节点",
  "assets": [],
  "nodes": [{
    "id": "import-upload",
    "name": "导入上传素材",
    "description": "将临时上传素材导入当前项目素材库",
    "category": "resources",
    "icon": "solar:import-linear",
    "handler": "handlers/resources.py:import_upload",
    "inputs": [{"id": "upload", "name": "上传文件", "type": "upload", "required": true}],
    "outputs": [{"id": "asset", "name": "项目素材", "type": "asset"}],
    "config_schema": {
      "type": "object",
      "properties": {"name": {"type": "string"}, "kind": {"type": "string", "enum": ["image", "video", "audio", "music"]}},
      "additionalProperties": false
    }
  }]
}
```

节点 ID 在包内唯一，外部稳定类型名为 `<package-id>.<node-id>`；端口 ID 也在各自输入/输出列表内唯一。允许的端口类型：`text`、`number`、`integer`、`boolean`、`json`、`upload`、`asset`、`image`、`video`、`audio`、`music`、`media`、`project`、`category`。端口可带 `description`、`required`、`multiple`；`multiple` 只用于输入并表示数组。项目素材句柄至少需要 `{ "project_id": "...", "path": "项目相对路径", "type": "image|video|audio|music" }`，也可包含素材库返回的 `name`、`category_id`、`media_type`、`size`、`modified`、`url` 元数据；`asset`/`media` 可接收任一受支持媒体类型。`image`、`video`、`audio`、`music` 端口会限制媒体类型。`upload` 是短期上传引用 `{ "upload_id": "32位十六进制ID", "name": "可选文件名", "kind": "可选媒体类型" }`，只能作为输入，执行前会验证它仍是网关登记且存在的上传。默认分类 ID 是空字符串。

`config_schema` 必须为 JSON Schema Draft 2020-12 的 object schema；输入和输出依据端口声明自动验证，拒绝额外端口和非 JSON 值。项目端口只能指向当前项目；分类端口必须属于当前项目；素材端口会验证项目归属、素材存在性和扩展名。节点包不能借工作流数据跨项目读取素材。

处理器签名：

```python
def execute(inputs: dict, config: dict, runtime):
    return {"asset": runtime.application.import_upload(
        inputs["upload"]["upload_id"],
        name=config.get("name", inputs["upload"].get("name", "")),
        kind=config.get("kind"),
    )}
```

也支持 `async def`。处理器必须返回一个只含已声明输出端口的 JSON 对象。资源目录读取使用 `runtime.application.library(kind=..., category_id=...)`；上传转项目素材使用 `runtime.application.import_upload(...)`；生成能力和插件动作必须通过 `runtime.invoke_capability(...)` / `runtime.execute_action(...)`，智能体节点可用 `runtime.call_model(...)`。不要直接访问 SQLite、项目文件绝对路径、ComfyUI HTTP 客户端或其他插件代码。`ApplicationRuntime.library()` 返回项目相对路径，不返回项目磁盘绝对路径。

发现与单节点执行使用受认证的 HTTP API：

```text
GET  /api/v2/canvas-nodes
POST /api/v2/canvas-nodes/{package-id}.{node-id}/execute
```

执行请求体为 `{"project_id":"可省略，默认当前项目","category_id":"可省略","inputs":{},"config":{}}`；响应就是处理器的输出 JSON。发现响应只含展示声明和 `config_schema`，不含 Python handler、包目录或 revision；插件错误只提供通用摘要，具体原因写入网关日志。插件文件变化返回 409 和 `X-Plugin-Restart-Required: true`，需排空节点任务并重启网关。节点执行失败返回统一错误，不直接把 Python traceback 或绝对路径交给客户端。

本协议只提供节点包发现、单节点执行、项目资源读写和现有生成/LLM 服务桥接；不负责画布 UI、连线、DAG 校验/调度、工作流 JSON 的保存/分享或运行记录界面。这些属于无限画布应用插件。框架当前没有内置节点包；项目资源、上传、生成、智能体等基础节点应按本协议独立开发和安装。HTTP 节点执行接口也不等于为每个节点增加 MCP 工具，MCP 暴露策略由画布应用自己的工作流动作设计决定。

## UI 中英双语约定

界面语言默认 `zh-CN`，用户在设置中选择 `en-US` 后持久化到框架 SQLite settings；不随项目切换，不依赖浏览器系统语言。HTTP/MCP 的 ID、参数、枚举值、提示词和用户内容保持原样。

插件通过以下清单注册自己的扁平字符串语言包：
```json
"localization": {
  "default_locale": "zh-CN",
  "messages": {
    "zh-CN": "locales/zh-CN.json",
    "en-US": "locales/en-US.json"
  }
}
```
语言包使用 `{"action.save":"保存"}` / `{"action.save":"Save"}`。声明中的显示字段用配套键标记，例如 `"name":"保存", "name_key":"action.save"`；同样适用于 label、description、placeholder、help、title、selection_label、mode_name、model_name、provider_name。选项只翻译 label，不翻译 value；能力、模型、模式和动作 ID 不变。语言包路径必须位于插件自己的 locales 目录。

框架只发布语言包与键元数据，由浏览器解析；不按语言改写 API/MCP 目录。缺少当前语言的键时，回退插件 default_locale，再回退原声明文本。无语言包插件继续显示原文。

插件 UI 收到响应式 `locale` 和 `t(key, fallback?, values?)` props；使用宿主 Vue 的插件也可注入 `videofree:ui-context`，其中 locale 为只读 computed ref，t 为同一翻译函数。例：`t('items.count', '共 {count} 项', {count: 3})`。声明式字段由框架本地化，插件内部按钮、状态、空态等由插件自己的语言包与 t 实现。翻译只在展示时发生，禁止把翻译文案写入业务状态、判断状态或修改提示词语法。

切换语言不得重建插件组件、重置草稿/时间线或监听翻译后对象来重新加载数据；监听稳定 ID。第三方独立构建插件优先使用 props，不导入框架源码。更新语言包属于插件更新，排空任务并重启网关。

音色与风格的显示名、风格分类使用插件自己的语言包，筛选和提交仍使用原 ID/值。固定进度提示在展示处翻译，用户/LLM 内容不自动翻译。日期遵循上下文 locale；没有翻译的服务错误保留原始诊断，并可附当前语言摘要。

声明式生成表单的 `@` 引用显示上传文件名，不随界面语言变化。输入 `@` 可筛选已上传素材；同名文件增加序号，引用在当前草稿内绑定 `upload_id`。提交时按当前各媒体类型的输入顺序转换成 `<Picture 1>`、`<Video 1>`、`<Audio 1>` 等模型标签。删除被引用素材后保留标记并阻止提交，避免错指其他素材。

