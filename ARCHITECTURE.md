# 架构说明

[English version](ARCHITECTURE_EN.md) · **中文**

项目采用模块化单体。所有能力运行在一个 FastAPI 进程内，但代码按业务所有权隔离，避免通过全局工具函数互相穿透。

## 依赖方向

```text
interfaces/http -> modules -> integrations / persistence
                         -> core
bootstrap / lifecycle -> all application modules
```

- `backend/core/`：环境配置、运行时上下文、错误和日志，不依赖业务模块。
- `backend/persistence/`：SQLite 持久化，只提供数据访问。
- `backend/integrations/`：ComfyUI 与原生供应商适配，不包含 HTTP 路由。
- `backend/modules/`：generation、collaboration、settings、presets 等业务模块。
- `backend/interfaces/http/`：V1/V2 请求模型、能力映射和路由适配。
- `backend/lifecycle.py`：启动恢复、worker 创建、缓存清理和优雅关闭。

## 关键所有权

- `ApplicationContext` 是运行期可变状态的唯一容器；禁止新增模块级可变队列、锁或任务表。
- 当前产品是单用户单安装，不提供工作区或多租户隔离；项目、任务和素材属于当前网关安装实例。多人账号和权限不在当前范围内。
- `TaskStore` 负责可恢复任务包和 manifest；ComfyUI 执行器不直接设计磁盘结构。
- `WorkflowRegistry` 负责工作流 allowlist、路径校验和画布加载；HTTP 层不读取工作流文件。
- generation 按注册表中的执行面调度：本地 ComfyUI 能力进入受控队列，声明
  `execution_plane: cloud` 的供应商能力直接并发提交；两者共用任务状态、持久化和项目归档。
- collaboration 的 `progress`、`media`、`prompts`、`analysis` 和 `service` 分别负责进度投影、素材适配、固定提示词、确定性检查和导演编排。
- projects 负责当前项目、任务归属和 `data/projects/` 项目素材库。生成任务完成后由该域发布全部最终产物；资源面板不扫描 ComfyUI 输出目录。
- `plugins/film-studio/` 是成片应用插件，拥有页面、素材选择扩展、六阶段进度、方案和插件自有 FFmpeg 时间线引擎。框架只通过应用注册和通用动作承载，不保留专用成片路由或服务。`ApplicationRuntime` 提供按插件及项目隔离的文档、标记、文件访问和可取消后台任务；任务与信号量归 ApplicationContext，启动不探测可选合成依赖。
- V1 路由按 system、assets、generation、collaboration 分组；V2 的 schema 与 capability 映射独立于路由组装。

## 扩展规则

1. 新能力放入 `plugins/<plugin-id>/`，由 `plugin.json` 注册主分类、能力、参数和多个处理模式。专用工作流编译器与协作处理器放在同一插件内，禁止在路由里判断节点。
   云端供应商必须显式声明 `execution_plane: cloud`，本地能力保持默认的 `local`。
2. 插件的所有非 direct 模式统一注册 Python 处理器；平台 collaboration 只负责会话、队列、确认和调度，不特殊识别 H3。H3 转换和导演协作为同一插件的两个模式。
3. 跨模块复用的方法只有在两个业务域真实使用时才进入 shared；单域帮助函数留在本域。
4. HTTP handler 只做协议校验、错误映射和调用编排，不直接访问外部服务文件格式。
5. 不保留旧模型协议入口或按模型猜测能力的提交路径；生成必须指定插件 capability_id，新代码从实际所有者导入。

## 验证

