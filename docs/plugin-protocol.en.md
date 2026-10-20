# VideoFree Plugin Protocol v1

[中文](plugin-protocol.md) · **English**

This protocol packages local AI models and standalone workflows as stable product capabilities. Workbench users select features instead of editing nodes; agents call capability schemas instead of guessing workflow structure. Plugins own model-specific workflows, prompt rules, UI, and fixed assets. The framework provides shared project, job, media, collaboration, and transport services.

## Installation and boundaries

A plugin is a complete directory under `plugins/<plugin-id>/`. Its `plugin.json`, `INSTALL.md`, workflows, Python compilers, collaboration handlers, skills, UI, and fixed assets ship together. Do not copy plugin-owned files into framework directories.

The platform owns HTTP/MCP transport, project archival, job queues, ComfyUI upload/submit/poll/download, and collaboration sessions, follow-up, and confirmation. A plugin declares capabilities, node bindings, model-specific preparation, and prompt handling. It may use public platform adapters, but must not create another gateway or access the platform database directly.

Before installation or upgrade, drain that plugin's generation and collaboration jobs, copy its complete directory, restart the gateway, and refresh the workbench. Set `enabled: false` to disable a plugin. Do not remove code used by a running job. Invalid plugins are isolated and reported in `GET /api/v2/plugins` under `errors`; online hot-unload is not guaranteed.

Plugin Python handlers run with gateway permissions and are **not sandboxed**. Install trusted code only. Plugins do not automatically install models, ComfyUI nodes, or Python packages. Missing dependencies must be reported when the feature is used; importing a plugin must not download files or start services.

`INSTALL.md` is a required installation contract. List every model and ComfyUI node package actually used by the workflows, whether required or optional, exact names, trusted download URLs, and installation paths relative to the ComfyUI root. Also list Python/system dependencies, external services, automatic downloads, and license restrictions. Explicitly state “none” when a dependency class is absent. Never use developer-machine absolute paths. Update this file whenever workflows, model filenames, or node classes change.

An agent may install dependencies only when authorized by the user. It must follow `INSTALL.md`, verify the installation, and must not install over the plugin import or gateway startup path. Workflow metadata such as `properties.cnr_id` and `properties.models` is a discovery clue; verify download locations against the node/model owner's official source.

The plugin catalog is loaded once into the `ApplicationContext` snapshot during startup. Drain jobs and restart before adding, removing, or updating a plugin. Execution checks the plugin revision and rejects a stale job snapshot.

## Minimal manifest

The following abbreviated example shows the manifest shape; use the current declarations and schemas in this document for a production plugin.

```json
{
  "schema_version": 1,
  "id": "example-image",
  "version": "1.0.0",
  "name": "Example image plugin",
  "categories": [{"id": "design", "name": "Design", "icon": "solar:gallery-linear"}],
  "modes": [{"id": "direct", "name": "Direct generation"}],
  "ui_models": [{
    "id": "example-model",
    "name": "Example model",
    "category": "design",
    "functions": [{"capability_id": "example.image.create", "name": "Text to image"}]
  }],
  "capabilities": {
    "example.image.create": {
      "name": "Example image generation",
      "category": "design",
      "kind": "image",
      "mode": "text_to_image",
      "model_family": "example",
      "file": "workflow.json",
      "compiler": "declarative",
      "processing_modes": ["direct"],
      "references": {"image": {"min": 0, "max": 0}},
      "prompt_bindings": [{"node": "6", "input": "text"}],
      "output_nodes": ["9"]
    }
  }
}
```

`workflow.json` should be a ComfyUI API-format export. Node IDs above are illustrative and must be taken from the plugin's tested workflow.

## Manifest and capability rules

### Identity, handlers, and execution

The plugin declares public `name`, `model_id`, `model_name`, and `provider_name`; the platform does not maintain a built-in model-name table. `model_family` is an internal workflow key, while `model_id` is the public identity. `model_aliases`, `mode_aliases`, `skill_model`, and `skill_mode` may map collaboration names to plugin-owned skill directories. Without overrides, the model family and request mode are used.

All Python handler references use `relative_file.py:function` within the plugin directory and may use plugin-local relative imports. Paths must never escape the plugin.

