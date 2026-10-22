# System Service Extension Protocol / 系统服务扩展协议

This document defines the stable boundary for framework-level services. System services are neither generation plugins nor application plugins. They provide shared infrastructure to the framework and trusted local plugins, while the framework retains configuration ownership, credential storage, lifecycle, and the public runtime contract.

本文规定框架级系统服务的稳定扩展边界。系统服务不是生成插件，也不是应用插件。它们为框架和可信本地插件提供共享基础能力；配置归属、密钥存储、生命周期及对外运行时契约由框架管理。

## Goals and compatibility / 目标与兼容规则

- Adding a provider for an already supported service contract must only add files under that service's directory. Do not edit framework modules, HTTP/MCP routes, settings UI, or plugin code.
- A provider may implement only the provider interface of its service. It must not own application behavior, project data, or framework configuration storage.
- The service contract is versioned and framework-owned. A provider declares the contract version it implements. A breaking contract change requires a new major contract version; the framework may keep two versions during a documented migration, but must not add provider-ID branches.
- A new provider must be discoverable from its manifest and isolated from other providers when loading fails.

- 为已支持的系统服务增加服务商时，只能在该服务目录中增加文件，不得修改框架模块、HTTP/MCP 路由、设置界面或插件代码。
- 服务商只实现所属服务的供应商协议，不得接管应用业务、项目数据或框架配置存储。
- 服务契约由框架维护并版本化；服务商必须声明所实现的契约版本。破坏性变更升级主版本。迁移可按文档短期保留两个版本，但不得增加按供应商 ID 分支的框架代码。
- 服务商必须由清单发现；单个服务商加载失败不得阻止其他服务商启动。

An arbitrary new kind of behavior cannot be made plug-and-play by documentation alone. To meet the no-framework-edit requirement, future system extensions must fit the generic service invocation contract and settings schema below. A genuinely new cross-cutting runtime primitive is a protocol-version change and must be implemented once in the framework before providers can use it; do not disguise that change as a provider addition.

仅靠文档无法让任意新行为自动接入。为满足“不因每个扩展修改框架”的要求，后续系统扩展必须适配下文的通用服务调用契约和设置 Schema。若确实需要新的跨领域运行时原语，那是协议版本升级，必须先在框架中实现一次，不能伪装成新增服务商。

## Ownership and directory / 归属与目录

System service adapter source belongs to `backend/integrations/system_services/`. The current LLM catalog uses this layout:

```text
backend/integrations/system_services/
  llm_providers/
    openai-compatible/provider.py
    openai-compatible/provider.json
    deepseek/provider.json
    custom/provider.json
```

系统服务适配代码归属 `backend/integrations/system_services/`。当前 LLM Provider 目录为：

```text
backend/integrations/system_services/
  llm_providers/
    openai-compatible/provider.py
    <provider-id>/provider.json
```

Generic provider manifests are stored in `<service-id>_providers/<provider-id>/provider.json`. The manifest's `entry` resolves from the service catalog root, allowing providers of one service to share an adapter while preventing paths from escaping that catalog. The complete machine-readable contract is [`schemas/system-service-provider-v1.schema.json`](schemas/system-service-provider-v1.schema.json).

通用 Provider 清单位于 `<service-id>_providers/<provider-id>/provider.json`。`entry` 相对于该服务目录解析，因此同一服务可共享适配器，同时禁止路径逃逸。完整机器契约见 [`schemas/system-service-provider-v1.schema.json`](schemas/system-service-provider-v1.schema.json)。

The first file-storage contract is implemented separately from LLM provider discovery in `backend/integrations/system_services/storage/`: `protocol.py` owns the contract and object metadata; `local.py` implements the local backend. `StorageProvider` owns byte-object operations only: safe relative keys, `put_stream`/`put_file`, `open`, metadata listing, delete/prefix-delete, and local materialization. The framework owns project/category metadata and authorization. The built-in `LocalStorageProvider` follows the active resource-directory setting; it is not manifest-discovered because it is currently the only backend. A future storage backend must satisfy the same contract and be explicitly selected by framework configuration before use.

