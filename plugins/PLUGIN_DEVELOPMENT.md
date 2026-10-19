# VideoFree 插件开发指南

VideoFree 插件的目标，是把零散的模型、ComfyUI 工作流、提示词规则和配套资源封装成普通用户能直接使用、Agent 能稳定调用的产品能力。用户不应为了使用插件而理解节点连线；Agent 也不应接触节点 ID、模型路径或工作流内部结构。

插件是本地可信代码包，必须位于 `plugins/<plugin-id>/`，由同目录的
`plugin.json` 注册。框架负责发现、校验、项目归属、任务状态、持久化边界和 HTTP/MCP 通用入口；插件负责业务、工作流、页面和专用资源。

使用开发智能体时，可以安装仓库内的 `.agents/skills/videofree-plugin-development/`，让它先按本指南与当前协议判断插件形态，再实现和验证。技能不必与源码位于同一台电脑：它会先寻找仓库标记文件；本地没有源码时可从 [GitHub](https://github.com/linpengishero/VideoFree) 或 [Gitee 镜像](https://gitee.com/heroofgod_admin/videofree) 获取。仓库内文档始终是协议唯一事实来源。

## 目录结构

```text
plugins/my-plugin/
  plugin.json                 # 唯一注册入口
  INSTALL.md                  # 必需：模型、节点和运行依赖安装说明
  compiler.py                 # 可选：工作流/请求编译器
  actions.py                  # 可选：插件动作
  lifecycle.py                # 可选：应用删除钩子
  ui/                         # 可选：应用 UI
    MyApplication.vue
    dist/                     # 独立构建 UI
  workflows/                  # 可选：专用工作流
  assets/                     # 固定资源
  tests/                      # 插件测试
```

固定资源（图标、CosyVoice 音色 MP3、提示词模板、工作流辅助文件）必须随插件分发，不能放在框架目录、`data/` 或根目录。可变数据不能写回插件源码目录。

## 从 ComfyUI 工作流开发

用户可以把一个或多个原始 ComfyUI 工作流交给开发 Agent。优先接收 API JSON；UI JSON 或带工作流信息的 PNG 应先导出或提取为 API JSON，不能靠截图重写节点图。逐个核对输入、输出、模型加载节点、自定义节点、媒体角色和参数，再决定它们是同一能力的 variant、同插件的多个能力，还是不同插件。

工作流 UI JSON 的 `properties.cnr_id` 可帮助定位 ComfyUI Manager 包，`properties.models` 可提供模型文件和来源；这些信息仍需同官方仓库核对。无法确认来源时应明确标记待确认，禁止编造下载地址。插件打包测试过的工作流快照，用户和外部 Agent 只面对语义化能力，不应看到节点编号。

## 安装依赖说明（必需）

每个插件必须提供 `plugins/<plugin-id>/INSTALL.md`，即使插件没有 ComfyUI 依赖也要明确写“无”。安装说明至少包含：

1. 支持的 ComfyUI/VideoFree 或外部服务版本；
2. 每个必需/可选模型的准确文件名或仓库 ID、官方或作者下载地址、相对 ComfyUI 根目录的安装路径；
3. 每个自定义节点包的仓库名、ComfyUI Manager ID（若有）、下载地址、`custom_nodes/<目录>` 安装位置，以及工作流实际使用的节点类名；
4. Python 包、系统程序、云端 Key 等其他依赖；
5. 自动下载行为、许可证/再分发限制、安装后验证和常见缺失错误。

路径必须写成相对 ComfyUI 根目录，例如 `models/diffusion_models/example.safetensors`，不能写开发者电脑上的盘符。下载地址应指向官方模型页、官方仓库或作者明确发布页；不能用不明网盘替代。插件导入和网关启动阶段禁止联网下载，安装只能由用户或获得用户授权的 Agent 执行。

推荐结构：

```markdown
# 插件名安装说明

## 模型
| 必需 | 文件/仓库 ID | 下载地址 | 安装到（相对 ComfyUI 根目录） |

## ComfyUI 节点
| 必需 | 包/Manager ID | 下载地址 | 安装到 | 本插件使用的节点类 |

## 其他依赖
## 安装验证
## 许可证与自动下载说明
```

## 清单注册

```json
{
  "schema_version": 1,
  "id": "my-plugin",
  "version": "1.0.0",
  "name": "我的插件",
  "description": "插件说明",
  "assets": ["assets/icon.png"],
  "categories": [],
  "capabilities": {},
  "modes": [],
  "actions": []
}
```

`id`、`version` 必须唯一且只能使用字母、数字、`.`、`_`、`-`。所有清单路径必须是插件目录内的相对路径。

## 能力、模式和动作

能力写入 `capabilities`，处理模式写入 `modes`。编译器、提示词转换、确认修正和供应商适配必须放在插件目录，路由不得判断模型名称或读取工作流文件。

动作写入 `actions`，例如：

```json
{
  "id": "my-plugin.list",
  "name": "查询插件数据",
  "scope": "workspace",
  "automation": true,
  "handler": "actions.py:execute",
  "input_schema": {"type": "object", "properties": {}, "additionalProperties": false}
}
```

动作处理器接收框架校验后的输入和 `PluginRuntime`。项目、分类、素材归属和来源条件必须通过运行时接口校验；破坏性动作默认使用 `automation: false`。

生成动作须在动作声明中填写 `capability_id`，处理器返回 `(kind, GenerateRequest)` 或 `("tts", TTSRequest)`。框架会把动作声明的能力 ID 和动作名称注入任务快照后走统一提交校验；动作使用的算法或工作流不同于能力默认模型时，再声明 `model_name`。调用方无需在动作 `inputs` 中重复传入。只注册工作流真实支持的能力；隐藏入口也会被 MCP 发现，不能用 `ui_hidden` 掩盖未实现的功能。

协作返回 `ready` 时必须提供完整的 `optimized_prompt` 和 `optimized_prompt_zh`；返回 `needs_input` 时必须提供 `session_id` 及非空 `questions`（每项包含 `text`、可选择的 `options`）。复用 `runtime.single(request)` 会由框架创建会话并修复一次格式异常；自定义协作处理器应使用 `runtime.repair_result(...)`。`start_progress` 接收阶段对象列表，例如 `[{"id": "optimize", "label": "提示词优化"}]`，不能传模式名称字符串。

## PluginRuntime

```python
def prepare(workflow, config, request, media, job_id, prompt, runtime=None):
    # runtime.plugin_id / project_id / category_id
    # runtime.configuration / runtime.application
    return workflow
```

常用接口：

```python
runtime.job_request(job)
runtime.jobs()
runtime.call_model(messages, max_tokens=2500)
runtime.comfyui_request(path, method="GET", body=None)
runtime.application
```

### 完整运行时接口

插件处理器不应导入 `backend` 内部模块；需要平台能力时只使用下面的稳定接口。

`PluginRuntime` 提供：

| 接口 | 用途 |
| --- | --- |
| `plugin_id`, `project_id`, `category_id` | 当前插件及项目/分类上下文，只读属性 |
| `configuration` | 当前插件通过 `settings` 声明映射出的配置 |
| `application` | 当前应用插件运行时，见下表 |
| `single(request)` | 复用平台单阶段协作流程（异步） |
| `call_model(messages, max_tokens=2500)` | 调用平台 LLM，不暴露密钥 |
| `comfyui_request(path, method="GET", body=None)` | 调用系统 ComfyUI 适配器 |
| `job_request(job)` | 读取任务的持久化请求 |
| `jobs()` | 读取当前项目可见任务 |
| `update_job_parameters(job, parameters, **metadata)` | 持久化插件产生的任务元数据 |
| `voice_preset(id)`, `voice_sample(preset)` | 只读读取声音预设及样本路径 |
| `style_items()` | 读取当前插件自己的风格库 |
| `reference(upload_id, media)` | 校验并取得上传参考素材引用 |
| `comfyui_output_file(relative)` | 安全读取一个 ComfyUI 输出文件 |
| `comfyui_output_files(directory, pattern, detect=True)` | 在输出目录内查找辅助文件 |
| `free_comfyui_memory()` | 请求释放 ComfyUI 显存 |
| `session(id)`, `save_session(session, limit=50)` | 读写平台管理的临时协作会话 |
| `initial_message(request)`, `staged_context(request)` | 构造标准协作上下文 |
| `repair_result(...)` | 使用平台模型修复结构化协作结果，可传插件 validator |
| `start_progress(...)`, `update_progress(...)`, `finish_progress(...)`, `fail_progress(...)` | 写入统一协作进度 |

`runtime.application` 提供项目和应用级数据边界：

| 接口 | 说明 |
| --- | --- |
| `project(id)`, `projects()` | 查询项目；运行时有项目上下文时会拒绝越界访问 |
| `categories(project_id=None)`, `category(project_id=None, category_id=None)` | 查询项目分类 |
| `directory(project_id)` | 当前插件的项目文件目录 |
| `category_directory(project_id=None, category_id=None)` | 当前插件的分类文件目录 |
| `resolve_library_path(project_id, relative_path, allowed_suffixes=None)` | 安全解析项目素材库相对路径，校验项目归属、路径穿越、文件存在性和扩展名 |
| `job(job_id)`, `jobs(project_id)` | 查询项目任务 |
| `selected()`, `mark(job_id, selected)` | 读取/设置插件素材选择标记 |
| `documents(project_id=None, category_id=None)` | 查询插件文档 |
| `document(project_id, document_id, category_id=None)` | 查询单个插件文档 |
| `save(document, references, active=False, selected_job_id=None)` | 保存文档、声明任务引用和活跃状态 |
| `delete(project_id, document_id, category_id=None)` | 删除插件文档 |
| `start(key, coroutine)` | 注册一个受框架管理的后台任务；同一插件/项目/key 不可重复运行 |
| `semaphore()` | 获取当前插件的项目级并发信号量 |
| `invalidate_library()` | 使工作台素材库缓存失效 |

应用插件后端如需调用其他插件的生成或业务动作，使用 `await runtime.execute_action(action_id, inputs, project_id=..., category_id=...)`。该接口复用统一动作发现、Schema、项目归属和任务提交校验；禁止导入其他插件的 Python 模块或直接调用其内部函数。

`directory()` 和 `category_directory()` 返回的路径只用于当前插件文件，不能把路径暴露给客户端或写入插件源码目录。
项目素材库路径不是插件目录路径；插件只能保存项目相对资源句柄，读取时必须调用
`resolve_library_path()`，不能自行拼接 `projects_root` 或读取框架数据库。

插件不能读取系统密钥、直接操作 SQLite、直接依赖 HTTP 路由内部实现，或把供应商协议写入框架模块。

插件处理器需要返回明确业务错误时，从稳定运行时导入 `PluginError`，不要依赖 FastAPI：

```python
from backend.modules.shared.plugin_runtime import PluginError

raise PluginError(422, "素材规格不符合当前能力")
```

框架会在 HTTP/MCP 边界统一转换错误；`409` 用于可重试的状态冲突，`422` 用于输入或能力约束，`502` 用于插件或上游返回异常。

## 应用 UI

插件页面可复用 `@framework` 下的 `PluginDialog` 和 `MediaDialog`。`PluginDialog` 统一处理遮罩、ESC、关闭、忙碌态、焦点恢复和内容滚动；插件只实现业务内容，不要复制外层弹框。`MediaDialog` 是媒体选择和预览场景的别名。资源扩展仍可发送 `notice` 和 `changed` 事件。

所有插件可调用框架通知服务，不需要自己实现通知容器，也不要使用浏览器 `alert()`：

```js
import { notify, dismissNotification } from '@framework/services/notifications';

notify('素材已保存', { type: 'success' });
notify('无法读取素材', { type: 'error', title: '操作失败' });
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

`type` 支持 `error`（默认）、`success`、`info`；`title` 可选，`duration` 单位为毫秒，默认 4500，0 表示不自动消失。返回的 ID 可用于关闭通知。框架统一显示最多 5 条通知，通知不会阻塞操作，也不能代替用户确认。独立 bundle 构建时需配置 `@framework` 别名指向 `frontend/src` 并将通知服务打包；浏览器不直接解析该别名。服务通过同一窗口的 DOM 事件与框架通信，不依赖共享 Vue 实例。

应用可声明 `requires_project_flags`，只有当前项目满足所有标记时才显示入口，例如 AI 进度应用声明 `["ai_created"]`。`ai_created` 默认是 `false`，由 MCP 创建项目时设置为 `true`，人工工作台创建的项目保持 `false`；它只控制入口可见性，不存储进度。`categoryId=null` 显示项目总览，具体分类 ID 显示该分类进度，同一个应用不应拆成两个插件。

应用页面由插件自己实现。推荐使用独立 bundle：

```json
{
  "application": {
    "name": "剧本",
    "scope": "category",
    "ui": {"entry": "ui/dist/index.js"},
    "icon": "assets/icon.png"
  }
}
```

`ui/dist/index.js` 默认导出 Vue 组件：

```js
export { default } from './ScriptApplication.vue';
```

JS、CSS、图片和依赖全部由插件构建并放在 `ui/dist/`。框架通过
`/api/v2/plugins/<plugin-id>/ui/...` 动态加载，不需要重新构建主前端。

也可以使用传统入口 `application.entry`（以及资源扩展的 `resource_entry`），但这类入口是主前端构建的一部分，必须位于插件的 `ui/*.vue`，新增或修改后运行 `cd frontend; npm run build`。推荐新插件使用 `application.ui.entry` 独立 bundle；两种模式只能选择一种，不要同时注册两套页面实现。独立 bundle 不得引用主前端的相对源码路径。

页面会收到 `application`、`project`、`category`、`categoryId`、`categories`、当前分类筛选后的 `jobs`，以及宿主提供的 `resourcePicker` 函数。`scope` 可为 `workspace`、`project`、`category` 或 `resource`；其中 `workspace` 仅表示工作台动作/入口范围，不提供数据隔离。分类插件必须按 `categoryId` 过滤和保存数据。

页面通过属性接收上下文，通过事件通知工作台：资源扩展可发送 `notice`（字符串）和 `changed`（任意变更标记）；工作台收到 `changed` 后会刷新任务和素材。插件页面应自行调用统一 REST API 或插件动作接口，不要访问父组件内部状态。独立 bundle 的入口默认导出 Vue 组件，且不得依赖主前端的相对源码路径。

应用插件可以调用宿主资源选择器，不要复制实现资源抽屉：

```js
props.resourcePicker({
  types: ['video'],
  onSelect: resource => addToTimeline(resource),
});
```

`types` 可使用 `image`、`video`、`audio`、`music` 等资源类型；省略时显示全部类型。选择器默认使用当前项目和当前分类，用户也可以切换到项目的全部素材或项目资产。点击“引用”后调用 `onSelect`，取消或关闭不会调用回调。

回调资源结构如下：

```js
{
  project_id: 'project-id',
  category_id: 'category-id-or-null',
  name: '片段.mp4',
  type: 'video',
  path: 'projects/project-id/片段.mp4',
  url: '/v1/library/files/projects/project-id/%E7%89%87%E6%AE%B5.mp4'
}
```

`path` 是项目资源句柄，不是任意文件路径，也不能作为绝对路径返回给浏览器。建议只把 `path` 写入插件文档；展示或预览时使用 `url`，合成、探测和读取时在插件后端调用：

```python
source = runtime.resolve_library_path(
    project_id,
    clip['library_path'],
    allowed_suffixes={'.mp4', '.mov', '.webm', '.mkv'},
)
```

插件应保存 `library_path` 而不是 `url`。资源可能被用户删除，读取失败时应返回可恢复的业务错误，不能绕过校验访问磁盘。

## 结构化数据

使用框架提供的插件文档存储：

```python
app = runtime.application
items = app.documents(project_id, category_id)
item = app.document(project_id, document_id, category_id)
app.save({
    "id": "script-001",
    "project_id": project_id,
    "category_id": category_id,
    "schema_version": 1,
    "title": "第一集"
}, references=[job_id], active=False)
app.delete(project_id, document_id, category_id)
```

平台按 `plugin_id + project_id + category_id + document_id` 隔离。插件不能自己创建平台表或直接取得 SQLite 连接。`schema_version` 由插件维护，升级数据格式时自行兼容或迁移。

## 文件和素材

```python
project_dir = app.directory(project_id)
category_dir = app.category_directory(project_id, category_id)
jobs = app.jobs(project_id)
app.mark(job_id, True)
selected = app.selected()
```

运行时目录为：

```text
data/projects/<project>/.plugins/<plugin-id>/
data/projects/<project>/.plugins/<plugin-id>/categories/<category-id>/
```

文档的 `references` 应列出依赖的任务 ID；后台处理期间设置 `active=True`，完成、失败或取消后必须恢复为 `False`。框架删除项目或素材前会检查引用。

## 后台任务

```python
task = runtime.application.start("index", coroutine())
semaphore = runtime.application.semaphore()
```

任务和信号量由 `ApplicationContext` 管理。不得创建模块级全局队列、锁或任务表。项目/分类删除期间不能有插件后台任务运行。

## 删除生命周期

```json
{
  "application_lifecycle": {
    "project_delete": "lifecycle.py:project_delete",
    "category_delete": "lifecycle.py:category_delete"
  }
}
```

处理器签名：

```python
def category_delete(event, runtime):
    # event: project_id, category_id, reason
    # runtime.application: 当前插件和项目/分类上下文
    pass
```

钩子失败会阻止删除。分类钩子成功后框架清理插件分类目录；项目目录和插件文档由框架删除。钩子应幂等。任务辅助文件另有 `resource_lifecycle` 的 `completed`、`recover`、`delete` 钩子，不能代替应用数据生命周期钩子。

## 配置和固定资源

- 插件配置在 `plugin.json.settings` 声明，通过插件设置接口读取。
- 音色预设在清单声明，样本 MP3 使用插件内相对路径。预设语音提交前会验证音色存在、归属插件和样本文件；模型专用的音频时长限制应由插件处理，不能在框架硬编码统一的 30 秒限制。
- 风格必须内置在插件中：使用 `style_library.directory` 指向插件内 JSON 风格目录，使用 `style_library.default_id` 指定默认项，并在 `assets` 中声明风格 JSON 与预览图片。用网关的插件能力生成实际风格示例，作为该插件的缩略图，不从 ComfyUI 风格目录复制素材。`runtime.style_items()` 只返回当前插件的风格；没有风格库的插件得到空列表。框架不读取 ComfyUI 风格目录、`MEDIA_STYLE_DIR` 或其它插件的资源。
- 8-bit PCM WAV 在上传给 ComfyUI 时自动转换为 PCM16；原始上传文件及任务输入哈希保持不变。
- 图标使用插件内 PNG/JPG/WEBP/GIF；没有图片时框架显示名称首字。
- 工作流放插件目录并注册，不使用根目录旧工作流路径。

## 测试和发布检查

至少测试清单扫描、输入校验、项目/分类隔离、数据保存读取、删除钩子幂等、路径安全和外部依赖缺失。

```powershell
python -m compileall -q backend tests plugins
python -m unittest discover -s tests -p 'test_*.py'
cmd /c "videofree.bat --check"
```

发布前确认：`INSTALL.md` 与当前工作流一致且没有本机绝对路径；每个模型和自定义节点都有来源与安装位置；固定资源都在插件目录；没有框架专用分支；没有直接 SQLite/ComfyUI 文件访问；独立 UI bundle 位于 `ui/dist`；动作已通过通用能力发现和 MCP 入口暴露；项目和分类删除不会留下插件数据。

完整字段约束见 [`docs/plugin-protocol.md`](../docs/plugin-protocol.md)。
