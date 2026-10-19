# Architecture

**English** · [中文](ARCHITECTURE.md)

The project is a modular monolith. All capabilities run in one FastAPI process, while code is separated by ownership to prevent cross-domain access through global utility functions.

## Dependency Direction

```text
interfaces/http -> modules -> integrations / persistence
                         -> core
bootstrap / lifecycle -> all application modules
```

- `backend/core/`: environment configuration, runtime context, errors, and logging; it does not depend on business modules.
- `backend/persistence/`: SQLite persistence and data-access APIs only.
- `backend/integrations/`: ComfyUI and native vendor adapters; no HTTP routes.
- `backend/modules/`: business domains such as generation, collaboration, settings, and presets.
- `backend/interfaces/http/`: V1/V2 request schemas, capability mapping, and route adapters.
- `backend/lifecycle.py`: startup recovery, worker creation, cache cleanup, and graceful shutdown.

## Ownership

- `ApplicationContext` is the sole owner of mutable runtime state. Do not add module-level mutable queues, locks, or task tables.
- The product is single-user and single-installation. It has no workspace or multi-tenant isolation; projects, jobs, and assets belong to the gateway installation. Accounts and multi-user permissions are out of scope.
- `TaskStore` owns recoverable task packages and manifests. The ComfyUI executor does not define their disk layout.
- `WorkflowRegistry` owns the workflow allowlist, path validation, and graph loading. HTTP layers do not read workflow files.
- Generation is scheduled by the registered execution plane: local ComfyUI capabilities use the controlled queue; vendor capabilities declaring `execution_plane: cloud` are submitted concurrently. Both use the same job state, persistence, and project archival.
- Collaboration's `progress`, `media`, `prompts`, `analysis`, and `service` modules own progress projection, media adaptation, fixed prompts, deterministic checks, and director orchestration respectively.
- Projects own the current project, job ownership, and the `data/projects/` asset library. The projects domain publishes all final artifacts after generation; the resource panel does not scan ComfyUI output directories.
- `plugins/film-studio/` is the editing application plugin. It owns its page, asset-selection extension, six-stage progress, plans, and its own FFmpeg timeline engine. The framework loads it through generic application registration and actions, with no editor-specific route or service. `ApplicationRuntime` provides plugin- and project-scoped documents, marks, file access, and cancellable background tasks; task state and semaphores belong to `ApplicationContext`. Startup does not probe optional editing dependencies.
- V1 routes are grouped by system, assets, generation, and collaboration. V2 schemas and capability mapping are independent of route assembly.

## Extension Rules

1. Put new generation capabilities in `plugins/<plugin-id>/` and register their primary category, capability, parameters, and processing modes in `plugin.json`. Keep dedicated workflow compilers and collaboration handlers in the same plugin; routes must not branch on workflow nodes. Cloud vendors must explicitly declare `execution_plane: cloud`; local capabilities default to `local`.
2. Register every non-direct plugin mode with a Python handler. Platform collaboration owns sessions, queues, confirmation, and scheduling; it must not special-case H3. H3 prompt conversion and director collaboration are two modes in one plugin.
3. Move methods into shared modules only when at least two domains actually use them. Keep single-domain helpers in their domain.
4. HTTP handlers only validate protocol data, map errors, and orchestrate service calls; they do not parse external-service file formats.
5. Do not keep legacy model protocol entry points or infer capabilities from model names. Generation submissions must specify a plugin `capability_id`; new code imports from the actual owner.

## Contracts and Runtime

See the [plugin protocol](docs/plugin-protocol.md). `PluginCatalog` isolates invalid plugins. `WorkflowRegistry` reads only capabilities registered by plugin manifests and does not load a legacy registry. Handlers load as versioned Python packages and support relative imports within a plugin. Model-specific collaboration code is called by its plugin, without framework compatibility forwarding.

The frontend reads primary categories, capabilities, processing modes, and `ui.version=1` field declarations from the capability catalog. Plugins share `PluginComposer` and `PluginField`; resource editing and post-processing use the same declarations instead of built-in model forms. `backend/modules/generation/plugin_ui.py` validates declarations, applies defaults, and assembles option prompts. Workflow compilers execute parameters; they do not define layout. Voice definitions belong to audio plugins; the platform provides read-only discovery and sample access, not global preset management.

Toolbar hierarchy is declared by plugin `ui_models`: primary category, model, and top-left generation subfeature. Settings bind to the current subfeature's capability declaration. Prompt-processing mode is a separate peer of the subfeature; the framework does not maintain model submenu lists.