| Manifest field | Handler contract |
| --- | --- |
| `compiler_handler` | `prepare(workflow, config, request, media, job_id, prompt, runtime=None)`; mutates the workflow in place. System runtime services are injected only when declared. |
| `executor_handler` | `execute(context)` synchronously returns `NativeExecutionResult`. Every non-ComfyUI executor must declare it; there is no vendor allowlist. |
| `speech_handler` | `prepare_speech(request, preset, runtime)` returns `TTSRequest` and may select a plugin-owned voice reference sample. |
| `confirmation_handler` | `confirmation(source, result, runtime)` returns optional overrides for settings, parameters, or lyrics. It may return `capability_id` only to switch to a generation capability registered by the same plugin. |

Native execution types come from `backend.integrations.native`. `NativeExecutionContext` includes `job_id`, `config`, `prompt`, `references`, `params`, `api_key`, `output_dir`, `media_loader`, and `cancelled`. Check cancellation and raise `NativeExecutionCancelled`. Returned paths must be non-empty, exist, and remain under `output_dir`; width and height may also be returned. Plugin settings are injected at execution time and are not stored in the job configuration snapshot.

`runtime.comfyui_request` uses the configured ComfyUI adapter; `runtime.voice_sample(preset)` reads a plugin voice sample. Collaboration may pass a plugin validator to `runtime.repair_result`. Keep model-specific output validation in the plugin. A confirmation hook cannot replace project/session identity and cannot imply user consent.

### UI hierarchy and declarative forms

Generation plugins explicitly declare `ui_models` as **primary category → model → subfeature**. The framework does not infer menus from capability names or model IDs. Each model has a plugin-unique `id`, display `name`, registered `category`, and non-empty `functions`. `selector_order` sorts models in a category (lower values first); at most one model per category may declare `default: true`. If none is declared, the smallest `selector_order` is selected. Each function references a same-category generation capability exactly once; post-processing capabilities cannot be listed.

The first bottom selector chooses a category and the second a model. Expandable labels at the upper left select model subfeatures, peer to prompt-processing modes on the right. Every capability declares `ui: {"version": 1, "fields": [...]}`. Built-in and third-party plugins share the same renderer; no model-specific form is selected by model name. `parameters` defines business types and execution constraints; `ui.fields` defines controls, layout, defaults, and request bindings. Resource editing and post-processing use the same declarations.

Every field has unique `bind`, `component`, and `label`. `section` may be `body`, `settings` (default), or `submit`. Field order determines display order within a section.

| Component | Purpose and main fields |
| --- | --- |
| `textarea`, `text` | Multiline/single-line text; `placeholder`, `rows`, `required`, `maxLength` |
| `number` | Numeric input; `minimum`, `maximum`, `step`, `default` |
| `select` | Options as `[{"value": ..., "label": ...}]`, plus `default` |
| `checkbox` | Boolean switch and `default` |
| `media` | Reference media upload/preview; `media` is image, video, or audio |
| `voice` | Plugin voice selector and sample playback |
| `style` | Shared style-library picker bound to `settings.style_id` |
| `dimensions` | Post-processing target dimensions; `alignment`, `presets` |

Root bindings may be `prompt` or `lyrics`. General settings use `settings.<name>` such as `ratio`, `resolution`, `duration`, `variant`, `voice_id`, or `voice_speed`. Plugin parameters use `parameters.<registered-name>`. `settings` is extensible: each plugin declares its own defaults, choices, and limits; the framework has no model-specific settings allowlist.

Reference fields bind to `settings.reference_image`, `settings.reference_video`, or `settings.reference_audio`. The renderer converts them to request `inputs`; they are not passed as settings. If `references` permits a media type (`max > 0`), declare its media field. Positional media must also declare `input_roles`. The generation toolbar merges media fields into one plus button and opens a shared media dialog grouped by label, media type, and reference limits. The dialog supports upload, removal, preview, and role selection; plugins do not implement a separate reference dialog.

The server fills defaults only for omitted fields and validates required values, enums, and numeric limits using the shared declaration. Voice UI may declare `normal_chars_per_second` (for example `4.5`) for an approximate duration estimate. `ui.prompt_template` may combine selected option prompts using `fields` and an optional `suffix`; an option needs `prompt` in addition to `value` and `label`. Existing user prompt text is not overwritten. Music style, singing mode, and voice texture are declared by the plugin, not frontend constants.

Existing controls can be extended by declarations without a frontend edit. A new control type or execution primitive still requires framework support; JSON does not enable arbitrary code execution. `processing_modes` are prompt-processing choices (for example direct, compilation, or director collaboration), separate from generation subfeatures.