首个文件存储契约独立于 LLM Provider 注册器，代码位于 `backend/integrations/system_services/storage/`：`protocol.py` 声明契约与对象元数据，`local.py` 实现本地后端。`StorageProvider` 只负责文件对象字节操作：安全相对键、`put_stream`/`put_file`、`open`、元数据列表、删除/前缀删除及本地物化。项目/分类元数据和授权仍归框架。本地 Provider 根据当前资源目录设置工作；目前它是唯一后端，因此没有做清单发现。未来存储后端必须实现同一契约，并由框架配置显式选择后才可启用。

Do not put system services in `plugins/`, `backend/modules/`, `backend/core/`, or the project data directory. Runtime configuration and secrets remain in the framework settings database, never beside provider code. The registry rejects providers of one service when they disagree on contract version, selection key, UI visibility, or operation schemas.

系统服务不得放进 `plugins/`、`backend/modules/`、`backend/core/` 或项目数据目录。运行配置和密钥继续由框架保存到设置数据库，不得与服务商代码放在一起。同一服务的 Provider 若在契约版本、选择键、UI 可见性或操作 Schema 上不一致，注册表会拒绝加载。

## Current ComfyUI contract / 当前 ComfyUI 契约

`backend/integrations/system_services/comfyui/provider.json` declares
`schema_version: 1`, `service_id: "comfyui"`, `contract_version: 1`,
`provider_id: "default"`, and `entry: "provider.py:Provider"`. Startup validates
versions, entry confinement and required methods, and injects one provider into
`ApplicationContext.comfyui_provider`. Settings retain the existing URL and local
output-directory controls; there is no node-management or provider-selection UI.

ComfyUI 清单声明以上版本、服务、默认 Provider 和入口，启动时校验并注入唯一实例。
设置继续使用现有地址与本地输出目录，没有新增节点管理或 Provider 切换界面。

The typed `ComfyUIProvider` methods are `configure(base_url)`,
`request(path, method="GET", body=None)`, `is_available()`,
`node_definitions(kinds, aliases)`, `upload_input(body, media_type, filename)`,
`open_output(descriptor)`, `download_output(descriptor)`,
`upload_file(source, relative, destination="output")`, and `free_memory()`.
`open_output` is a streaming context manager. `upload_file` streams opaque files
to safe relative input/output paths, without interpreting model formats.
Plugins use PluginRuntime rather than importing provider implementations.

类型化契约的方法如上。`open_output` 是流式上下文管理器；`upload_file` 流式恢复任意
字节文件到安全的相对 input/output 路径，不解析模型格式。插件通过 PluginRuntime
访问服务和任务依赖文件，不导入 Provider 实现。这是单 Provider 接入，没有实现
下文的通用 invoke 注册表或多节点调度。

## Generic service contract / 通用服务契约

Every system service uses the same outer contract. Service-specific Python types may refine the payloads, but must not bypass the registry, settings boundary, or error contract.

```python
class SystemServiceProvider:
    def __init__(self, manifest: dict): ...

    def invoke(self, operation: str, inputs: dict, settings: dict, *, context) -> dict:
        """Run a declared operation and return JSON-compatible data."""
        ...
```

The framework runtime resolves `(service_id, provider_id, operation)`, validates declared input/output schemas, injects only that service's approved settings, and maps provider exceptions to a credential-free `SystemServiceError` with a stable error code. Plugins use the framework's `PluginRuntime.call_system_service(service_id, operation, inputs)`; they never import a provider module or receive secrets. Framework-owned business flows may use the typed facade for that service, which delegates to the same registered provider and error handling.

所有系统服务使用相同的外层契约。具体服务可用 Python 类型细化数据结构，但不得绕过注册表、设置边界或统一错误契约。

```python
class SystemServiceProvider:
    def __init__(self, manifest: dict): ...

    def invoke(self, operation: str, inputs: dict, settings: dict, *, context) -> dict:
        """执行已声明操作并返回 JSON 兼容数据。"""
        ...
```

