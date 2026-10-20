# VideoFree Plugin Development Guide

[中文](PLUGIN_DEVELOPMENT.md) · **English**

VideoFree plugins package scattered models, ComfyUI workflows, prompt rules, and related resources as product capabilities that people can use and agents can call reliably. Users should not need to understand node wiring; agents should not need node IDs, model paths, or workflow internals.

A plugin is trusted local code under `plugins/<plugin-id>/`, registered by its local `plugin.json`. The framework owns discovery, validation, project ownership, job lifecycle, persistence boundaries, and shared HTTP/MCP entry points. Plugins own their product behavior, workflows, pages, and dedicated resources.

For another AI coding agent, install/read `.agents/skills/videofree-plugin-development/` first. The skill locates the source repository and follows this guide plus the [plugin protocol](../docs/plugin-protocol.en.md); repository documentation is the authoritative contract. The skill can be used on another machine and can obtain the repository from [GitHub](https://github.com/linpengishero/VideoFree) or the [Gitee mirror](https://gitee.com/heroofgod_admin/videofree).

## Directory layout

```text
plugins/my-plugin/
  plugin.json                 # only registration source
  INSTALL.md                  # required dependency installation guide
  compiler.py                 # optional workflow/request compiler
  actions.py                  # optional plugin actions
  lifecycle.py                # optional application deletion hooks
  ui/                         # optional application UI
    MyApplication.vue
    dist/                     # standalone UI bundle
  workflows/                  # optional plugin workflows
  assets/                     # fixed resources
  tests/                      # plugin tests
```

Fixed resources (icons, CosyVoice samples, prompt templates, workflow support files) ship inside the plugin. Do not put them in framework directories, `data/`, or the repository root. Mutable user data must never be written into plugin source directories.

## Develop from ComfyUI workflows

Users may provide one or more original ComfyUI workflows. Prefer API JSON exports. Export UI JSON or extract workflow PNGs to API JSON first; do not recreate node graphs from screenshots. Inspect each workflow's inputs, outputs, model-loader nodes, custom nodes, media roles, and parameters. Decide whether workflows are variants of one capability, multiple capabilities in one plugin, or separate plugins.

Workflow UI JSON metadata such as `properties.cnr_id` can help identify ComfyUI Manager packages, and `properties.models` may show model filenames and sources. Verify these against official repositories. If a source cannot be confirmed, state the gap; never invent a download URL. Bundle the tested workflow snapshot. Users and external agents interact with semantic capabilities, never node numbers.

## Required dependency guide

Every plugin must include `plugins/<plugin-id>/INSTALL.md`, including plugins with no ComfyUI dependencies (state “none”). At minimum include:

1. Supported ComfyUI, VideoFree, and external-service versions.
2. Every required/optional model's exact filename or repository ID, official/author download page, and path relative to the ComfyUI root.
3. Every custom-node package's repository name, ComfyUI Manager ID when available, URL, `custom_nodes/<directory>` target, and workflow node class names actually used.
4. Python packages, system programs, cloud keys, and other dependencies.
5. Automatic downloads, license/redistribution restrictions, installation verification, and common missing-dependency errors.

Use relative paths such as `models/diffusion_models/example.safetensors`, never a developer's drive path. Link to official model pages, repositories, or an author's release page, not an unknown file share. Plugin import and gateway startup must not download dependencies. Installation is performed by the user or an agent explicitly authorized by the user.

Suggested template:

```markdown
# <Plugin> Installation

## Models
| Required | Filename/repository ID | Download | ComfyUI-relative path |

## ComfyUI nodes
| Required | Package/Manager ID | Repository | Install path | Node classes used |

## Other dependencies
## Verification
## Licenses and automatic downloads
```

## Manifest registration

```json
{
  "schema_version": 1,
  "id": "my-plugin",
  "version": "1.0.0",
  "name": "My plugin",
  "description": "Plugin description",
  "assets": ["assets/icon.png"],
  "categories": [],
  "capabilities": {},
  "modes": [],
  "actions": []
}
```

`id` and `version` must be unique and contain only letters, digits, `.`, `_`, or `-`. All manifest paths are relative to and confined within the plugin directory.

## Capabilities, modes, and actions

Capabilities go in `capabilities`; processing modes go in `modes`. Compilers, prompt conversion, confirmation corrections, and provider adapters belong inside the plugin. Routes must not inspect model names or read workflow files.

Actions go in top-level `actions`:

```json
{
  "id": "my-plugin.list",
  "name": "List plugin data",
  "scope": "workspace",
  "automation": true,
  "handler": "actions.py:execute",
  "input_schema": {"type": "object", "properties": {}, "additionalProperties": false}
}
```

An action receives framework-validated input and `PluginRuntime`. Validate project, category, media ownership, and applicability using runtime APIs. Destructive actions must default to `automation: false`.

Task-producing actions declare `capability_id` and return `(kind, GenerateRequest)` or `("tts", TTSRequest)`. The framework injects the action's capability ID and name into the job snapshot and runs shared submission validation; callers do not repeat them in `inputs`. Declare `model_name` if the action's algorithm/workflow differs from the capability's default model. Register only capabilities the workflow actually supports. Hidden menu entries remain MCP-discoverable; `ui_hidden` must not be used to conceal an unimplemented feature.

Collaboration results with `ready` must contain complete `optimized_prompt` and `optimized_prompt_zh`. `needs_input` must contain `session_id` and non-empty `questions` (each question has `text` and optional `options`). `runtime.single(request)` creates a session and repairs one structured-format error; custom handlers should use `runtime.repair_result(...)`. `start_progress` takes stage objects, for example `[ {"id": "optimize", "label": "Optimize prompt"} ]`, not a mode-name string.

## PluginRuntime

Do not import backend implementation modules from plugin handlers. Use the stable runtime contract:

```python
def prepare(workflow, config, request, media, job_id, prompt, runtime=None):
    # runtime.plugin_id / project_id / category_id
    # runtime.configuration / runtime.application
    return workflow
```

| API | Purpose |
| --- | --- |
| `plugin_id`, `project_id`, `category_id` | Read-only plugin and current project/category context |
| `configuration` | This plugin's declared settings |
| `application` | Project/application-scoped runtime, described below |
| `single(request)` | Asynchronous shared single-stage collaboration |
| `call_model(messages, max_tokens=2500)` | System LLM without exposing its key |
| `comfyui_request(path, method="GET", body=None)` | Configured ComfyUI integration |
| `job_request(job)`, `jobs()` | Persisted request and visible current-project jobs |
| `update_job_parameters(job, parameters, **metadata)` | Persist plugin-produced job metadata |
| `voice_preset(id)`, `voice_sample(preset)` | Read-only voice preset/sample access |
| `style_items()` | This plugin's style catalog |
| `reference(upload_id, media)` | Validate and resolve an uploaded reference |
| `comfyui_output_file(relative)`, `comfyui_output_files(directory, pattern, detect=True)` | Safe ComfyUI output lookup |
| `free_comfyui_memory()` | Request ComfyUI memory release |
| `session(id)`, `save_session(session, limit=50)` | Platform-managed temporary collaboration session |
| `initial_message(request)`, `staged_context(request)` | Standard collaboration context |
| `repair_result(...)` | Repair structured collaboration output, optionally with a plugin validator |
| `start_progress(...)`, `update_progress(...)`, `finish_progress(...)`, `fail_progress(...)` | Shared collaboration progress |

`runtime.application` provides:

| API | Purpose |
| --- | --- |
| `project(id)`, `projects()` | Project lookup; scoped runtimes reject access outside their project |
| `categories(project_id=None)`, `category(project_id=None, category_id=None)` | Project categories |
| `directory(project_id)`, `category_directory(...)` | Plugin-owned project/category files |
| `resolve_library_path(project_id, relative_path, allowed_suffixes=None)` | Safely resolve an owned project-library file; validates traversal, existence, and extension |
| `job(job_id)`, `jobs(project_id)` | Project jobs |
| `selected()`, `mark(job_id, selected)` | Plugin asset-selection marks |
| `documents(...)`, `document(...)`, `save(...)`, `delete(...)` | Plugin-isolated structured documents |
| `start(key, coroutine)` | Managed background task; one task per plugin/project/key |
| `semaphore()` | Project-scoped concurrency semaphore |
| `invalidate_library()` | Invalidate workbench library cache |

Application plugins may call another plugin's action with `await runtime.execute_action(action_id, inputs, project_id=..., category_id=...)`. The shared executor validates action schema, project ownership, availability, and task submission. Never import another plugin's Python module or call its private function.

`directory()` and `category_directory()` are for the current plugin's files only. Never expose them to clients or write into plugin source. Project-library paths are resource handles, not plugin paths. Store project-relative handles and read through `resolve_library_path()`; do not construct `projects_root` paths or read the database.

Plugins must not read system secrets, use SQLite directly, depend on internal HTTP routes, or place vendor protocols in framework modules. Raise the stable `PluginError` rather than FastAPI exceptions:

```python
from backend.modules.shared.plugin_runtime import PluginError
raise PluginError(422, "The media does not meet this capability's requirements")
```

HTTP/MCP maps errors centrally: `409` for retryable state conflicts, `422` for invalid input/capability constraints, and `502` for plugin/upstream failures.

## Application UI

Contextual `project_tool` panels use the framework's centered dialog. Set
`dialog: {"width":860,"height":740}` in the tool declaration. Each dimension accepts
an integer from 1 to 4096 pixels or `"auto"` for content sizing; defaults are
560 by 680. The host always constrains the panel to its available area. Plugins
own wrapping and internal scrolling; hiding scrollbars must not disable scrolling.

Reuse `@framework` public components and services. `PluginDialog` and `MediaDialog` provide the dialog shell, backdrop, ESC/close behavior, busy state, focus restoration, and content scrolling. The plugin implements only business content. All plugins may use shared notifications and confirmations; do not create duplicate notification containers or use browser `alert()`/`confirm()`.

```js
import { notify, dismissNotification } from '@framework/services/notifications';
notify('Asset saved', { type: 'success' });
const id = notify('Working...', { type: 'info', duration: 0 });
dismissNotification(id);

import { confirmAction } from '@framework/services/confirmations';
if (await confirmAction('Delete this record?', { title: 'Delete', confirmText: 'Delete' })) {
  // Perform the plugin-owned operation after explicit user consent.
}
```

Notification types are `error` (default), `success`, and `info`; title is optional, duration defaults to 4500 ms, and 0 means persistent. At most five notifications are shown. They do not block an operation or replace a confirmation. `confirmAction()` returns `Promise<boolean>`; cancel, ESC, close, and host unmount return false. Requests are serialized; `danger` defaults true. Record the target ID before awaiting confirmation and recheck context afterward. Standalone builds must configure the `@framework` alias and bundle the services; same-window DOM events connect them to the host without sharing a Vue instance.

Other reusable UI includes `SelectMenu.vue`, `MediaPreview.vue`, and `PopoverPanel.vue`. Keep Vue external in independent bundles; do not bundle a second Vue runtime. Shared classes include `ui-button` (`is-primary`, `is-danger`) and `ui-feedback` (`is-error`, `is-success`, `is-info`). Design tokens include `--line-strong`, `--surface-raised`, `--danger`, `--success`, `--info`, `--radius-control`, and `--focus-ring`. Business layout and scoped styles belong to the plugin. Collaboration content fills the host, message history scrolls, and the input stays at the bottom.

The host handles app/collaboration loading, runtime errors, and retry; plugins handle their request errors with a business message. Use `@framework/services/api`'s `gateway`, and `readMediaBlob(url)` for authenticated media. Resource extensions may emit `notice` and `changed` events.

Applications should prefer a standalone bundle in `ui/dist/`, declared as `application.ui.entry`; it is loaded from `/api/v2/plugins/<plugin-id>/ui/...` and does not require a main frontend rebuild. The bundle default-exports a Vue component and contains its JS/CSS/images. The legacy `application.entry` and `resource_entry` modes must point to `ui/*.vue` and require `npm run build` after source changes. Use only one UI implementation mode.

Pages receive `application`, `project`, `category`, `categoryId`, `categories`, category-filtered `jobs`, and a host `resourcePicker`. `scope` may be workspace, project, category, or resource; workspace is an entry/action scope, not data isolation. Category tools must filter and save by `categoryId`. `categoryId: null` means project overview; an empty string is the default category. The shared category selector remounts the page when changed.

Applications may call `resourcePicker({types: ['video'], onSelect})`; omitted types means all. It defaults to current project/category, and users may switch to all project media or project assets. Cancel does not call `onSelect`. Results contain `project_id`, `category_id`, `name`, `type`, `path`, and `url`. `path` is a project resource handle, not an arbitrary path or filesystem path exposed to the browser. Store `path`/`library_path`, display `url`, and resolve files on the backend with `runtime.resolve_library_path(...)`. Missing/deleted files must return a recoverable business error.

An application can declare `requires_project_flags`, for example `ai_created`. It defaults false, is set true for MCP-created projects, and remains false for workbench-created projects. It controls entry visibility; it does not store progress. Use a single progress plugin that displays either project summary or the current category based on context.

## Structured data and lifecycle

Use the framework's plugin document API; do not create framework tables or access SQLite. Documents are isolated by `(plugin_id, project_id, category_id, document_id)`. `save()` validates ownership and stores `category_id`; do not hide it only in custom JSON. Increment `schema_version` when changing a document format and handle migration/compatibility in the plugin.

```python
app = runtime.application
items = app.documents(project_id, category_id)
item = app.document(project_id, document_id, category_id)
app.save({"id": "script-001", "project_id": project_id,
          "category_id": category_id, "schema_version": 1}, references=[])
```

`save()` can declare referenced job IDs and an active flag so the platform prevents deletion while a task uses the source. Clear active state on success, failure, or cancellation. The platform stores JSON but does not parse plugin business content. Start with one document; propose a constrained plugin-namespaced storage extension only if relational queries are truly needed.

Applications may declare `application_lifecycle` hooks for `project_delete` and `category_delete`. Handler signature is `(event, runtime)`; event includes project ID, category ID (null on project deletion), and reason. Hook failure blocks deletion. Use hooks for external data/indexes; the platform then deletes its shared documents. Store plugin files under `runtime.application.directory(project_id)` or `category_directory()`.

`runtime.application.start()` and `semaphore()` create framework-managed cancellable work. The framework owns task state and reclaims it on startup/shutdown. Application startup may restore plugin state. Disabling a plugin hides its entry/actions but preserves its data.

## Testing and release validation

Add focused tests for manifest validation, parameter/media mapping, action handlers, data isolation/lifecycle, and affected UI. Validate discovery output, schemas/defaults, automation visibility, project/category ownership, artifact publication, and useful failures. Plugin load success alone is not sufficient. Do not submit paid/cloud or GPU-heavy generation unless requested.

Run checks proportional to the change; for shared contracts or packaging run the release set:

```powershell
python -m compileall -q backend tests plugins
python -m unittest discover -s tests -p 'test_*.py'
cd frontend
npm run build
cd ..
cmd /c "videofree.bat --check"
```

Run plugin-local tests separately when present. Do not manually edit `static/dist`, runtime data, caches, or generated bundles. After changing plugin Python, manifests, workflows, or fixed assets, drain jobs and restart the gateway. Keep model/node requirements and `INSTALL.md` in the plugin. State plugin type, changed files, capability/action IDs, dependencies, validation, and anything requiring a real ComfyUI environment when handing off.
## UI localization contract

The UI defaults to `zh-CN`. Choosing `en-US` in Settings persists to the framework SQLite settings across restarts and projects. HTTP/MCP IDs, parameter and enum values, prompts and user content remain unchanged.

Register plugin-owned flat string dictionaries:
```json
"localization": {
  "default_locale": "zh-CN",
  "messages": {
    "zh-CN": "locales/zh-CN.json",
    "en-US": "locales/en-US.json"
  }
}
```
For example, use `{"action.save":"保存"}` and `{"action.save":"Save"}`. Pair presentation fields with explicit keys: `"name":"保存", "name_key":"action.save"`. Supported fields: name, label, description, placeholder, help, title, selection_label, mode_name, model_name and provider_name. Translate option labels, never option values or capability/model/mode/action IDs. Pack paths must stay in the plugin's locales directory.

The catalog publishes messages and key metadata; only the browser resolves translations. Fallback order: selected locale, plugin default_locale, original declaration text. Plugins without packs retain their original text.

Plugin UI receives reactive `locale` and `t(key, fallback?, values?)` props. Components using the host Vue may also inject `videofree:ui-context`: locale is a readonly computed ref, t is the same translator. Example: `t('items.count', '{count} items', {count: 3})`. The framework translates declared fields; plugins translate their own buttons, states and empty views using their own packs. Never store translated text as business state, compare translated labels for control flow, or translate prompt syntax.

Language changes must preserve component instances, drafts and timelines. Watch stable IDs rather than translated objects. Independently built plugins should use the props without importing framework source. Updating packs is a plugin update: drain tasks and restart the gateway.

All bundled plugins provide Chinese and English packs. Voice display names, style names and style categories use their owning plugin's dictionary; preset IDs, style prompts and category filter values remain unchanged. Translate fixed progress messages at display time. Keep LLM replies, user content and confirmation drafts in their original language, and format dates with the context locale. In English UI, request errors use curated translations where available; unknown Chinese errors retain their original diagnostics alongside an English summary.

The framework handles `@` mentions in declarative generation forms: uploaded file names are displayed, typing `@` lists uploaded references, and duplicate names receive suffixes. Mentions bind to `upload_id` and become tokens such as `<Picture 1>`, `<Video 1>` and `<Audio 1>` on submission. Neither file names nor model tokens are translated. Removing a mentioned file blocks submission until its marker is removed or a reference is selected again. Plugins do not need to duplicate this logic.