Every generation capability must appear in `ui_models`, or explicitly declare `ui_hidden: true` for API-only use; hidden capabilities must not also appear in a menu. Missing menu declarations are reported at startup, not silently hidden. `ui_hidden` must be boolean. Pure post-processing plugins do not need `ui_models`. Capability discovery returns `selector_model` and `mode_name`; submission continues to use the original `capability_id`.

Additional declaration constraints:

- `schema_version` is `1`. Plugin, version, capability, category, and mode IDs use letters, digits, `.`, `_`, or `-`, are at most 120 characters, and start with a letter or digit. Capability IDs are globally unique. Plugins sharing a primary category must declare it identically. Categories are extensible; `kind` remains a media execution type (`image`, `video`, `tts`, `music`, or `audio`), not a primary category.
- `file`, variants, and handlers are plugin-relative. Workflow files may be JSON or PNG; API JSON is recommended to avoid frontend-specific node conversion.
- `compiler` defaults to `declarative`. Model-specific graph transformation belongs in `compiler_handler`; the framework does not guess based on model name.
- Ratios are positive integer `width:height` values such as `32:9`. Resolution values may be `900P`, `1.5K`, or `4K`; K means 1024 pixels. Images interpret the resolution as width; video P uses the short edge and K uses the long edge. Final dimensions must remain within API limits and satisfy node alignment. Options come from the plugin, not framework name allowlists.
- Speech jobs preserve explicit `capability_id`, `plugin_parameters`, and `api_settings` for execution and regeneration. Speech may use declarative ComfyUI workflows or native executors. Reference audio is persisted and reconstructed during recovery.
- Each plugin declares one `direct` mode. Capabilities reference modes through `processing_modes`; omitted means direct only. Mode names have no platform-specific meaning.
- `parameters` supports string, boolean, integer, and number, with `default`, `required`, `enum`, `minimum`, `maximum`, `maxLength`, and `label`. Unknown or invalid values are rejected. Do not declare reserved names `width`, `height`, `duration`, `fps`, `seed`, `latent_checkpoint`, `latent_sha256`, `music_bpm`, `music_key`, or `music_timesignature`; bind these platform values directly.
- `references` declares min/max by image/video/audio. `input_roles` restricts role names. `media_bindings` maps `{node,input,source_index}`; by default the uploaded filename is written to the input. `connect: true` creates and connects a standard loader node (output defaults to 0). Use a compiler for complex inputs.
- `prompt_bindings` uses the final prompt by default. `source` can select a parameter and `append: true` appends to the existing value. Only declared targets are modified; negative prompts are not overwritten as positive prompts. `{{prompt}}` placeholders in workflow strings are also supported.
- `output_nodes` declares final outputs. `prune_to_outputs: true` keeps their dependency graph. `output_bindings` writes the project output prefix to custom save nodes. The platform sets standard save-node prefixes and archives final artifacts.
- `variants` maps IDs to overrides; `public_variants` restricts exposed tiers. `duration` is `{min,max,default}`. The current shared API accepts 1–360 seconds; resolution and ratio choices come from capability discovery.
- `execution_plane` defaults to `local` and uses the controlled local queue. `cloud` uses cloud scheduling, but does not implement a vendor by itself. Current cloud execution reuses registered native adapters; adding an HTTP vendor still requires a platform integration.

### Voice presets and fixed assets

A speech plugin may declare `"voice_presets": "voices.py:presets"`. This synchronous, no-argument function returns `{preset_id: {"display_name": ..., "instruction": ...}}`. Preset IDs are globally unique and follow plugin ID rules. Optional `model` selects a registered model family (default: plugin ID); `sample_file` points to an audio file inside the plugin. If omitted, no sample is provided and the framework cache is not used.

Fixed files such as voice MP3s must ship with their owning plugin, for example `plugins/cosyvoice3/samples/`. User uploads and generated files belong in `data/`. Declare every fixed relative path in the top-level `assets` array. Startup and release checks verify existence and path containment; declared assets contribute to the plugin revision, and a missing asset prevents registration. The workbench and AI can read presets but cannot globally create, edit, delete, or train them. The built-in `my_voice` preset is no longer distributed; old database rows and caches do not belong to plugin files and user files are not automatically deleted.

`GET /api/v2/plugins/{plugin_id}/presets` and MCP `list_plugin_presets` return declared field choices, plugin voices, and user-created presets for the plugin's category. New plugins do not require a dedicated MCP tool. Generation categories and capability menus are discovered from the catalog.

