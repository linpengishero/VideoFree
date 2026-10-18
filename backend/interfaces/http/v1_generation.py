import asyncio
import json
import mimetypes
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ...bootstrap import context
from ...modules.generation.service import (
    cancel_generation, comfy, create_task_package, generation_metadata,
    generation_error_info,
    hydrate_job_request, job_execution_plane, set_status,
    start_direct_generation,
    task_directory, upload_cache_path, validate_reference_counts,
)
from ...modules.projects import ProjectService
from .dependencies import auth


router = APIRouter()
ARTIFACTS = context.paths.artifacts
TASKS = context.paths.tasks
MAX_TEXT = context.config.max_text
MAX_UPLOAD_BYTES = context.config.max_upload_bytes
MAX_TOTAL_UPLOAD_BYTES = context.config.max_total_upload_bytes
MAX_QUEUE_SIZE = context.config.max_queue_size

def _authorize_job(item: dict[str, Any]) -> dict[str, Any]:
    try:
        return ProjectService(context).authorize(str(item.get("project_id") or ""))
    except ValueError as exc:
        raise HTTPException(404, "job not found") from exc

def estimated_data_url_bytes(value: Any) -> int:
    if not isinstance(value, str) or not value.startswith("data:"):
        return 0
    try:
        encoded = value.split(",", 1)[1]
    except IndexError:
        return 0
    return max(0, (len(encoded.rstrip("=")) * 3) // 4)


def upload_reference_size(value: Any) -> int:
    if not isinstance(value, str):
        return 0
    path = upload_cache_path(value)
    if value.startswith("upload:") and not path:
        raise HTTPException(400, "上传素材不存在或已过期，请重新上传")
    return path.stat().st_size if path else estimated_data_url_bytes(value)


def validate_upload_budget(payload: dict[str, Any]) -> None:
    """Reject oversized Base64 payloads before they enter the job queue/DB."""
    values: list[tuple[str, Any]] = []
    values.extend(("参考图", item) for item in payload.get("references", []) if isinstance(item, str))
    values.append(("参考音频", payload.get("reference_audio")))
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    values.extend(("视频素材", item) for item in params.get("videos", []) if isinstance(item, str))
    values.extend(("音频素材", item) for item in params.get("audios", []) if isinstance(item, str))
    total = 0
    for label, value in values:
        size = upload_reference_size(value)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"{label}单文件超过 {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
        total += size
    if total > MAX_TOTAL_UPLOAD_BYTES:
        raise HTTPException(413, f"本次上传总量超过 {MAX_TOTAL_UPLOAD_BYTES // (1024 * 1024)} MB")


def public_job(item: dict[str, Any]) -> dict[str, Any]:
    """Return job metadata without exposing uploaded media payloads."""
    result = dict(item)
    result.pop("_publishing", None)
    if result.get("error"):
        result["error_info"] = generation_error_info(str(result["error"]))
        result["error"] = result["error_info"]["message"]
    request = result.pop("request", None)
    if isinstance(request, dict):
        safe_request = dict(request)
        safe_request.pop("references", None)
        safe_request.pop("reference_audio", None)
        if isinstance(safe_request.get("params"), dict):
            safe_request["params"] = dict(safe_request["params"])
            safe_request["params"].pop("videos", None)
            safe_request["params"].pop("audios", None)
        result["request"] = safe_request
    return result




def validate_generation_request(kind: str, payload: dict[str, Any]) -> None:
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    from ...modules.generation.service import registry_service, validate_voice_preset
    from ...modules.generation.plugins import validate_parameters
    if not params.get("capability_id"):
        raise HTTPException(422, "必须指定插件 capability_id")
    config = registry_service().capability(params["capability_id"], params.get("speed", "") if kind == "video" else "")
    if config["kind"] != kind or config["mode"] != payload.get("mode"):
        raise HTTPException(422, "能力与生成类型或模式不匹配")
    validate_parameters(config, params.get("plugin_parameters", {}))
    if kind == "tts":
        validate_voice_preset(config, str(payload.get("character") or ""))
    for key, minimum, maximum in (("width", 64, 4096), ("height", 64, 4096), ("fps", 1, 120)):
        if key not in params:
            continue
        try:
            value = int(params[key])
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, f"{key} 必须是整数") from exc
        if not minimum <= value <= maximum:
            raise HTTPException(422, f"{key} 必须在 {minimum}-{maximum} 之间")
    if config.get("duration"):
        limits = config["duration"]
        if not limits["min"] <= float(payload.get("duration_seconds", 5)) <= limits["max"]:
            raise ValueError("生成时长超出插件允许范围")
    validate_reference_counts(config, len(payload.get("references", [])),
                              len(params.get("videos", [])) if isinstance(params.get("videos", []), list) else -1,
                              (1 if payload.get("reference_audio") else 0) if "text" in payload else
                              len(params.get("audios", [])) if isinstance(params.get("audios", []), list) else -1)


