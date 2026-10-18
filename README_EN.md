# VideoFree

[中文](README.md) · [English](README_EN.md)

Current version: `1.1.0`

**Turn fragmented local AI workflows into complete creative capabilities that people can use, developers can distribute, and agents can call reliably.**

VideoFree is a local AI video creation workspace, capability gateway, and plugin platform. It uses ComfyUI as a generation engine without forcing users to work directly with complex node graphs, model paths, and disconnected workflow files. Models, workflows, parameter forms, prompt expertise, and supporting assets are packaged as installable plugins, while projects, categories, assets, and jobs are managed in one place.

People can create in the workspace, while external agents use the same plugin capabilities, project data, and local media through MCP or HTTP APIs.

## Why VideoFree

### Local AI is powerful, but fragmented

Cloud products choose the model, parameters, and interaction flow for the user. Moving to local creation means facing an overwhelming number of models, workflows scattered across the web, hard-to-read ComfyUI graphs, missing custom nodes, incompatible versions, and model paths that differ from one installation to another.

VideoFree does not replace ComfyUI. It adds a stable product layer on top of it. A tested workflow can be packaged with its input rules, parameters, compiler logic, UI, dependencies, and documentation. Users select a capability like they would in a regular creative application instead of learning its internal graph first.

### Every model speaks a different prompt language

Image, video, speech, and music models use different prompt formats, media roles, and parameter constraints. The same request may need a completely different execution prompt for each model.

A VideoFree plugin can ship model-specific collaboration skills. Users describe the desired scene, motion, dialogue, or music in plain language; the collaboration flow asks for missing information, checks media relationships, and compiles the request into the format expected by the selected model. Model-specific knowledge stays inside the plugin instead of accumulating in the framework.

### Local files, prompts, and production notes quickly become unmanageable

ComfyUI executes workflows well, but it is not a complete video project manager. Images, clips, voices, music, intermediate files, scripts, prompts, references, and chat notes often end up in unrelated folders.

VideoFree organizes creation as **project → category → asset**. A project can represent a film or series, while categories can represent episodes, chapters, or shot groups. Final media is archived automatically. Job records preserve source media, parameters, capability identity, and regeneration lineage. Reusable characters, scenes, and voices can be maintained as project assets. Project plugins can also manage scripts, storyboards, and progress in the current project or category context.

### Agents need a stable capability contract, not raw graph access

Directly manipulating ComfyUI graphs is brittle for agents: node IDs, connections, model filenames, and workflow versions can change at any time.

VideoFree exposes workflows as capabilities with stable IDs, input schemas, and execution contracts. An agent discovers capabilities, uploads media, submits validated inputs, and monitors jobs. VideoFree handles workflow selection, media binding, queues, recovery, error reporting, and result archiving. The workspace, MCP, and HTTP API all share one capability catalog and one job service.

### Workflows become installable products

A single plugin can contain:

- ComfyUI workflows;
- model and capability declarations;
- parameter forms;
- workflow compilers and native executors;
- model-specific prompt and collaboration skills;
- presets, icons, voice samples, and other fixed assets;
- post-processing actions;
- project tools or a complete application UI.

The same plugin can serve people in the workspace and agents through MCP or HTTP.

Plugin development resources:

- [Plugin development guide](plugins/PLUGIN_DEVELOPMENT.md)
- [Plugin protocol](docs/plugin-protocol.md)
- [VideoFree plugin development skill](.agents/skills/videofree-plugin-development/SKILL.md)

## Core capabilities

- Local and cloud image, video, speech, and music generation.
- Declarative capability discovery and parameter validation.
- Model-specific prompt compilation and collaboration.
- Persistent queues, cancellation, restart recovery, and job lineage.
- Project/category media library and reusable project assets.
- Resource actions such as refinement, upscaling, interpolation, and image splitting.
- Application plugins and contextual project tools.
- Shared access through the workspace, MCP, and HTTP API.

## Quick start

VideoFree currently targets Windows GPU workstations and complete release packages.

1. Prepare and start ComfyUI with the models and custom nodes required by the plugins you want to use.
2. Extract the complete VideoFree release package.
3. Double-click `启动VideoFree.cmd`.
4. Open the workspace, create a project, and enter the actual ComfyUI URL in Settings. The common default is `http://127.0.0.1:8189`, but your installation may use another port.
5. Start with a low-resolution image or short clip to verify the environment before running expensive jobs.