## Plugin actions and post-processing

Capabilities declare what can be generated; actions declare how plugin business operations are called. Register actions only in top-level `plugin.json.actions`, not inside a capability as `postprocess`. A generation workflow capability may still declare `operation: "postprocess"`.

```json
"actions": [{
  "id": "example.normalize_audio",
  "name": "Normalize audio",
  "scope": "resource",
  "automation": true,
  "capability_id": "example.audio.normalize",
  "source_types": ["tts", "music", "audio"],
  "description": "Normalize loudness",
  "input_schema": {"type": "object", "additionalProperties": false}
}]
```

The plugin must provide the referenced capability/workflow; the platform does not include the algorithm.

- `id` is globally unique, `name` is required, and `description` is plugin-owned. A task-producing action may declare `model_name` to override the workflow/algorithm label in the job snapshot; the task function name uses the action name.
- `scope` is `resource`, `workspace`, or `automation`. `workspace` is an action grouping, not tenant isolation and not a full application page.
- `automation` defaults to false. Only actions explicitly set true are discoverable and executable through MCP. This does not expose plugin preset management.
- `input_schema` uses JSON Schema 2020-12 with an object root. Nested objects/arrays, required fields, and numeric constraints are validated. Only local `#` references are allowed; remote references are forbidden. Missing local references disable the plugin with diagnostics. Prefer `additionalProperties: false`; omitted schema is an unrestricted object.
- At least one of `capability_id` and `handler` is required. A capability ID must belong to this plugin; a handler must resolve inside it. Task-producing handlers must declare `capability_id`.
- Resource actions declare `source_types` (`image`, `video`, `tts`, `music`, `audio`) and require a completed matching source. `source_schema` can constrain source metadata. Use plugin-local `availability_handler` for file/state checks; legacy model-specific `requires_latent` and `preview_only` fields are not supported.
- Optional `ui` supports existing post-processing forms such as `parameters.<name>`, `upscaler`, and `target_size`; it is not an arbitrary application UI engine.

### Shared discovery and execution endpoints

```text
GET  /api/v2/plugin-actions?scope=resource&source_job_id=<job_id>&automation=true
GET  /api/v2/plugin-actions/<action_id>
POST /api/v2/plugin-actions/<action_id>/execute
```

The request body is `{"project_id":"optional","source_job_id":"source-job","inputs":{...}}`. For external media, upload first and pass `source_upload_id` instead of `source_job_id`; the two fields are mutually exclusive. External sources may set `category_id`; post-processing a job retains its original category. Source type is determined from the uploaded file, never a client-supplied model/checkpoint claim.

Use `source_kind=image|video|audio` only to preview available actions for an external source; actual submission validates the file. `include_unavailable=true` is diagnostic: it returns actions with matching source type/schema plus `available` and `reason`, but not actions for another source type. The workbench hides unavailable actions by default.

MCP exposes the same three fixed tools: `list_plugin_actions`, `get_plugin_action`, and `run_plugin_action`. Clients discover actions and follow the returned `input_schema`; they must not guess action IDs. HTTP `automation` only filters listing, whereas MCP discovery and execution both enforce the flag.

Without `project_id`, execution inherits the source job's project, or otherwise the current project. Explicit projects must exist and be active. An action cannot move a source into another project. VideoFree is single-user/single-installation: there is no workspace, multi-tenant, or `workspace_id` parameter, and HTTP, MCP, and the workbench share the same projects.

Task-producing actions return `action_id`, `status`, `job_id`, `job_url`, and `wait_url`; use normal job query/wait APIs. Immediate actions return `action_id`, `status: completed`, and `result`, without `job_id`. Do not treat immediate output as a job or automatically confirm a collaboration session.

### Action handlers and availability

Handlers may be synchronous or asynchronous and receive validated request data plus `PluginRuntime`:

```python
async def inspect(request, runtime):
    return {"project_id": runtime.project_id, "value": request["inputs"]["value"]}
```

A handler may return JSON-compatible data or `(kind, GenerateRequest/TTSRequest)`. The kind must match its registered capability. The framework submits, queues, recovers, and archives generated work; plugins do not create their own generation queue. Without a handler, a resource action may stage source output as an upload reference and submit its declared capability. An action-only plugin may use `categories: []` and `capabilities: {}`.