框架运行时按 `(service_id, provider_id, operation)` 解析服务，校验清单声明的输入/输出 Schema，只注入该服务获准读取的设置，并将供应商异常转换为不含密钥的稳定 `SystemServiceError`。插件只能调用框架的 `PluginRuntime.call_system_service(service_id, operation, inputs)`，不能导入供应商模块或接收密钥。框架自身的业务流程可以使用该服务的类型化门面，但门面必须委托给同一个注册服务和错误处理流程。

## Manifest / 清单

This contract is implemented by `SystemServiceRegistry`. LLM providers use it directly; typed ComfyUI and Storage facades remain available for streaming and filesystem operations that are not JSON operations.

本契约由 `SystemServiceRegistry` 实现。LLM Provider 已接入；ComfyUI 和 Storage 对流式字节及文件操作继续保留类型化门面，不强行伪装成 JSON 操作。

Each generic provider manifest declares identity, contract compatibility, operations, settings, and a local entry point:

```json
{
  "schema_version": 1,
  "service_id": "llm",
  "contract_version": 1,
  "provider_id": "example",
  "name": "Example LLM",
  "entry": "provider.py:Provider",
  "settings": {
    "fields": [
      {"key":"base_url","type":"url","default":"https://api.example/v1"},
      {"key":"api_key","type":"string","secret":true,"environment":"EXAMPLE_API_KEY"}
    ]
  },
  "operations": {
    "chat": {
      "input_schema": {"type": "object"},
      "output_schema": {"type": "object"}
    },
    "list_models": {
      "input_schema": {"type": "object"},
      "output_schema": {"type": "object"}
    }
  }
}
```

- `service_id` and `provider_id` are stable machine IDs; display names may change.
- `entry` is relative to the `<service-id>_providers/` catalog and must remain inside it. Shared adapters are allowed there; provider-private code should remain inside its provider directory.
- `settings.fields` is a whitelist. Each field may declare its runtime key, framework settings source, environment fallback, type, default, required/secret flags and UI metadata. Plugins never receive this declaration or its secret values.
- Each operation has JSON Schema input/output. Undeclared operations are not callable.
- Manifests may include non-secret capability metadata, but must not contain executable workflow definitions, user data, credentials, or arbitrary filesystem paths.

每份服务商清单必须声明身份、契约兼容版本、操作、设置和本地入口：

- `service_id`、`provider_id` 是稳定机器 ID，显示名称可以修改。
- `entry` 相对 `<service-id>_providers/` 服务目录解析，必须留在该目录内部。
- `settings.fields` 是设置白名单，可声明运行键、框架设置来源、环境变量回退、类型、默认值以及 required/secret 和 UI 信息；插件不会得到设置声明或密钥值。
- 每个操作都要提供 JSON Schema 输入/输出；未声明操作不得调用。
- 清单可声明非敏感能力元数据，但不得包含可执行工作流、用户数据、凭证或任意文件系统路径。

## Security, lifecycle, and errors / 安全、生命周期与错误

- Provider Python is trusted in-process code, not a sandbox. Keep it narrowly scoped and review it like framework integration code.
- Provider receives only the selected provider's settings. It must never log or persist secrets, and errors must redact URL credentials and authorization headers.
- Network calls require explicit timeouts. Long-running/cancellable work must cooperate with the supplied cancellation context; providers must not create unmanaged threads or global mutable state.
- Catalog loading validates IDs, versions, entry paths, and operation schemas. Invalid providers are reported in diagnostics and do not disable healthy providers.
- Settings updates persist only explicitly supplied values; masked or environment-derived secrets are never copied into the database implicitly.
- Providers must not access the database directly, mutate projects/jobs, scan plugin folders, or call another provider by importing its implementation.
- Adding/removing providers requires a gateway restart. Hot reload is not part of protocol v1.

