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

Provider manifests are stored in `<provider-id>/provider.json`. The manifest's `entry` currently resolves from the `llm_providers/` catalog root, allowing the built-in providers to share `openai-compatible/provider.py`. The catalog validates the entry remains inside that root. Current manifests use `schema_version`, `id`, `name`, `entry`, optional `thinking`, and string `defaults` limited to `ai_base_url` and `ai_model`.

Provider 清单位于 `<provider-id>/provider.json`。当前 `entry` 相对于 `llm_providers/` 目录解析，因此内置 Provider 可以共用 `openai-compatible/provider.py`；目录注册器会校验入口仍在该目录内。当前清单字段为 `schema_version`、`id`、`name`、`entry`、可选的 `thinking`，以及仅含字符串 `ai_base_url`、`ai_model` 的 `defaults`。

Do not put system services in `plugins/`, `backend/modules/`, `backend/core/`, or the project data directory. Runtime configuration and secrets remain in the framework settings database, never beside provider code. If the generic cross-service runtime contract is implemented, its loader and manifest may use a service-first directory layout, but that migration must update this document and its tests together.

系统服务不得放进 `plugins/`、`backend/modules/`、`backend/core/` 或项目数据目录。运行配置和密钥继续由框架保存到设置数据库，不得与服务商代码放在一起。未来若通用跨服务运行时采用 service-first 目录布局，必须同步更新本协议和测试。

## Future generic service contract / 未来通用服务契约

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

The following is a **target design, not the current implementation**. The current LLM catalog does not load `service_id`, `contract_version`, operation schemas, or schema-driven provider settings. Do not implement a provider against this example until the generic runtime is implemented and the status section below is updated.

以下是**目标设计，不是当前实现**。当前 LLM 注册器不读取 `service_id`、`contract_version`、操作 Schema 或 Schema 驱动的 Provider 设置。通用运行时实现并更新下文状态之前，不要按该示例实现 Provider。

Each future generic provider manifest would declare identity, contract compatibility, operations, settings, and a local entry point:

```json
{
  "schema_version": 1,
  "service_id": "llm",
  "contract_version": 1,
  "provider_id": "example",
  "name": "Example LLM",
  "entry": "provider.py:Provider",
  "settings": {
    "defaults": {"base_url": "https://api.example/v1", "model": "example-model"},
    "fields": []
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
- In the current LLM catalog, `entry` is relative to `llm_providers/` and must resolve within that catalog. Shared adapters are allowed there; provider-private code should remain inside its provider directory.
- `settings.defaults` contains non-secret initial values only. Secret fields are declared explicitly and are stored by the framework in its settings database.
- Each operation has JSON Schema input/output. Undeclared operations are not callable.
- Manifests may include non-secret capability metadata, but must not contain executable workflow definitions, user data, credentials, or arbitrary filesystem paths.

每份服务商清单必须声明身份、契约兼容版本、操作、设置和本地入口：

- `service_id`、`provider_id` 是稳定机器 ID，显示名称可以修改。
- `entry` 相对服务商目录解析，必须留在该目录内部。
- `settings.defaults` 只能包含非敏感默认值。密钥字段必须显式声明，并由框架写入设置数据库。
- 每个操作都要提供 JSON Schema 输入/输出；未声明操作不得调用。
- 清单可声明非敏感能力元数据，但不得包含可执行工作流、用户数据、凭证或任意文件系统路径。

## Security, lifecycle, and errors / 安全、生命周期与错误

- Provider Python is trusted in-process code, not a sandbox. Keep it narrowly scoped and review it like framework integration code.
- Provider receives only the selected provider's settings. It must never log or persist secrets, and errors must redact URL credentials and authorization headers.
- Network calls require explicit timeouts. Long-running/cancellable work must cooperate with the supplied cancellation context; providers must not create unmanaged threads or global mutable state.
- Catalog loading validates IDs, versions, entry paths, and operation schemas. Invalid providers are reported in diagnostics and do not disable healthy providers.
- Providers must not access the database directly, mutate projects/jobs, scan plugin folders, or call another provider by importing its implementation.
- Adding/removing providers requires a gateway restart. Hot reload is not part of protocol v1.

- Provider 是进程内可信 Python 代码，不是沙箱；必须保持职责狭窄，并按框架集成代码审查。
- Provider 只能收到当前选中服务商的设置，不得记录或持久化密钥；错误信息需脱敏 URL 凭证和授权头。
- 网络调用必须设置超时。长任务/可取消任务必须遵从传入的取消上下文；不得创建无人管理的线程或模块级可变状态。
- 注册表需校验 ID、版本、入口路径和操作 Schema。非法服务商只产生诊断，不得拖垮其他正常服务商。
- Provider 不得直接访问数据库、修改项目/任务、扫描插件目录或通过导入另一个 Provider 实现来调用它。
- 新增或移除服务商需要重启网关；协议 v1 不承诺热更新。

## Current LLM provider contract / 当前 LLM Provider 契约

The current provider interface has three methods: `build_chat_request(settings, messages, max_tokens, tools, tool_choice, *, plain_request=False, disable_thinking=False)`, `parse_chat_response(payload)`, and `list_models(base_url, api_key="")`. `build_chat_request` returns `(endpoint, body, headers, has_optional_thinking)`. The adapter owns endpoint construction, provider-specific request options, response normalization, and model-list retrieval. Collaboration retains cancellation-aware HTTP transport, media fallback/retry, orchestration, and output validation.

当前 Provider 接口有三个方法：`build_chat_request(settings, messages, max_tokens, tools, tool_choice, *, plain_request=False, disable_thinking=False)`、`parse_chat_response(payload)` 和 `list_models(base_url, api_key="")`。`build_chat_request` 返回 `(endpoint, body, headers, has_optional_thinking)`。适配器负责 endpoint 构造、供应商专用请求参数、响应归一化和模型列表读取；协作模块继续负责可取消 HTTP 传输、媒体兼容重试、编排和输出校验。

1. Add `backend/integrations/system_services/llm_providers/<provider-id>/provider.json`. Set `id`, `name`, `entry`, optional `thinking`, and safe string `defaults`. Never put API keys in a manifest.
2. Reuse `openai-compatible/provider.py` only when its request format and response shape match the service. The current adapter's supported thinking values are `none`, `openai`, `deepseek`, and `custom`; adding a new request protocol or thinking behavior requires changing the provider adapter and tests, not a manifest-only addition.
3. If a new adapter is needed, place it under `llm_providers/` and point `entry` to it. The entry is resolved from the catalog root, not the provider folder.
4. Add tests for request construction, response normalization, model listing, malformed responses, and secret redaction.
5. Run focused tests and the backend suite, then restart the gateway. Settings discovery comes from the catalog.

1. 在 `backend/integrations/system_services/llm_providers/<provider-id>/provider.json` 新增清单，声明 `id`、`name`、`entry`、可选 `thinking` 和安全字符串 `defaults`。禁止把 API Key 写入清单。
2. 只有当请求格式和响应结构一致时才复用 `openai-compatible/provider.py`。当前适配器支持的 thinking 值为 `none`、`openai`、`deepseek`、`custom`；若增加新的请求协议或 thinking 行为，需修改 Provider 适配器并补测试，不能只靠清单实现。
3. 若需新适配器，将代码放在 `llm_providers/` 下并在 `entry` 指向它。入口相对注册表根目录解析，不是相对 Provider 子目录。
4. 为请求构造、响应归一化、模型列表、异常响应和密钥脱敏添加测试。
5. 运行专项及后端测试后重启网关；设置页通过注册表发现服务商。

## Current implementation status / 当前实现状态

The current code implements manifest discovery for LLM providers and keeps the collaboration call site provider-neutral. It does not yet implement the generic `SystemServiceProvider.invoke` registry, schema-driven settings for arbitrary service types, or `PluginRuntime.call_system_service`. Therefore v1 currently guarantees framework-free addition of LLM providers only. Do not claim arbitrary future service types are plug-and-play until those generic runtime pieces are implemented. This status is intentional and must be updated as the contract is implemented.

当前代码已实现 LLM Provider 清单发现，协作调用点不再按服务商分支。但尚未实现通用 `SystemServiceProvider.invoke` 注册表、任意服务类型的 Schema 驱动设置界面，以及 `PluginRuntime.call_system_service`。因此当前 v1 只保证增加 LLM Provider 无需修改框架。在这些通用运行时能力实现前，不得宣称任意未来服务类型可直接插拔。协议实现完成后必须同步更新本节状态。

## Related docs / 相关文档

- [Architecture / 架构说明](../ARCHITECTURE.md)
- [Plugin protocol / 插件协议](plugin-protocol.md)