`availability_handler` is synchronous, read-only, and lightweight. It may inspect registration, source metadata, or local state, but must not probe ComfyUI, access the network, or scan models. Return `{"available": false, "reason": "..."}` when unavailable. Exceptions and invalid results count as unavailable. Discovery and execution use the same check; handlers still validate actual files and backend dependencies at submission time. Runtime configuration for availability, application startup, and resource lifecycle hooks is the current plugin configuration.

Top-level `resource_lifecycle` may declare `completed`, `recover`, and `delete` hooks, each with `(event, runtime)`. `event` contains job/request/config, or null where absent. `completed` runs after generation succeeds but before artifact publication; `recover` runs after startup loads jobs; `delete` runs before source outputs are deleted with a job/category/project. Dispatch goes only to the owning plugin when identity is known. For legacy jobs without identity, the handler must determine ownership. Recovery must be idempotent, offline, and independent of optional backend availability.

Use `runtime.comfyui_output_files(directory, pattern, detect=False)` for local helper-file lookup, `runtime.update_job_parameters(job, parameters, **metadata)` to persist plugin metadata, and `runtime.free_comfyui_memory()` when appropriate. Startup recovery must disable online probing. Paths are confined to the ComfyUI output root.

Completion/recovery hook errors are logged without discarding generated media; deletion hook errors stop deletion. Check ownership and active-job references; never delete a parent helper file borrowed by a child job. The platform publishes all final workflow outputs, including multiple outputs and outputs whose media type differs from the input. Capability/artifact declarations determine their types.

For H3 refinement, `postprocess.py:prepare` follows `(request, runtime)`. Declare target dimensions and upscaler using `action.ui`. A `dimensions` field uses `alignment` and `presets`; `edge` means short edge unless `long_edge: true`. The UI calculates width/height. AI callers pass width, height, and optional upscaler in `inputs`; missing required dimensions return 422. Speech plugins expose `speech_preset`, `speech_describe`, and `speech_clone` actions using their live schemas; these submit jobs directly and do not create collaboration confirmation sessions.

Legacy model generation, `/v1/jobs/{job_id}/refine`, `/api/v2/tts/*`, and `/v1/agent/*` were removed and return 404. Generate through `POST /api/v2/generations` with `capability_id`; use plugin actions for operations. H3 translation is the `h3_translate` action owned by minimax-h3 and calls the system LLM through `PluginRuntime`. Collaboration lifecycle uses `/api/v2/collaborations`; references use `inputs: [{type, upload_id, role}]`; storyboard data uses `settings.shots`.

## Dedicated compilers

A capability may declare `compiler_handler: "compiler.py:prepare"`:

```python
def prepare(workflow, config, request, media, job_id, prompt):
    # Mutate this workflow only. Do not submit a job or download results.
    return workflow
```

The framework order is: load workflow; apply placeholders/fixed instructions; apply input overrides; upload media; bind media; bind prompt; bind parameters; run plugin compiler; bind outputs; prune/normalize; persist execution snapshot; submit. `media` contains uploaded image/video/audio filenames. `request` is usually `GenerateRequest` (`TTSRequest` for built-in speech requests). A built-in compiler may reuse existing platform model adapters; third-party plugins must not duplicate those adapters.

## Processing modes and collaboration

A plugin may register any number of modes:

```json
{"id":"review","name":"Prompt review","handler":"collaboration/handler.py:review"}
```

```python
async def review(request, runtime):
    return await runtime.single(request)
```

Handlers receive `AgentChatRequest` and the platform `PluginRuntime`. Public operations include:

- `await runtime.single(request)`: reuse the shared single-stage collaboration flow.
- `runtime.call_model(messages, max_tokens)`: call the system LLM without exposing its key.
- `runtime.configuration`: this plugin's declared settings mapped from its own `.env`.
- `runtime.session()` / `runtime.save_session()`: use platform-managed temporary collaboration state.
- `runtime.start_progress()`, `update_progress()`, `finish_progress()`, `fail_progress()`: update shared collaboration progress.

Plugins must not read the platform database, HTTP routes, or `ApplicationContext`. Add future framework capabilities only through `PluginRuntime`, so plugins do not bind to internal implementation. For `runtime.single`, put skills inside the plugin at `collaboration/skills/system.md`, `models/<model_family>/model.md`, and `modes/<generation-mode>.md`; `skill_model` and `skill_mode` can override directory names. All calls still use shared collaboration scheduling; the framework does not read skills from a repository-level directory.

### Plugin-owned collaboration UI

When a capability needs model-specific questions, confirmation, or stage display, declare a Vue component inside the plugin:

