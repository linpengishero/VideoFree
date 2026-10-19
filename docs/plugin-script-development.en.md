# Script Plugin Development Guide

[中文](plugin-script-development.md) · **English**

This guide helps another AI or developer build a “script” application plugin. Script is only an example; the same contract applies to storyboards, character/scene libraries, research notes, task boards, and other project tools.

Before implementation, ask the development agent to read `.agents/skills/videofree-plugin-development/SKILL.md` and treat the current contracts in `plugins/PLUGIN_DEVELOPMENT.md` and `docs/plugin-protocol.md` as authoritative. This guide adds only the business rules for a category-scoped script tool.

## Purpose

The script plugin appears as a small tool to the right of the category bar in the project workbench. It inherits the current project and category; it is not a full-page application. A project may have many categories (often episodes or versions), and the plugin must never mix their data.

## Files

```text
plugins/script-studio/
  plugin.json
  actions.py
  ui/
    ScriptStudio.vue
    icon.png
```

The plugin supplies its own icon. Prefer `ui/icon.png` at 64x64 or 128x128. If no image is ready, omit `icon`; the framework displays the first character of the plugin name.

## Manifest

```json
{
  "schema_version": 1,
  "id": "script-studio",
  "version": "1.0.0",
  "name": "Script",
  "description": "Manage script content by project category.",
  "assets": ["ui/icon.png"],
  "categories": [],
  "capabilities": {},
  "project_tool": {
    "name": "Script",
    "icon": "ui/icon.png",
    "entry": "ui/ScriptStudio.vue",
    "scope": "category",
    "order": 20
  },
  "actions": []
}
```

`scope: category` is the standard for scripts and storyboards. The small-plugin entry is sorted by `order`. The page always receives current category context. If no specific category is selected, show a selection prompt; do not default to data from every category.

## Vue page context

```js
const props = defineProps({
  project: Object,
  category: Object,
  categoryId: String,
  categories: Array,
  jobs: Array,
  projectTool: Object
})
```

`project` is the current project. `category` is the selected category or `null`; `categoryId: null` means project overview and an empty string means the default category. `categories` is the project category list and `jobs` is filtered to the current category. Switching category remounts the tool page.

## Optional collaboration UI

If the plugin also declares generation capabilities and needs its own question/confirmation UI, add `ui/Collaboration.vue` inside the same plugin and declare `"collaboration_ui": "ui/Collaboration.vue"` on the capability. The component owns only its UI and plugin-specific interaction. It receives `session`, `busy`, `pending`, and `answer`, then emits `update:answer`, `answer`, `confirm`, or `new-task` to request framework lifecycle operations. The framework supplies collaboration state, APIs, and polling; it does not inject another plugin's business UI.

## Structured data storage

Store script content with the framework plugin-document API. Do not connect to SQLite directly or create framework tables:

```python
def save_script(runtime, script):
    runtime.application.save(
        {
            "id": "main-script",
            "project_id": runtime.project_id,
            "category_id": runtime.category_id or "",
            "title": script["title"],
            "scenes": script["scenes"],
        },
        references=[],
    )
```

In a category-scoped runtime, `runtime.application.documents(project_id)`, `document(project_id, id)`, and `delete(project_id, id)` default to the current category. The platform validates project/category ownership and isolates records by `(plugin_id, project_id, category_id, id)`.

## Boundaries

- Do not import `backend.bootstrap`, database objects, or another plugin's code.
- Do not simulate category isolation by keeping the category ID only in a custom JSON property.
- Do not read or modify another plugin's documents.
- The framework handles category deletion. Use document references and active markers to prevent deletion while a task is running.
- Start with one JSON document for structured data. If relational queries are genuinely required, propose a constrained plugin-namespaced storage extension; never create platform tables yourself.

## Verification checklist

1. Create two project categories and save a separate script document in each.
2. After switching categories, only the selected category's script is visible.
3. Delete or archive operations never affect another category's data.
4. With no icon image, the entry shows the first character of the plugin name, not a broken image.
5. Run `python -m compileall -q backend tests`, the backend tests, and `cd frontend; npm run build`.
