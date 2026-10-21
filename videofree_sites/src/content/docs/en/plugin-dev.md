---
title: Build Plugins
lead: "Even plugin development is an agent job now: the repository ships a dedicated skill, and your coding agent analyzes, implements, and tests a debugged ComfyUI workflow end to end. Once registered, workspace users and MCP-connected agents automatically share one stable capability — zero MCP integration code."
order: 3
---

<div class="diagram">
  <div class="dtitle">from workflow to mcp</div>
  <div class="dflow">
    <div class="dbox"><b>ComfyUI workflow</b><small>debugged</small></div>
    <div class="darr">→</div>
    <div class="dbox"><b>Plugin folder</b><small>plugin.json registers it</small></div>
    <div class="darr">→</div>
    <div class="dbox"><b>Gateway scan</b><small>restart to register</small></div>
    <div class="darr">→</div>
    <div class="dbox hot"><b>Workspace + MCP tools</b><small>automatic, zero glue code</small></div>
  </div>
  <div class="dnote">discovered by list_capabilities · inspected by get_capability · submitted by submit_generation — all generic tools</div>
</div>

## <span class="no">1</span>Let your coding agent do it (recommended)

The repository ships `.agents/skills/videofree-plugin-development/`. Install the whole folder into your coding agent's skills directory (Claude Code, Codex, Cursor, …), then send:

> Use $videofree-plugin-development to turn my ComfyUI workflow into a VideoFree Studio plugin. First analyze inputs, outputs, model dependencies, and the right plugin shape; then implement, test, and run the release self-check. All model-specific code and assets must stay inside the plugin folder.

The agent analyzes the workflow, picks the right plugin shape, then writes the implementation and runs the tests. Sections 2–4 below are its ground rules — and your acceptance checklist.

## <span class="no">2</span>Choose the plugin shape

- **Generation plugin**: wraps an image, video, speech, or music workflow;
- **Action plugin**: adds second takes, enhancement, or business operations;
- **Project mini-plugin**: manages scripts, progress, and other data in the current project or category;
- **Application plugin**: owns a full standalone page, like the editor.

## <span class="no">3</span>Keep all model-specific content inside the plugin

A plugin's `plugin.json` is the only registration entry. Workflows, compilers, collaboration skills, Vue pages, icons, presets, and fixed samples must ship with the plugin. Model-specific rules never go into the framework, and plugins never read the platform database or another plugin's code.

Once registered, MCP access is automatic: the capability shows up in `list_capabilities`, agents inspect its input limits with `get_capability`, and submit jobs with `submit_generation` — never touching nodes. Your only job is to get the `plugin.json` fields right.

What models are needed and where they go belongs in the plugin's own `INSTALL.md` — the same file the [installation guide](/en/guide/plugin-install/) tells users and agents to install from.

## <span class="no">4</span>Develop and validate against the real protocol

Detailed fields, runtime interfaces, and UI rules live in the repository: [`plugins/PLUGIN_DEVELOPMENT.md`](https://github.com/linpengishero/VideoFreeStudio/blob/main/plugins/PLUGIN_DEVELOPMENT.md), [`docs/plugin-protocol.md`](https://github.com/linpengishero/VideoFreeStudio/blob/main/docs/plugin-protocol.md), and [`ARCHITECTURE.md`](https://github.com/linpengishero/VideoFreeStudio/blob/main/ARCHITECTURE.md). When done, at minimum verify plugin scanning, related tests, the frontend build (when there is UI), and `videofree.bat --check` (`./videofree.sh --check` on Linux).

To verify the MCP side: have any MCP-capable AI call `list_capabilities` once. If your new capability is in the list and `get_capability` returns its full input schema, the integration is done.

::note
Plugins are trusted local code, not a security sandbox. Drain related jobs before installing or updating, restart the gateway afterwards, and remember plugins never install ComfyUI models or nodes by themselves.
::