```json
{"collaboration_ui":"ui/Collaboration.vue"}
```

The path must point to an existing `.vue` file under that plugin's `ui/` directory. The catalog rejects paths outside the directory, non-Vue files, and missing files. Discovery returns `plugin_folder` and `collaboration_ui`; the workbench loads the component dynamically. The plugin owns its template, styles, and model-specific interaction. The framework does not render collaboration DOM based on model name or retain an old model-specific panel.

The component receives read-only `session`, `busy`, `pending`, and `answer` props. It may emit `update:answer`, `answer`, `confirm`, and `new-task`. The framework owns collaboration APIs, polling, recovery, revision checks, and job lifecycle. Plugin UI must not call internal routes or read the database. Without a declared component, only status text is shown.

## Plugin settings

Declare `settings` only when the plugin needs its own settings; the settings page adds a plugin section automatically. Supported field types are `string`, `secret`, `url`, `boolean`, `number`, and `select`:

```json
{
  "settings": {
    "title": "Example provider",
    "description": "Cloud image service",
    "fields": [
      {"key":"SERVICE_API_KEY","label":"API key","type":"secret","required":true,"runtime_key":"api_key"},
      {"key":"SERVICE_BASE_URL","label":"API URL","type":"url","runtime_key":"base_url"}
    ]
  }
}
```

Values are stored in the plugin's `.env`, not the system database or capability/MCP catalog. `runtime_key` determines the name visible to the plugin; secrets are injected only during execution. System settings such as ComfyUI, storage paths, and the shared LLM remain in the framework settings store.

Collaboration handler results must be dictionaries:

- `status: needs_input` includes `session_id` and `questions`, preserves session context, and resumes that session after the user responds.
- `status: ready` includes `optimized_prompt` (execution prompt), `optimized_prompt_zh` (Chinese confirmation text), and `generation_payload` when needed. Follow current platform contracts and do not submit the generation yourself.

The platform projects these results to public states such as `awaiting_input` and `awaiting_confirmation`. External agents cannot bypass confirmation or alter presets. Plugin revisions are checked when resuming, confirming, and queueing; changed files reject stale sessions rather than silently using a different workflow.

## UI, REST, and MCP

### Plugin boundaries and fixed resources

Model-specific prompts, workflow-node recognition, and graph rewriting remain in the plugin. Shared system prompts must not contain model or mode rules. Do not import `backend.bootstrap.context` or the generation service for global state; use the passed `PluginRuntime`. `runtime.style_items()` reads the current plugin's style catalog.

Declare fixed files in the manifest's top-level `assets` array using plugin-relative paths. Missing files prevent registration. Never complete a plugin package from framework caches. Uploads, generated outputs, and database records remain runtime data under `data/`.

Built-in `parameter_bindings` sources are `width`, `height`, `duration`, `fps`, and `seed`. Other values come from validated `plugin_parameters` or internal request parameters. Use a binding's `default` only when no value is supplied; otherwise fail clearly. Plugin-specific defaults such as music/checkpoint selections belong to the plugin manifest.

The plugin may declare `prompt_translation_action` at the top level or on a capability, referencing a non-resource action owned by that plugin. When present, the task editor exposes translation; the action receives `text` and `mode` and returns `english_prompt`. The framework has no model-specific action ID list.

Image styles are plugin-owned. Declare top-level `style_library.directory` pointing to a plugin-local folder containing style JSON and a stable `default_id`. Prompts, preview images, and other fixed assets ship there and are included in `assets`. The framework discovers and applies styles by plugin; it does not scan ComfyUI installation directories, environment variables, or runtime data. A plugin without a style library receives an empty catalog and never falls back to another plugin's styles.

### Workbench applications and project tools

An application may declare `requires_project_flags`; the framework shows it only when the current project has every flag. For example, the AI-progress app uses `ai_created`. Applications are full product pages. A lightweight project/category utility next to the category bar uses `project_tool` and inherits current project/category context; it is not a separate application.

An optional `project_tool.dialog` object configures the centered host panel, for
example `{"width":860,"height":740}`. Each dimension accepts an integer from
1 to 4096 pixels or `"auto"` for content sizing. Defaults are 560 by 680; the
host always limits the panel to its available area. Outer scrollbars are hidden
without disabling scrolling. Plugins own content layout, wrapping and internal
scrolling and should set `min-width:0` on flexible content.