插件协议见 [docs/plugin-protocol.md](docs/plugin-protocol.md)。PluginCatalog 隔离损坏的插件，WorkflowRegistry 仅使用插件清单注册能力，不再加载旧 registry。处理器按插件版本作为 Python 包加载，支持插件内部相对导入；模型专用协作实现由插件直接调用，不通过平台兼容转发。
前端从能力目录获取主分类、能力、处理模式和 `ui.version=1` 字段声明。全部插件共用 PluginComposer / PluginField，资源编辑和后处理也读取同一声明，不保留内置模型专用表单。backend/modules/generation/plugin_ui.py 统一校验声明、应用缺省值和组装选项提示词；工作流编译器负责执行参数，不负责布局。音色定义归声音插件，平台仅提供只读目录和样本读取，不提供全局预设管理。
操作栏层级由插件 `ui_models` 声明：主分类、模型、左上角生成子功能；设置绑定当前子功能的能力声明。右侧提示词处理模式与子功能平级且独立，框架不维护模型子菜单列表。
HTTP v2 与 MCP 共用能力目录和提交入口，不给每个插件复制路由或 MCP 工具。
系统 LLM、协作会话、进度及跨插件能力/动作调用通过 `PluginRuntime` 作为稳定框架接口提供给插件；跨插件调用仍经过能力与动作目录、项目归属、Schema 校验和统一任务队列，插件不得导入其他插件代码、读取系统数据库或 LLM 密钥。插件专属配置由 `plugin.json.settings` 声明、设置页按插件切换，并保存到该插件的 `.env`；系统配置仍归 settings 数据库。
系统级外部服务适配归 `backend/integrations/system_services/`，不得伪装成生成插件。当前 LLM Provider 通过清单发现，服务商差异由 Provider 实现，协作业务不按服务商 ID 分支。新增 LLM Provider 不修改框架业务代码；系统服务扩展协议及当前未覆盖的通用调用能力见 [docs/system-service-protocol.md](docs/system-service-protocol.md)。
插件业务通过 plugin.json 顶层 actions 声明用途、输入 Schema、自动化可见性和处理器；generation/actions 负责统一校验、项目归属、源素材适配和任务调度，专用实现归插件。HTTP/MCP 只提供固定的动作发现、详情和执行入口；声音生成、二采与译稿均走此入口。旧模型生成、专用 TTS、refine、H3 翻译和 studio 协作 URL 已移除，不提供重定向或回退。项目、上传、任务、当前协作生命周期和系统服务仍归框架，不因 URL 含 v1 而废弃。
排队任务与协作保存插件版本快照，插件文件发生变化后拒绝继续执行旧任务；更新插件应先排空任务。
插件修订指纹使用清单和源码、文档及声明资源的内容哈希，不依赖安装或复制后的文件时间。执行中的任务由 ApplicationContext.executing_jobs 跟踪，取消状态不代表执行器已退出；删除、切换存储目录必须等待执行器退出，归档阶段拒绝取消。
网关访问令牌归系统 settings，工作台、HTTP API 和 MCP 共享唯一生效值；环境变量只提供未保存设置时的缺省值。浏览器令牌验证后获得有时限的 HttpOnly、SameSite=Strict 签名会话，媒体直链使用同一会话；轮换令牌使旧会话失效，API/MCP 继续使用 X-API-Token 请求头。
本地 Python 插件是可信代码，不是沙箱；不支持在线安装任意网络代码。

原生执行器由能力的 executor_handler 声明，框架只保留执行上下文、返回值与取消契约，不维护供应商白名单。
插件专属固定资源（包括音色 MP3）必须随插件分发并通过插件内相对路径引用；框架不得用 data/cache 的资源补全插件安装包。用户上传、任务和生成结果仍归运行数据。
工作流专用图变换、H3 提示词审查、声音样本准备和确认参数修正分别由插件的 compiler_handler、
speech_handler、confirmation_handler 及协作处理器拥有。模型名称、对外 ID、别名和时长约束来自插件声明。
资源动作以 source_types、source_schema 和插件 availability_handler 声明适用条件，发现与提交共用校验，框架不识别模型专用检查点格式。
插件清单在启动期间注册为 ApplicationContext 共享快照，发现接口不重复扫描文件或探测 ComfyUI；可用性钩子只做轻量只读检查，执行时才校验实际文件与后端依赖。插件更新需排空任务并重启，提交与执行检查版本，避免清单与处理器混用。
辅助文件生命周期由插件 resource_lifecycle 的 completed/recover/delete 钩子负责；H3 检查点持久化、删除和启动恢复归 minimax-h3 插件。启动恢复仅检查本地目录，不依赖 ComfyUI 在线。
应用插件应优先分发自己的 `ui/dist/` 独立 bundle，安装插件时不需要重新构建主前端；仓库内仍使用源码 Vue 入口的插件只有在修改该入口时才需要重建主前端。纯声明式生成插件不需要编写专用 Vue 组件。

```powershell
python -m compileall -q backend tests
python -m unittest discover -s tests -p 'test_*.py'
cd frontend
npm ci
npm run build
cd ..
cmd /c "videofree.bat --check"
```
