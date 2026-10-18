"""Project and category scoped AI production progress."""
from datetime import datetime, timezone


DOCUMENT_ID = "production-progress"
STATUSES = {"pending", "running", "completed", "failed", "blocked", "skipped"}


def _scope(runtime):
    if not runtime.project_id:
        raise ValueError("当前调用没有项目")
    project = runtime.application.project(runtime.project_id)
    if not project.get("ai_created"):
        raise ValueError("制作进度仅适用于 AI 创建的项目")
    category_id = runtime.category_id or ""
    return project, category_id


async def execute(request, runtime):
    project, category_id = _scope(runtime)
    app = runtime.application
    action = request["action"]["id"].rsplit(".", 1)[-1]
    document = app.document(project["id"], DOCUMENT_ID, category_id) or {
        "id": DOCUMENT_ID,
        "project_id": project["id"],
        "category_id": category_id,
        "schema_version": 1,
        "stages": [],
    }
    if action == "get":
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
                 updated_at=datetime.now(timezone.utc).isoformat())
    stages.sort(key=lambda item: (int(item.get("order", 0)), str(item.get("created_at", "")), str(item.get("id", ""))))
    active = next((item for item in stages if item["status"] == "running"), None)
    total = sum(item["status"] not in {"skipped"} for item in stages)
    completed = sum(item["status"] in {"completed", "skipped"} for item in stages)
    document.update(
        stages=stages,
        status="failed" if any(item["status"] == "failed" for item in stages) else "blocked" if any(item["status"] == "blocked" for item in stages) else "completed" if total and completed == total else "running" if active else "pending",
        percent=round(completed * 100 / total) if total else 0,
        current_stage=active["id"] if active else None,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    app.save(document, references=[], active=False)
    return document
