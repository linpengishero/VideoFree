---
name: videofree-plugin-development
description: Develop, migrate, review, or validate VideoFree plugins from ComfyUI workflows or product ideas. Use for generation capabilities, plugin actions, collaboration skills, project tools, and application plugins; keep plugin-owned code, UI, workflows, and fixed assets out of the framework.
---

# VideoFree Plugin Development

Turn a tested workflow or product requirement into a self-contained VideoFree plugin that works in the workspace and, when automation is enabled, through the shared HTTP/MCP capability surface.

## Establish the contract first

Use the user's VideoFree path when supplied. Otherwise search the current workspace and its parents for a directory containing all of `AGENTS.md`, `ARCHITECTURE.md`, `plugins/PLUGIN_DEVELOPMENT.md`, `docs/plugin-protocol.md`, and `plugins/`; that directory is the repository root. Resolve every path below from that root, never from this skill folder.

If the source repository is not available locally, obtain it from the official repository the user prefers:

- GitHub: `https://github.com/linpengishero/VideoFree`
- Gitee mirror: `https://gitee.com/heroofgod_admin/videofree`

Do not guess a local path or treat an installed skill directory as the product source. If cloning or downloading source would change the user's machine and was not part of the request, ask for the repository path or authorization first. After locating the repository, read these files completely before editing:

- `AGENTS.md`
- `ARCHITECTURE.md`
- `plugins/PLUGIN_DEVELOPMENT.md`
- the relevant sections of `docs/plugin-protocol.md`

They respectively define workspace ownership rules, architecture boundaries, the development workflow/runtime surface, and the manifest protocol. Inspect `plugins/<closest-plugin>/` as a current implementation example. Treat current code and repository documents as authoritative; do not rely on copied schemas or an older plugin when they disagree. Do not copy these documents into the skill because that would create a second protocol version.

## Start from one or more ComfyUI workflows

The user may provide one workflow, several related workflows, or a product idea. Preserve the original files as evidence until the plugin is verified. For every supplied workflow:

- accept ComfyUI API JSON directly; when given UI JSON or workflow PNG, extract or export API JSON instead of hand-recreating node graphs;
- identify prompt/media inputs, output nodes, model files, custom-node class names and package IDs, supported roles, resolutions, durations, and parameters;
- use embedded `properties.cnr_id`, `properties.models`, workflow metadata, and official project pages to resolve dependencies, but verify rather than trusting filenames alone;
- decide whether workflows are variants of one capability, separate capabilities, or separate plugins based on their user-visible purpose;
- bundle the tested workflow snapshot in the plugin and bind stable semantic inputs explicitly; do not expose node IDs to users or agents.

Do not infer modes the workflow has not demonstrated. If a required model or node source cannot be identified, report that gap instead of inventing a download link.

Every plugin must include `INSTALL.md`. List every required and optional model, ComfyUI custom-node package, Python/system dependency, and external service. For each model give the exact filename or repository ID, authoritative download URL, and path relative to the ComfyUI root (for example `models/diffusion_models/model.safetensors`). For each custom-node package give its repository/Manager ID, URL, target such as `custom_nodes/ComfyUI-Example`, and the node class names used by the bundled workflows. State when ComfyUI core provides a node, when a component auto-downloads a model, and any license or redistribution restriction. Keep this guide aligned with the actual bundled workflow; never hide dependencies only in chat.

An agent may install documented dependencies when the user's request authorizes installation. Prefer official repositories, preserve expected filenames and subdirectories, verify the result, and never download during plugin import or gateway startup.

## Choose the smallest correct plugin shape

- Use a generation capability for a model workflow that creates image, video, speech, or music jobs.
- Use a plugin action for post-processing or a bounded business operation. Destructive actions are not automation-visible by default.
- Use `project_tool` for a contextual panel tied to the current project/category.
- Use `application` for a full independent product page such as an editor.
- Add custom collaboration only when model-specific prompting, clarification, or confirmation materially improves execution. Keep its skills and UI inside the plugin.
- Combine these shapes in one plugin only when they belong to the same product capability.

Do not add a new framework route, MCP tool, category renderer, or global model rule when the existing capability/action/application contracts can express the feature. If a genuine reusable framework contract is missing, explain the gap and its consumers before changing framework code; obtain user direction when that change expands the requested scope.

## Preserve plugin ownership

Keep all model- or product-specific content under `plugins/<plugin-id>/`:

- `plugin.json` is the only registration source.
- Workflows, compilers, executors, actions, collaboration handlers and skills remain local to the plugin.
- Icons, presets, voice samples, templates, and other fixed resources ship with the plugin and use relative paths.
- Plugin UI implements its business interface. Reuse framework dialogs, notifications, confirmation, API, and style tokens only through the documented stable surface.
- Mutable project/category data uses `runtime.application`; generation outputs use the project library. Never write user data into plugin source directories.
- A plugin must not read the platform database, import another plugin, read system secrets, or import HTTP routes/bootstrap globals.
- Report handler errors with `PluginError`, not FastAPI exceptions.
- Missing optional models, nodes, files, or services are checked when the capability runs and produce actionable errors; plugin import must not download packages, contact services, or start processes.

Plugins are trusted local code, not a sandbox. Preserve third-party licenses and document model, node, binary, font, sample, and workflow redistribution boundaries.

## Implement the complete vertical slice

1. Create or update only `plugins/<plugin-id>/` plus focused tests and protocol documentation that truly changed. Add or update the plugin's `INSTALL.md`.
2. Declare identity, version, capabilities/actions/UI/settings/assets and local handler paths in `plugin.json`.
3. Bind prompts, media, dimensions, seed, duration, and plugin parameters explicitly. Never depend on a user's node numbering beyond the bundled workflow snapshot.
4. Use a plugin compiler only for graph logic that declarative bindings cannot express.
5. Return generation requests to the framework instead of submitting directly. Use `PluginRuntime` for model calls, capability/action invocation, project access, uploads, jobs, styles, voices, and ComfyUI output lookup.
6. For independent application UI, build and distribute `ui/dist/`; do not require a main frontend rebuild. For repository-local legacy Vue entries, follow the current protocol and build process exactly.
7. Give every user-visible plugin entry an icon owned by the plugin. The framework may fall back to the first character only when no icon exists.
8. Add the smallest executable tests for manifest validation, parameter/media mapping, handlers, lifecycle/data isolation, and UI behavior affected by the change.

Do not keep old and new implementations side by side. Do not manually edit `static/dist`, runtime data, caches, or generated bundles.

## Validate and hand off

Run checks proportional to the change, including the full release checks when shared contracts or packaging are affected:

```powershell
python -m compileall -q backend tests plugins
python -m unittest discover -s tests -p 'test_*.py'
cd frontend
npm run build
cd ..
cmd /c "videofree.bat --check"
```

Run plugin-local tests separately when present. A plugin that loads is not necessarily usable: verify discovery output, input Schema, default values, automation visibility, project/category ownership, output publication, and understandable failure messages. Do not submit real paid or GPU-heavy generation unless the user requested it.

Finish by stating the plugin type, files changed, exposed capability/action IDs, the location of `INSTALL.md`, required ComfyUI models/nodes or external services, verification results, and anything that still requires a real environment. Remind the user to drain plugin jobs and restart the gateway after installing or changing plugin Python, manifests, workflows, or fixed assets.
