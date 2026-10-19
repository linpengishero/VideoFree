# 剧本插件开发规范

[English version](plugin-script-development.en.md) · **中文**

本文档供其他 AI 或开发者实现“剧本”应用插件。剧本只是一个示例；同一协议也适用于分镜、角色库、场景库、研究资料、任务看板等任意项目工具。

建议先让开发智能体读取 `.agents/skills/videofree-plugin-development/SKILL.md`，并以 `plugins/PLUGIN_DEVELOPMENT.md` 和 `docs/plugin-protocol.md` 的当前契约为准；本文只说明分类级剧本工具的业务约束。

## 目标

剧本插件显示在项目工作台分类栏右侧的小插件入口中，并且按当前项目分类隔离。它不是独立应用，不会占据整个工作台。一个项目可以有多个分类（通常代表第 1 集、第 2 集或不同版本），插件不得把不同分类的数据混在一起。

## 目录

```text
plugins/script-studio/
  plugin.json
  actions.py
  ui/
    ScriptStudio.vue
    icon.png
```

图标必须由插件自己提供。推荐 `ui/icon.png`，尺寸 64x64 或 128x128。若暂时没有图片，可以不声明 `icon`，框架会显示插件名称的首字。

## plugin.json

```json
{
  "schema_version": 1,
  "id": "script-studio",
  "version": "1.0.0",
  "name": "剧本",
  "description": "按项目分类管理剧本内容。",
  "assets": ["ui/icon.png"],
  "categories": [],
  "capabilities": {},
  "project_tool": {
    "name": "剧本",
    "icon": "ui/icon.png",
    "entry": "ui/ScriptStudio.vue",
    "scope": "category",
    "order": 20
  },
  "actions": []
}
```

`scope: category` 是剧本和分镜的标准设置。红框入口按 `order` 排序。小插件页面始终收到当前分类上下文；没有选择具体分类时，应显示选择提示，不应默认读取整个项目所有分类。

## Vue 页面上下文

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

其中 `project` 是当前项目，`category` 是当前分类对象（无具体分类时为 `null`），`categoryId` 为 `null` 表示项目总览、空字符串表示默认分类，`categories` 是分类列表，`jobs` 已按当前分类筛选。分类切换会重新挂载小插件页面。

## 生成协作 UI

如果插件同时声明生成能力，并需要自定义追问或确认界面，在同一个插件目录增加 `ui/Collaboration.vue`，然后在对应 capability 中声明 `"collaboration_ui": "ui/Collaboration.vue"`。组件只负责 UI 和插件特有交互，接收 `session`、`busy`、`pending`、`answer`，通过 `update:answer`、`answer`、`confirm`、`new-task` 事件请求框架执行对应生命周期操作。框架提供协作状态、API 和轮询，不会把其他插件的业务 UI 注入这个组件。

## 文档存储

普通剧本内容使用平台提供的插件文档存储，不要直接连接 SQLite，也不要创建框架表：

```python
def save_script(runtime, script):
    runtime.application.save(
        {
            "id": "main-script",
            "project_id": runtime.project_id,
            "category_id": runtime.category_id or "",
            "title": script["title"],
            "scenes": script["scenes"]
        },
        references=[]
    )
```

在带分类的运行时中，`runtime.application.documents(project_id)`、`document(project_id, id)`、`delete(project_id, id)` 会自动限定到当前分类。平台会校验项目、分类归属，并在数据库中以 `(plugin_id, project_id, category_id, id)` 隔离文档。

## 设计边界

- 不直接导入 `backend.bootstrap`、数据库对象或其他插件代码。
- 不把分类 ID 仅保存到自定义 JSON 字段来模拟隔离。
- 不查询或修改其他插件的文档。
- 删除分类由框架处理；插件可通过文档引用和活动标记阻止正在运行的任务被删除。
- 复杂数据先使用一个文档 JSON；确实需要多表查询时再提出受限插件命名空间存储扩展，不得自行建平台表。

## 验证清单

1. 新建两个项目分类，分别保存剧本文档。
2. 切换分类后只能看到当前分类的剧本。
3. 删除或归档时不出现跨分类数据。
4. 无图标图片时红框入口显示“剧”字，而不是破损图片。
5. 运行 `python -m compileall -q backend tests`、后端测试和 `cd frontend; npm run build`。