async def submit(kind: str, request: BaseModel) -> dict[str, Any]:
    assert context.job_queue is not None and context.submission_lock is not None
    async with context.submission_lock:
        try:
            return await _submit(kind, request)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc


async def _submit(kind: str, request: BaseModel) -> dict[str, Any]:
    payload = request.model_dump()
    text = payload.get("text") or payload.get("prompt") or ""
    if len(text) > MAX_TEXT:
        raise HTTPException(413, "文本内容过长")
    validate_upload_budget(payload)
    try:
        validate_generation_request(kind, payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    payload["generation"] = generation_metadata(kind, payload)
    execution_plane = str(payload["generation"].get("execution_plane", "local"))
    if execution_plane == "local" and context.job_queue.qsize() >= MAX_QUEUE_SIZE:
        raise HTTPException(429, f"任务队列已满，最多等待 {MAX_QUEUE_SIZE} 个任务")
    if kind != "tts":
        params = dict(payload.get("params") or {})
        params["source_prompt"] = str(params.get("source_prompt") or text)
        payload["params"] = params
    job_id = f"{kind}-{uuid.uuid4().hex[:12]}"
    params = payload.get("params", {}) if isinstance(payload, dict) else {}
    parent_job_id = (params.get("parent_job_id") if isinstance(params, dict) else None) or payload.get("parent_job_id")
    parent = context.db.job(str(parent_job_id)) if parent_job_id else None
    internal_project_id = str(getattr(request, "internal_project_id", None) or params.pop("_project_id", "") or "")
    if parent_job_id:
        project = ProjectService(context).resolve_job_project(parent_job_id)
    elif internal_project_id:
        try:
            project = ProjectService(context).authorize(internal_project_id)
        except ValueError as exc:
            raise HTTPException(409, "任务所属项目不存在或不属于当前安装实例") from exc
    else:
        try:
            project = ProjectService(context).current()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    payload["params"] = params
    requested_category = getattr(request, "category_id", None)
    if requested_category is None:
        requested_category = params.pop("_category_id", None)
    if parent:
        requested_category = parent.get("category_id") or ""
    try:
        category_id = ProjectService(context).validate_category(project["id"], requested_category)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    payload["category_id"] = category_id
    revision = int(parent.get("revision", 1)) + 1 if parent else 1
    context.jobs[job_id] = {
        "id": job_id, "kind": kind, "status": "queued", "request": payload, "created_at": time.time(),
        "width": params.get("width") if kind in {"image", "video"} else None,
        "height": params.get("height") if kind in {"image", "video"} else None,
        "duration_seconds": payload.get("duration_seconds") if kind == "video" else None,
        "parent_job_id": parent_job_id,
        "revision": revision,
        "project_id": project["id"],
        "category_id": category_id,
    }
    try:
        task_dir = await asyncio.to_thread(create_task_package, context.jobs[job_id], parent_job_id)
    except Exception:
        shutil.rmtree(task_directory(job_id), ignore_errors=True)
        context.jobs.pop(job_id, None)
        raise
    context.jobs[job_id]["task_dir"] = str(task_dir)
    context.jobs[job_id]["manifest_path"] = str(task_dir / "manifest.json")
    # Media is already persisted under the task package. Keep the worker's
    # in-memory request intact, but never duplicate Base64 payloads in SQLite.
    persisted_payload = dict(payload)
    persisted_payload.pop("references", None)
    persisted_payload.pop("reference_audio", None)
    if isinstance(persisted_payload.get("params"), dict):
        persisted_payload["params"] = dict(persisted_payload["params"])
        persisted_payload["params"].pop("videos", None)
        persisted_payload["params"].pop("audios", None)
    try:
        context.db.insert_job({**context.jobs[job_id], "request": persisted_payload})
    except Exception:
        shutil.rmtree(task_dir, ignore_errors=True)
        context.jobs.pop(job_id, None)
        raise
    context.jobs[job_id]["request"] = hydrate_job_request(context.jobs[job_id])
    if job_execution_plane(context.jobs[job_id]) == "cloud":
        start_direct_generation(job_id)
    else:
        context.job_queue.put_nowait(job_id)
    return {"job_id": job_id, "kind": kind, "status": "queued", "job_url": f"/v1/jobs/{job_id}", "project_id": project["id"], "category_id": category_id}

@router.get("/v1/jobs/{job_id}", dependencies=[Depends(auth)])
async def job(job_id: str):
    item = context.jobs.get(job_id) or context.db.job(job_id)
    if not item: raise HTTPException(404, "job not found")
    _authorize_job(item)
    return public_job(item)


@router.post("/v1/jobs/{job_id}/cancel", dependencies=[Depends(auth)])
async def cancel_job(job_id: str):
    item = context.jobs.get(job_id) or context.db.job(job_id)
    if not item: raise HTTPException(404, "job not found")
    _authorize_job(item)
    try:
        return await asyncio.to_thread(cancel_generation, job_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc

@router.get("/v1/jobs/{job_id}/manifest", dependencies=[Depends(auth)])
async def job_manifest(job_id: str):
    item = context.jobs.get(job_id) or context.db.job(job_id)
    if not item:
        raise HTTPException(404, "job not found")
    _authorize_job(item)
    path = Path(item.get("manifest_path") or (task_directory(job_id) / "manifest.json"))
    if not path.is_file():
        raise HTTPException(404, "task manifest not found")
    try:
        return {**json.loads(path.read_text(encoding="utf-8")), "status": item["status"]}
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(500, "task manifest is invalid") from exc

@router.delete("/v1/jobs/{job_id}", dependencies=[Depends(auth)])
async def delete_job(job_id: str):
    item = context.jobs.get(job_id) or context.db.job(job_id)
    if not item:
        raise HTTPException(404, "job not found")
    _authorize_job(item)
    if item.get('status') in {'queued', 'running'} or job_id in context.executing_jobs:
        raise HTTPException(409, 'Cannot delete an active job')
    if any(
        child.get("parent_job_id") == job_id and (child.get("status") in {"queued", "running"}
                                                or child["id"] in context.executing_jobs)
        for child in context.db.jobs(limit=None)
    ):
        raise HTTPException(409, "二采任务仍在运行，暂时不能删除它的初稿")
    try:
        ProjectService(context).check_application_references(item.get('project_id'), {job_id})
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    delete_job_files(item)
    context.db.delete_job(job_id)
    context.jobs.pop(job_id, None)
    return {"id": job_id, "deleted": True}


def delete_job_files(item: dict[str, Any]) -> None:
    job_id = item["id"]
    ProjectService(context).delete_job_published(item)
    artifact_names = [a.get("name") for a in item.get("artifacts", []) if a.get("name")]
    if not artifact_names and item.get("artifact_name"):
        artifact_names = [item["artifact_name"]]
    if not artifact_names:
        artifact_names = context.db.artifact_names(job_id)
    for name in artifact_names:
        path = ARTIFACTS / Path(name).name
        if path.is_file(): path.unlink()
    task_dir = Path(item.get("task_dir", task_directory(job_id)))
    if task_dir.resolve().parent.parent == TASKS.resolve() and task_dir.is_dir():
        shutil.rmtree(task_dir)


@router.delete("/v1/jobs", dependencies=[Depends(auth)])
async def clear_jobs(category_id: str | None = None):
    project_id = ProjectService(context).current()["id"]
    items = context.db.jobs(limit=None, project_id=project_id)
    if category_id is not None:
        try:
            ProjectService(context).validate_category(project_id, category_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        items = [item for item in items if (item.get("category_id") or "") == category_id]
    if any(item.get("status") in {"queued", "running"} or item["id"] in context.executing_jobs for item in items):
        raise HTTPException(409, "仍有任务正在排队或生成，请先取消后再清空工作台")
    try:
        ProjectService(context).check_application_references(project_id, {item['id'] for item in items})
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    for item in items:
        delete_job_files(item)
        context.db.delete_job(item["id"])
        context.jobs.pop(item["id"], None)
    return {"deleted": len(items)}

@router.get("/v1/jobs", dependencies=[Depends(auth)])
async def job_list(limit: int | None = None):
    if limit is not None and (limit < 1 or limit > 500): raise HTTPException(400, "invalid limit")
    project_id = ProjectService(context).current()["id"]
    return {"items": [public_job(item) for item in context.db.jobs(limit=limit, project_id=project_id)]}

@router.get("/v1/artifacts/{name}")
async def artifact(name: str, _: None = Depends(auth)):
    path = ARTIFACTS / Path(name).name
    if not path.exists(): raise HTTPException(404, "artifact not found")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "public, max-age=3600"})

@router.get("/v1/tasks/{task_id}/files/{path:path}", dependencies=[Depends(auth)])
async def task_file(task_id: str, path: str):
    item = context.jobs.get(task_id) or context.db.job(task_id)
    if not item:
        raise HTTPException(404, "task file not found")
    _authorize_job(item)
    task_root = task_directory(Path(task_id).name).resolve()
    target = (task_root / path).resolve()
    if ((task_root != target and task_root not in target.parents) or not target.is_file()):
        raise HTTPException(404, "task file not found")
    return FileResponse(target, media_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream")