The release package includes its Python runtime and does not require a separate Python or Node.js installation. Source deployments must install `requirements.txt` and build the frontend.

The optional companion ComfyUI model/node bundle is currently hosted on Quark Drive:

- URL: <https://pan.quark.cn/s/306e83d5c2ce>
- Extraction code: `5vM9`

Keep model filenames and subdirectories unchanged. Some bundled workflows require SageAttention installed in the Python environment actually used by ComfyUI. Do not install it only into the system Python or upgrade PyTorch/CUDA without checking compatibility.

## Configuration

The launcher reads a root `.env` file. The main options are:

```dotenv
COMFYUI_URL=http://127.0.0.1:8189
MEDIA_GATEWAY_HOST=0.0.0.0
MEDIA_GATEWAY_PORT=8765
MEDIA_GATEWAY_TOKEN=
```

The access token is empty by default. The token saved in Settings is shared by the workspace, HTTP API, and MCP and takes precedence over the environment default. Do not expose an unauthenticated gateway directly to the public internet.

Project media is stored under `data/projects/` unless another library directory is selected in Settings. System settings, projects, and job records are stored in `data/media_gateway.db`. Plugin-owned secrets are stored in each plugin's ignored `.env` file. Fixed plugin resources must remain inside the plugin directory.

## Agent and MCP access

The MCP endpoint starts with the gateway:

```json
{
  "mcpServers": {
    "videofree": {
      "type": "http",
      "url": "http://127.0.0.1:8765/mcp"
    }
  }
}
```

For another machine on the LAN, replace `127.0.0.1` with the gateway machine's real LAN address. If a gateway token is configured, add it as the `X-API-Token` header. Client naming for HTTP MCP transports differs; use the transport name required by your client.

Agents should begin with health and discovery calls, then submit only capability IDs and schemas returned by the running gateway. They should not infer model paths, workflow files, or ComfyUI nodes.

- MCP guide: [.agents/skills/zizai-creation/references/mcp-install.md](.agents/skills/zizai-creation/references/mcp-install.md)
- Direct API skill: [.agents/skills/zizai-creation](.agents/skills/zizai-creation)
- Interactive API documentation: `http://127.0.0.1:8765/docs`
- Capability catalog: `http://127.0.0.1:8765/api/v2/capabilities`

## Plugin installation and development

Each plugin is a complete `plugins/<plugin-id>/` folder. Its manifest, workflows, Python handlers, collaboration skills, UI, icons, presets, and fixed assets must stay inside that folder.

Wait for jobs using the plugin to finish, copy or update the whole folder, restart the gateway, and refresh the workspace. Python plugins are trusted local code, not a sandbox. Plugins do not automatically install models, ComfyUI nodes, or Python packages.

Use the included skill when asking a coding agent to create, migrate, review, or validate a plugin:

> Use `$videofree-plugin-development` to package this ComfyUI workflow as a VideoFree plugin. Keep all model-specific code and assets inside the plugin, expose a stable capability schema, and run the plugin and release checks.

## Community

- AI Arsenal and project updates: [laobanclaw.top](https://laobanclaw.top/)
- VideoFree WeChat group:

<img src="https://laobanclaw.top/videofree/qrcode.jpg" alt="VideoFree WeChat group QR code" width="240" />

The QR code may expire; use the website above for the latest community entry.

## License and third-party boundaries

VideoFree-owned source code is released under [GNU AGPL-3.0](LICENSE). For closed-source integration, enterprise deployment, white-label use, support, or custom development, see the [commercial licensing notice](COMMERCIAL_LICENSE.md).

ComfyUI, community nodes, models, LoRAs, fonts, FFmpeg, and other third-party resources keep their own licenses. The editor is the `plugins/film-studio/` application plugin and distributes its FFmpeg/ffprobe runtime and notices inside the plugin. `.agents/skills/openmontage/` is an independent automation skill and is not a runtime dependency of the editor. See [third-party notices](THIRD_PARTY_NOTICES.md).

Only install plugins from sources you trust. Model and sample-file redistribution rights must be verified separately from VideoFree's source-code license.
