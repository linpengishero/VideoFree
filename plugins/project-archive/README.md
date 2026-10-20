# Creative Archive / 创作档案

Project/category creative records for people and external AI agents. No models,
ComfyUI nodes, binary downloads, or external services are required.

## Scope / 上下文

- `category_id: null`: project overview, common story/world/character rules. No episode information.
- A named category ID: that episode,
  chapter, or production unit. Project common settings are available read-only.
- The project overview and story setting are plain text. Write the project type
  and story format naturally; categories do not implicitly turn a project into a series.
- Data is plugin-namespaced in the framework document store. Deleting a category
  or project removes its documents and history through the platform lifecycle.
  Media is not copied into the plugin directory.

“全部素材”展示项目总览，不展示“本集”。切换分类后展示该分类的剧本、
分镜、提示词和交接记录；同时可查看项目公共设定。人工项目和 AI 项目均可用。

## Document Types / 档案类型

| Type | 内容 |
| --- | --- |
| `profile` | 项目概览，纯文本 |
| `story` | 故事设定，纯文本 |
| `episode` | 仅命名分类：本集信息，纯文本 |
| `script` | 剧本定稿，纯文本；不强制拆场或使用表单 |
| `storyboard` | 稳定 ID 镜头列表、镜头内容、可选剧本/制作信息和镜头组 |
| `prompts` | 独立保存的生图/视频/配音/音乐/音效/模板，按镜头、镜头组、设定或项目关联 |
| `characters` | 角色、道具、音色等设定、固定特征和分类变化 |
| `scenes` | 场景设定、固定特征和分类变化 |
| `continuity` | 决策、完成结果、阻塞、下一步，供外部 AI 接续 |
| `final-package` | 定稿、交付清单、验收要求 |

Shots are managed as a readable list. The main editor uses one content field for
visual action, dialogue, and sound; optional script and production metadata stay
collapsed. Existing visual/dialogue/audio fields are shown together and are only
consolidated when edited. Prompt-specific references are distinct from shot-wide
references. Project-level cast and scene records can be selected as prompt targets
while editing a category. Optional groups can contain
any number of stable shot IDs; creating a group starts with four shots only as a
convenience. Group kinds are `sequence`, `character_views`, and `first_last`.

The UI stores prompts in the separate `prompts` document, linked by stable
`target_id`; it does not duplicate prompt data inside each shot. Each record can
hold a human description, execution prompt, capability/model/mode, parameters,
references, and actual task ID. History previews render readable text instead
of raw JSON. Legacy form-based text documents are converted to readable prose
on read/save without discarding their fields.

The UI displays recorded capability/model/mode, job ID, and parameters as
read-only metadata; external AI can still write these through the existing
document schema. The archive does not automatically execute or track generation.
Reference pickers avoid duplicate handles within each record and show task names.

Document schema version 4 keeps optional shot fields for dialogue turns, speaker
and listener, scene IDs, action start/process/end, required asset IDs, and a
static-frame prompt. The UI places these behind optional advanced sections;
existing records and revision history remain intact.

## Actions / AI 接口

Discover these through the existing `list_plugin_actions`, `get_plugin_action`,
and `run_plugin_action` MCP tools (or their generic HTTP equivalents). All ten
actions are declared in `plugin.json`; no dedicated framework routes are needed.

| Action prefix: `project-archive.` | Purpose |
| --- | --- |
| `get_schema` | Return the authoritative JSON Schema for one document type |
| `get_document` | Current document; missing document has revision 0 |
| `list_documents` | Current scope only, excluding historical snapshots |
| `search` | Search current scope titles/content |
| `get_context` | Project + current category, final records first |
| `save_document` | Replace one whole document, not a JSON patch |
| `finalize_document` | Mark a saved document final; create a new revision |
| `list_versions` | Paginated current and historical revision summaries |
| `get_version` | Read an exact immutable revision |
| `restore_version` | Restore a revision as a new draft; keep history |

Every write requires `expected_revision`. Use `0` for creation, otherwise the
revision returned by `get_document`. A stale write returns 409: re-read and merge
your changes, never blindly overwrite. Saving creates an immutable snapshot of
the replaced revision. `save_document` defaults to draft; pass `status: "final"`
only for approved records. Restoring history does not overwrite that history.

Example `run_plugin_action` payload (replace project/category IDs):

```json
{
  "action_id": "project-archive.save_document",
  "project_id": "project-EXAMPLE",
  "category_id": "category-EXAMPLE",
  "inputs": {
    "document_type": "storyboard",
    "expected_revision": 0,
    "content": {
      "notes": "Four consecutive shots, not character views",
      "shots": [
        {"id": "shot-1", "title": "Arrival", "duration": 5, "visual": "A train arrives"},
        {"id": "shot-2", "title": "Platform", "duration": 4},
        {"id": "shot-3", "title": "Greeting", "duration": 4},
        {"id": "shot-4", "title": "Departure", "duration": 5}
      ],
      "groups": [{"id": "board-1", "title": "Opening", "kind": "sequence", "shot_ids": ["shot-1", "shot-2", "shot-3", "shot-4"]}]
    }
  }
}
```

Call `get_schema` before writing other types. References are ordered objects:
`{"kind":"job|asset|library","id":"stable ID or library path","role":"first frame"}`.
Job references must belong to this project. Asset/library references are handles,
not copied files; resolve them through platform APIs and check their availability
before generating. Removing a shot does not silently retarget existing prompts.

### Resuming an AI task / AI 接续

1. Read project/category IDs explicitly; do not change the user's current project.
2. Use `get_context` with `include` and optionally `shot_id` to read only necessary records.
3. Follow `next_offset` for pagination. If `partial_documents` is nonempty, call
   `get_document` in the indicated scope to fetch that full document. A truncated
   `content` string is a preview, not necessarily valid JSON. `max_chars` limits
   content only, not response metadata.
4. Resolve saved asset/job/library handles through platform APIs. This plugin
   does not submit generation or claim a task succeeded merely because a prompt exists.
5. Save actual task IDs, selected results, decisions, and next actions. Production
   percentages belong to the separate AI progress plugin.

### Local editing / 本地编辑

Unsaved edits are temporarily kept in browser session storage per project,
category and document type, with explicit recovery. Tab switching asks for
confirmation. This is not a server backup: save drafts regularly. Generation
metadata and parameters are read-only; descriptions, execution prompts, and
references remain editable without a raw JSON editor. Histories persist on the server;
deleted projects/categories cannot be restored from the archive UI.

## Verification

```powershell
runtime/python/python.exe -B -m unittest discover -s plugins/project-archive/tests -p 'test_*.py'
node plugins/project-archive/tests/test_archive_ui.cjs
```

The browser test uses the built frontend and mocked APIs, without touching user
projects or generating media. Rebuild frontend assets after changing plugin UI;
restart the gateway after changing backend code or the plugin manifest.