HTTP v2 and MCP share the capability catalog and submission entry point; plugins do not duplicate routes or MCP tools.

System LLM access, collaboration sessions, progress, and cross-plugin capability/action dispatch are exposed through the stable `PluginRuntime` interface. Cross-plugin calls still pass through capability/action catalogs, project ownership, schema validation, and the shared task queue. Plugins must not import another plugin's code or read the system database or LLM secrets. Plugin-specific settings are declared in `plugin.json.settings`, edited per plugin, and stored in that plugin's `.env`; system settings remain in the settings database.

System-level external-service adapters belong in `backend/integrations/system_services/`, not in generation plugins. LLM providers are manifest-discovered; provider-specific behavior stays in each adapter, and collaboration does not branch on provider IDs. Adding an LLM provider does not require changing framework business code. See the [system service extension protocol](docs/system-service-protocol.md) for the current contract and the generic service-runtime capabilities not yet implemented.

Plugin business operations are declared in top-level `plugin.json.actions`, including purpose, input schema, automation visibility, and handler. `generation/actions` owns shared validation, project ownership, source adaptation, and task scheduling; dedicated behavior belongs to the plugin. HTTP/MCP provide fixed action discovery, detail, and execution entry points. Speech generation, refinement, and translation use these entry points. Legacy model generation, dedicated TTS, refinement, H3 translation, and studio-collaboration URLs were removed without redirects or fallback. Projects, uploads, jobs, collaboration lifecycle, and system services remain framework-owned regardless of whether an endpoint contains `v1`.

Queued jobs and collaborations store a plugin-version snapshot. If plugin files change, old jobs are rejected; drain jobs before updating a plugin.

Plugin revision fingerprints hash manifests, source, documentation, and declared resources; they do not depend on file timestamps after installation or copying. `ApplicationContext.executing_jobs` tracks active executors: cancellation state does not mean the executor has exited. Project deletion and storage-directory changes wait for executor exit; archival cannot be cancelled.

The gateway token belongs to system settings and is shared by the workbench, HTTP API, and MCP. Environment variables provide defaults only when no saved setting exists. After browser-token verification, the browser receives a time-limited signed HttpOnly, SameSite=Strict session; direct media links use the same session. Rotating the token invalidates old sessions, while API/MCP clients continue to send `X-API-Token`.

Local Python plugins are trusted code, not a sandbox. Arbitrary online code installation is not supported.

Native executors are selected by each capability's `executor_handler`. The framework only defines execution context, return values, and cancellation contracts; it does not maintain a vendor allowlist.

Plugin-owned fixed assets, including voice MP3s, must ship inside the plugin and be referenced by plugin-relative paths. The framework must not complete a plugin package with resources from `data/cache`. User uploads, jobs, and generated outputs remain runtime data.

Workflow-specific graph transformations, H3 prompt review, voice-sample preparation, and confirmation-parameter correction belong to plugin `compiler_handler`, `speech_handler`, `confirmation_handler`, and collaboration handlers. Model names, public IDs, aliases, and duration constraints come from plugin declarations.

Resource actions declare applicability using `source_types`, `source_schema`, and plugin `availability_handler`. Discovery and execution share validation; the framework does not recognize model-specific checkpoint formats.

Plugin manifests are registered once at startup into an `ApplicationContext` snapshot. Discovery endpoints do not rescan files or probe ComfyUI. Availability hooks are lightweight and read-only; actual files and backend dependencies are checked at execution. Drain jobs and restart after plugin updates; submission and execution verify the revision to prevent mixing a manifest with a different handler version.

Auxiliary-file lifecycle belongs to plugin `resource_lifecycle` hooks (`completed`, `recover`, and `delete`). H3 checkpoint persistence, deletion, and startup recovery belong to `minimax-h3`. Startup recovery checks local directories only and does not depend on ComfyUI being online.

Application plugins should ship their own `ui/dist/` bundle so installation does not require rebuilding the main frontend. A repository plugin that still uses a source Vue entry only requires the main frontend to be rebuilt when that entry changes. Declarative generation plugins do not need a dedicated Vue component.

## Verification

```powershell
python -m compileall -q backend tests
python -m unittest discover -s tests -p 'test_*.py'
cd frontend
npm ci
npm run build
cd ..
cmd /c "videofree.bat --check"
```