- Provider 是进程内可信 Python 代码，不是沙箱；必须保持职责狭窄，并按框架集成代码审查。
- Provider 只能收到当前选中服务商的设置，不得记录或持久化密钥；错误信息需脱敏 URL 凭证和授权头。
- 网络调用必须设置超时。长任务/可取消任务必须遵从传入的取消上下文；不得创建无人管理的线程或模块级可变状态。
- 注册表需校验 ID、版本、入口路径和操作 Schema。非法服务商只产生诊断，不得拖垮其他正常服务商。
- 配置更新只持久化调用方明确提交的字段；遮罩值或环境变量提供的密钥不会被隐式复制进数据库。
- Provider 不得直接访问数据库、修改项目/任务、扫描插件目录或通过导入另一个 Provider 实现来调用它。
- 新增或移除服务商需要重启网关；协议 v1 不承诺热更新。

## Current LLM provider contract / 当前 LLM Provider 契约

The typed LLM facade keeps `build_chat_request`, `parse_chat_response`, and `list_models`. The generic surface additionally implements `invoke(operation, inputs, settings, *, context)`. Collaboration retains cancellation-aware transport and media retries; `PluginRuntime.call_system_service("llm", ...)` uses the declared generic operations.

LLM 类型化门面继续提供 `build_chat_request`、`parse_chat_response`、`list_models`；通用面额外实现 `invoke(operation, inputs, settings, *, context)`。协作模块继续负责可取消传输和媒体重试；插件通过声明的通用操作调用 LLM。

1. Add `backend/integrations/system_services/llm_providers/<provider-id>/provider.json`. Declare `service_id`, `contract_version`, `provider_id`, `name`, `entry`, settings fields and operation schemas. Never put API keys in a manifest.
2. Reuse `openai-compatible/provider.py` only when its request format and response shape match the service. The current adapter's supported thinking values are `none`, `openai`, `deepseek`, and `custom`; adding a new request protocol or thinking behavior requires changing the provider adapter and tests, not a manifest-only addition.
3. If a new adapter is needed, place it under `llm_providers/` and point `entry` to it. The entry is resolved from the catalog root, not the provider folder.
4. Add tests for request construction, response normalization, model listing, malformed responses, and secret redaction.
5. Run focused tests and the backend suite, then restart the gateway. Settings discovery comes from the catalog.

1. 在 `backend/integrations/system_services/llm_providers/<provider-id>/provider.json` 新增清单，声明 `service_id`、`contract_version`、`provider_id`、`name`、`entry`、设置字段和操作 Schema。禁止把 API Key 写入清单。
2. 只有当请求格式和响应结构一致时才复用 `openai-compatible/provider.py`。当前适配器支持的 thinking 值为 `none`、`openai`、`deepseek`、`custom`；若增加新的请求协议或 thinking 行为，需修改 Provider 适配器并补测试，不能只靠清单实现。
3. 若需新适配器，将代码放在 `llm_providers/` 下并在 `entry` 指向它。入口相对注册表根目录解析，不是相对 Provider 子目录。
4. 为请求构造、响应归一化、模型列表、异常响应和密钥脱敏添加测试。
5. 运行专项及后端测试后重启网关；设置页通过注册表发现服务商。

## Current implementation status / 当前实现状态

The code implements generic provider discovery, contract-versioned manifests, JSON Schema input/output validation, schema-driven settings storage, credential-free errors, and `PluginRuntime.call_system_service`. LLM providers run on this registry. Local StorageProvider and the single-node ComfyUIProvider retain typed facades because their streaming/file operations are intentionally outside the JSON invocation contract. Remote storage, multiple ComfyUI nodes, scheduling and tenancy are not part of v1.

当前已实现通用 Provider 发现、带契约版本的清单、输入输出 JSON Schema 校验、Schema 驱动设置存储、无凭据错误以及 `PluginRuntime.call_system_service`；LLM Provider 已运行在该注册表上。本地 StorageProvider 与单节点 ComfyUIProvider 因包含流式/文件操作继续使用类型化门面。远程存储、多 ComfyUI 节点、调度和多租户不属于 v1。

## Related docs / 相关文档

- [Architecture / 架构说明](../ARCHITECTURE.md)
- [Plugin protocol / 插件协议](plugin-protocol.md)