```json
{
  "application": {
    "name": "Editor",
    "icon": "ui/icon.png",
    "entry": "ui/Editor.vue",
    "scope": "project",
    "order": 100,
    "resource_entry": "ui/Selection.vue",
    "source_types": ["video"],
    "selection_label": "Selected for editing",
    "library_outputs": {"directory":"films","filenames":["final.mp4"]},
    "startup": "actions.py:startup"
  }
}
```

`entry` is required; other fields are optional. `scope` is `workspace`, `project`, `category`, or `resource` and defaults to project. A category-scoped application must use the selected category, not treat “all categories” as its default. `order` sorts application links; default is 1000, then plugin ID.

`icon` must be an image within the plugin (`.png`, `.jpg`, `.jpeg`, `.webp`, or `.gif`). The first character of the application name is used only when there is no image. Old `solar:`, `mdi:`, and `lucide:` names remain compatible; new plugins should not depend on framework icon libraries.

Traditional Vue entry points must exist under `plugins/<id>/ui/*.vue`. The repository build scans that folder; after changing such Vue/JS files run `cd frontend; npm run build`. This is not a remote-script or arbitrary runtime installer. Manifest or Python-only changes require a gateway restart, not a frontend rebuild.

The page receives `project`, `category`, `categoryId`, `categories`, `jobs`, and the declared `scope`. `categoryId: null` means project overview; an empty string means the default category; `@public` is not passed as an ordinary category. A shared category selector appears above applications and remounts the page on change.

Application documents are category-isolated. `runtime.application.documents(project_id, category_id=None)`, `document(...)`, and `delete(...)` accept a category; omitting it in a category-scoped runtime uses the current category. `save()` validates project/category ownership and persists `document.category_id`; do not put the category ID only in a custom JSON field.

Applications may declare `application_lifecycle` hooks `project_delete` and `category_delete`. Handler signature is `(event, runtime)`. The event includes `project_id`, `category_id` (null for project deletion), and `reason`. A hook failure stops deletion. Use it to clean external resources/indexes; the platform then deletes shared document data. Save plugin files with `runtime.application.directory(project_id)`; use `category_directory()` for category files.

Applications may ship a standalone UI bundle under `ui/dist/` by declaring `application.ui.entry`, for example `ui/dist/index.js`. It must default-export a Vue component; JavaScript, CSS, and images are served from `/api/v2/plugins/<plugin-id>/ui/...`. Installation does not require rebuilding the main frontend. Without `application.ui`, the traditional `application.entry` compatibility mode remains available.

Application documents receive `schema_version` (default `1`). Increment it when changing data formats and handle migration or compatibility when reading older documents; the platform does not interpret plugin JSON.

Reuse public framework services through `@framework`: `PluginDialog`, `MediaDialog`, `SelectMenu.vue`, `MediaPreview.vue`, `PopoverPanel.vue`, API gateway, notifications, and confirmations. `PluginDialog` owns the modal shell (overlay, ESC, close, busy state, focus return, scrolling); the plugin owns business content. Do not use browser `alert()` or `confirm()`. Notifications are non-blocking (`error` default, `success`, `info`; optional title; default 4500 ms; 0 means persistent; at most five shown). Use `confirmAction()` for user consent; it returns `Promise<boolean>`. Standalone builds must configure the `@framework` alias and bundle these services without a duplicate Vue runtime. Notifications and confirmations communicate with the host through same-window DOM events.

The framework provides shared `ui-button` and `ui-feedback` classes and design tokens such as `--line-strong`, `--surface-raised`, `--danger`, `--success`, `--info`, `--radius-control`, and `--focus-ring`. Business layout and content scrolling remain in plugin-scoped styles. Collaboration content fills the host; messages scroll and the input stays at the bottom. The host handles app/collaboration loading, runtime errors, and retry; plugins handle their own network errors through shared notices. Use `@framework/services/api` and `readMediaBlob(url)` for authenticated media.

Projects may declare `requires_project_flags`. For example, `ai_created` defaults false, is true for MCP-created projects, and false for manually created projects. This flag controls app visibility; it does not store progress. One progress plugin shows project overview when `categoryId` is null and the selected category otherwise; do not split that into two plugins.

The host supplies a `resourcePicker` function to applications. Call it with media `types` and `onSelect`; it defaults to current project/category and lets users switch to all project media or project assets. It does not call the callback when canceled. The returned resource includes `project_id`, `category_id`, `name`, `type`, `path`, and `url`. `path` is a project-relative resource handle, never an arbitrary filesystem path or a browser absolute path. Store `path`/`library_path` in plugin documents; use `url` for display and call backend `runtime.resolve_library_path(project_id, relative_path, allowed_suffixes=...)` for reading, probing, or composition. Handle deleted resources as recoverable business errors.

