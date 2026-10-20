"""Contextual creative documents and immutable revision snapshots."""
from copy import deepcopy
from datetime import datetime, timezone
import json

from backend.modules.shared.plugin_runtime import PluginError
from .model import TYPES, empty_content, normalize, reference_jobs


def _key(kind, category_id):
    return f"archive:{kind}:{'project' if category_id is None else 'category'}"


def _document(app, project_id, kind, category_id):
    # Project documents have distinct IDs but share the default-category DB bucket.
    return app.document(project_id, _key(kind, category_id), "" if category_id is None else category_id)


def _items(app, project_id, category_id):
    return [doc for doc in app.documents(project_id, "" if category_id is None else category_id)
            if doc.get("id") == _key(doc.get("document_type"), category_id)]


def _text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


def _summary(doc):
    return {key: doc.get(key) for key in ("document_type", "title", "status", "revision", "updated_at")}


def _view(doc, kind):
    if not doc:
        return {"document_type": kind, "title": "", "status": "missing", "revision": 0, "content": empty_content(kind)}
    return dict(doc, content=normalize(kind, doc.get("content", "")))


def _context(app, project, category_id, values):
    include = values.get("include") or list(TYPES)
    records = []
    scopes = [("project", None), ("category", category_id)] if category_id is not None else [("project", None)]
    for scope, scope_id in scopes:
        for kind in include:
            if kind == "episode" and not scope_id:
                continue
            doc = _document(app, project["id"], kind, scope_id)
            if not doc:
                continue
            content = normalize(kind, doc.get("content", ""))
            shot_id = values.get("shot_id")
            if shot_id and kind == "storyboard":
                content["shots"] = [s for s in content.get("shots", []) if s["id"] == shot_id]
                content["groups"] = [g for g in content.get("groups", []) if shot_id in g["shot_ids"]]
            if shot_id and kind == "prompts":
                board = _document(app, project["id"], "storyboard", scope_id)
                board_content = (board or {}).get("content", {})
                groups = board_content.get("groups", []) if isinstance(board_content, dict) else []
                group_ids = {g["id"] for g in groups if shot_id in g["shot_ids"]}
                content["items"] = [p for p in content.get("items", []) if p.get("target_id") in {shot_id, *group_ids} or p.get("purpose") == "template"]
            records.append(dict(_summary(doc), scope=scope, category_id=scope_id, content=_text(content)))
    records.sort(key=lambda doc: doc["status"] != "final")
    offset, limit = values.get("offset", 0), values.get("limit", 10)
    selected = records[offset:offset + limit]
    remaining = values.get("max_chars", 12000)
    result, partial = [], []
    for record in selected:
        if remaining <= 0:
            break
        text = record["content"]
        result.append(dict(record, content=text[:remaining], truncated=len(text) > remaining))
        if len(text) > remaining:
            partial.append({"scope": record["scope"], "document_type": record["document_type"]})
        remaining -= min(remaining, len(text))
    next_offset = offset + len(result)
    return {"project": {"id": project["id"], "name": project.get("name")}, "category_id": category_id,
            "documents": result, "total": len(records), "next_offset": next_offset if next_offset < len(records) else None,
            "truncated": bool(partial) or next_offset < len(records), "partial_documents": partial}


async def execute(request, runtime):
    if not runtime.project_id:
        raise PluginError(422, "当前调用没有项目")
    app, project_id, category_id = runtime.application, runtime.project_id, runtime.category_id
    project = app.project(project_id)
    action = request["action"]["id"].rsplit(".", 1)[-1]
    values = request.get("inputs") or {}
    kind = values.get("document_type")
    if kind and kind not in TYPES:
        raise PluginError(422, "未知档案类型")
    if kind == "episode" and not category_id:
        raise PluginError(422, "分类信息只能在具体分类中保存或读取，项目总览请使用项目概览")
    if action == "get_document":
        return _view(_document(app, project_id, kind, category_id), kind)
    if action in {"list_documents", "search"}:
        docs = _items(app, project_id, category_id)
        if action == "search":
            query = values["query"].casefold()
            docs = [doc for doc in docs if query in _text(doc.get("content", "")).casefold() or query in doc.get("title", "").casefold()]
        return {"project_id": project_id, "category_id": category_id, "items": [_summary(doc) for doc in docs]}
    if action == "get_context":
        return _context(app, project, category_id, values)
    if action == "get_schema":
        from .model import SCHEMAS
        return {"document_type": kind, "content_schema": SCHEMAS[kind], "schema_version": 4}
    if action == "list_versions":
        prefix = _key(kind, category_id) + ":revision:"
        docs = [doc for doc in app.documents(project_id, "" if category_id is None else category_id) if doc["id"].startswith(prefix)]
        current = _document(app, project_id, kind, category_id)
        if current:
            docs.append(current)
        docs.sort(key=lambda doc: doc["revision"], reverse=True)
        offset, limit = values.get("offset", 0), values.get("limit", 20)
        return {"items": [_summary(doc) for doc in docs[offset:offset + limit]], "total": len(docs)}
    if action == "get_version":
        current = _document(app, project_id, kind, category_id)
        version = current if current and current["revision"] == values["revision"] else app.document(project_id, _key(kind, category_id) + f":revision:{values['revision']}", "" if category_id is None else category_id)
        if not version:
            raise PluginError(404, "档案版本不存在")
        return _view(version, kind)
    if action not in {"save_document", "finalize_document", "restore_version"}:
        raise PluginError(422, "未知的创作档案操作")
    async with app.semaphore():
        old = _document(app, project_id, kind, category_id)
        revision = int((old or {}).get("revision", 0))
        if values["expected_revision"] != revision:
            raise PluginError(409, "文档已被其他调用更新，请重新读取后再保存；本地修改未丢弃")
        if action == "save_document":
            content = normalize(kind, values["content"])
            document = dict(old or {}, title=values.get("title", (old or {}).get("title", "")), content=content,
                            status=values.get("status", "draft"))
            explicit = values.get("references", [])
        else:
            if not old:
                raise PluginError(404, "档案不存在")
            document = deepcopy(old)
            explicit = old.get("references", [])
            if action == "restore_version":
                source = await execute({"action": {"id": "get_version"}, "inputs": {"document_type": kind, "revision": values["revision"]}}, runtime)
                document.update(content=source["content"], title=source.get("title", ""), status="draft")
                explicit = source.get("references", [])
            else:
                document["status"] = "final"
        document["content"] = normalize(kind, document["content"])
        refs = reference_jobs(app, project_id, document["content"], explicit)
        document.update(id=_key(kind, category_id), project_id=project_id, category_id=category_id, document_type=kind,
                        revision=revision + 1, schema_version=4, references=refs, updated_at=datetime.now(timezone.utc).isoformat())
        if old:
            snapshot = dict(old, id=_key(kind, category_id) + f":revision:{revision}")
            if not app.document(project_id, snapshot["id"], "" if category_id is None else category_id):
                app.save(snapshot, references=old.get("references", []), active=False)
        app.save(document, references=refs, active=False)
        return document
