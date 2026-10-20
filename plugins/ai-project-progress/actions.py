"""Project and category scoped AI production progress."""
from datetime import datetime, timezone


DOCUMENT_ID = "production-progress"
STATUSES = {"pending", "running", "completed", "failed", "blocked", "skipped"}
DEFAULT_STAGES = (
    {"id": "planning", "name": "策划", "status": "pending", "order": 0, "weight": 1},
    {"id": "script", "name": "剧本", "status": "pending", "order": 1, "weight": 1},
    {"id": "storyboard", "name": "分镜", "status": "pending", "order": 2, "weight": 1},
    {"id": "assets", "name": "素材制作", "status": "pending", "order": 3, "weight": 1},
    {"id": "editing", "name": "剪辑包装", "status": "pending", "order": 4, "weight": 1},
    {"id": "review", "name": "检查验收", "status": "pending", "order": 5, "weight": 1},
)


def _scope(runtime):
    if not runtime.project_id:
        raise ValueError("当前调用没有项目")
    project = runtime.application.project(runtime.project_id)
    if not project.get("ai_created"):
        raise ValueError("制作进度仅适用于 AI 创建的项目")
    category_id = runtime.category_id
    return project, category_id


def _document_id(category_id):
    return f"{DOCUMENT_ID}:project" if category_id is None else f"{DOCUMENT_ID}:category"


def _calculate(document):
    stages = list(document.get("stages") or [])
    active = next((item for item in stages if item.get("status") == "running"), None)
    effective = [item for item in stages if item.get("status") != "skipped"]
    total_weight = sum(max(0, float(item.get("weight", 1))) for item in effective)
    completed_weight = sum(max(0, float(item.get("weight", 1))) for item in effective
                           if item.get("status") == "completed")
    percent = round(completed_weight * 100 / total_weight) if total_weight else 0
    if any(item.get("status") == "failed" for item in stages):
        overall = "failed"
    elif any(item.get("status") == "blocked" for item in stages):
        overall = "blocked"
    elif effective and completed_weight == total_weight:
        overall = "completed"
    elif active:
        overall = "running"
    else:
        overall = "pending"
    document.update(status=overall, percent=min(100, percent), current_stage=active["id"] if active else None)
    return document


def _new_document(project, category_id):
    stages = [dict(stage) for stage in DEFAULT_STAGES]
    return {"id": _document_id(category_id), "project_id": project["id"], "category_id": category_id,
            "schema_version": 2, "revision": 0, "stages": stages, "status": "pending", "percent": 0,
            "current_stage": None}


async def execute(request, runtime):
    project, category_id = _scope(runtime)
    app = runtime.application
    action = request["action"]["id"].rsplit(".", 1)[-1]
    document = app.document(project["id"], _document_id(category_id), category_id) or _new_document(project, category_id)
    if action == "get":
        return document
    if action == "summary":
        result = {"project_id": project["id"], "categories": []}
        for category in app.categories(project["id"]):
            item = app.document(project["id"], _document_id(category["id"]), category["id"])
            result["categories"].append({"id": category["id"], "name": category["name"],
                                         "status": (item or {}).get("status", "pending"),
                                         "percent": (item or {}).get("percent", 0)})
        return result
    if action == "plan":
        values = request["inputs"]
        stages = values["stages"]
        ids = [item["id"] for item in stages]
        if len(ids) != len(set(ids)):
            raise ValueError("阶段 ID 不能重复")
        document["stages"] = [dict(item, status=item.get("status", "pending"), weight=item.get("weight", 1))
                               for item in stages]
        document["revision"] = int(document.get("revision", 0)) + 1
        _calculate(document)
        document["updated_at"] = datetime.now(timezone.utc).isoformat()
        app.save(document, references=[], active=False)
        return document
    if action != "update":
        raise ValueError("未知的进度操作")

    values = request["inputs"]
    stages = list(document.get("stages") or [])
    stage = next((item for item in stages if item.get("id") == values["stage_id"]), None)
    if stage is None:
        stage = {"id": values["stage_id"], "created_at": datetime.now(timezone.utc).isoformat(), "order": len(stages)}
        stages.append(stage)
    if "order" in values:
        stage["order"] = values["order"]
    stage.update(name=values["stage_name"], status=values["status"], note=values.get("note", ""),
                 weight=values.get("weight", stage.get("weight", 1)),
                 updated_at=datetime.now(timezone.utc).isoformat())
    stages.sort(key=lambda item: (int(item.get("order", 0)), str(item.get("created_at", "")), str(item.get("id", ""))))
    document["stages"] = stages
    document["revision"] = int(document.get("revision", 0)) + 1
    _calculate(document)
    document["updated_at"] = datetime.now(timezone.utc).isoformat()
    app.save(document, references=[], active=False)
    return document