### Plugin data, file access, and tasks

Use framework plugin-document storage for structured data:

```python
app = runtime.application
items = app.documents(project_id, category_id)
item = app.document(project_id, document_id, category_id)
app.save({"id": "script-001", "project_id": project_id,
          "category_id": category_id, "schema_version": 1}, references=[])
```

Data is isolated by `(plugin_id, project_id, category_id, document_id)`. Do not create framework tables or connect directly to SQLite. If a real workload requires relational queries, propose a plugin-namespaced storage extension before implementation.

`runtime.application` exposes project/category lookup, plugin-owned project/category directories, safe project-library resolution, jobs and selection marks, documents (`documents`, `document`, `save`, `delete`), cancellable background `start(key, coroutine)`, project-scoped `semaphore()`, and library-cache invalidation. `save` accepts task references and an active flag to prevent deletion while work is running; clear active state on success, failure, and cancellation. The platform stores document JSON but does not interpret editor/project-specific content.

Use `runtime.execute_action(action_id, inputs, project_id=..., category_id=..., source_job_id=...)` for cross-plugin actions and `runtime.invoke_capability(capability_id, prompt, inputs=..., settings=..., parameters=..., project_id=..., category_id=..., idempotency_key=...)` for direct generation. The framework still performs schema, availability, source-media, project ownership, and queue validation. Cross-plugin Python imports are forbidden. Application startup hooks may restore state; cancellation and semaphores are managed by `ApplicationContext`. Disabling a plugin hides its entry/actions but does not delete its data.

## Public API and MCP

External agents should normally use MCP rather than installing a separate direct-HTTP skill. HTTP remains the workbench and MCP transport layer; both use the same catalog, validation, and job service. They are not separate generation implementations.

Plugins are discovered from repository-root `plugins/` by default. `MEDIA_GATEWAY_PLUGINS` may select another directory. The old `workflows/plugins/` directory and `MEDIA_GATEWAY_WORKFLOWS` variable are not scanned.

`GET /api/v2/plugins` returns plugins, categories, model registrations, and scan errors. `GET /api/v2/capabilities?category=design` returns capabilities, UI declarations, and public parameters. All plugins share category/model/subfeature selectors; there is no separate plugin-capabilities menu.

```json
{
  "capability_id": "example.image.create",
  "prompt": "A realistic landscape",
  "prompt_processing": "direct",
  "parameters": {"guidance": 4},
  "settings": {"ratio": "16:9", "resolution": "1K"},
  "project_id": "ID returned by the projects API"
}
```

Submit to `POST /api/v2/generations`. Non-direct processing uses the same endpoint and collaboration session/answer/confirmation lifecycle. MCP `list_capabilities` and `submit_generation` share the same catalog and contract; plugins do not create separate MCP generation tools.

Resource editing uses the same UI declaration and parameter bindings. Regeneration may pass `parent_job_id`; the platform fixes the project and category to the parent job and preserves the relationship. A child cannot move output across projects.

The workbench uses `GET /api/v2/collaborations?project_id=<ID>` for active sessions and `POST /api/v2/collaborations/<ID>/cancel` to cancel. The framework owns recovery, polling, and API calls. Questions, progress, confirmation, and error UI belong to the capability plugin's `collaboration_ui`, not a framework panel selected by model name.

The capability registry's sole source is `plugins/*/plugin.json`; there is no `workflows/registry.json` fallback. Processing modes come from plugin declarations, not model-name inference. Python handlers load in per-plugin versioned packages and support relative imports.
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

Voice/style display names and style categories use plugin-owned messages; filtering and submission retain original IDs and values. Translate fixed progress labels at display time, keeping user/LLM content intact. Format dates with the context locale. Preserve untranslated service diagnostics and optionally add a localized summary.

In declarative generation forms, `@` mentions display uploaded file names unchanged across languages. Typing `@` filters uploaded references. Duplicate names receive suffixes, and each mention stays bound to its `upload_id` for the current draft. Submission converts mentions to model tokens such as `<Picture 1>`, `<Video 1>` and `<Audio 1>`, using the current input order within each media type. Removing a mentioned file keeps the marker and blocks submission to prevent accidental rebinding.

