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
from ...modules.collaboration.analysis import parse_agent_json
from ...modules.collaboration.service import call_agent_model
from ...modules.generation.service import (
    comfy, create_task_package, delete_h3_checkpoint, generation_metadata,
    h3_checkpoint_path, hydrate_job_request, job_execution_plane, registered_workflow, set_status,
    start_direct_generation,
    task_directory, upload_cache_path,
)
from ...modules.shared.schemas import GenerateRequest, H3TranslationRequest, RefineRequest, TTSRequest
from ...modules.projects import ProjectService
from ...integrations.comfyui.compiler import validate_reference_counts
from ...integrations.comfyui.errors import describe_failure
from .dependencies import auth


router = APIRouter()
ARTIFACTS = context.paths.artifacts
TASKS = context.paths.tasks
MAX_TEXT = context.config.max_text
MAX_UPLOAD_BYTES = context.config.max_upload_bytes
MAX_TOTAL_UPLOAD_BYTES = context.config.max_total_upload_bytes
MAX_QUEUE_SIZE = context.config.max_queue_size

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
    if result.get("error"):
        result["error_info"] = describe_failure(str(result["error"]))
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
            ready = bool(safe_request["params"].pop("latent_checkpoint_ready", False))
            safe_request["params"].pop("latent_checkpoint", None)
            safe_request["params"].pop("latent_sha256", None)
            safe_request["params"].pop("latent_checkpoint_owner", None)
            result["latent_checkpoint_ready"] = ready
            for key in ("latent_width", "latent_height", "latent_frames", "latent_fps", "latent_size"):
                value = safe_request["params"].get(key)
                if value is not None:
                    result[key] = value
            result["latent_checkpoint_kind"] = safe_request["params"].get("h3_checkpoint_kind", "")
        result["request"] = safe_request
    return result




def validate_generation_request(kind: str, payload: dict[str, Any]) -> None:
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    for key, minimum, maximum in (("width", 64, 4096), ("height", 64, 4096), ("fps", 1, 120)):
        if key not in params:
            continue
        try:
            value = int(params[key])
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, f"{key} 必须是整数") from exc
        if not minimum <= value <= maximum:
            raise HTTPException(422, f"{key} 必须在 {minimum}-{maximum} 之间")
    if kind == "tts":
        config = registered_workflow("tts", payload.get("mode", ""), payload.get("voice_model", "qwen3_tts"))
        validate_reference_counts(config, 0, 0, 1 if payload.get("reference_audio") else 0)
        return
    if kind == "video":
        model = str(params.get("video_model", "minimax"))
        duration = float(payload.get("duration_seconds", 5) or 5)
        minimum, maximum = (1, 15) if model in {"", "minimax", "minimax-h3"} else (1, 30)
        if not minimum <= duration <= maximum:
            raise HTTPException(422, f"{model or 'minimax'} 视频时长必须在 {minimum}-{maximum} 秒之间")
    model = params.get("image_model", "") if kind == "image" else params.get("video_model", "") if kind == "video" else params.get("music_model", "") if kind == "music" else ""
    variant = params.get("speed", "") if kind == "video" and params.get("video_model", "minimax") != "ltx2_5" else ""
    config = registered_workflow(kind, payload.get("mode", ""), model, variant)
    validate_reference_counts(
        config,
        len(payload.get("references", [])),
        len(params.get("videos", [])) if isinstance(params.get("videos", []), list) else -1,
        len(params.get("audios", [])) if isinstance(params.get("audios", []), list) else -1,
    )


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
        project = ProjectService(context).resolve_job_project(context.current_workspace_id.get(), parent_job_id)
    elif internal_project_id:
        project = context.db.project(internal_project_id)
        if not project or project.get("status") != "active":
            raise HTTPException(409, "任务所属项目不存在或已归档")
    else:
        project = ProjectService(context).current(context.current_workspace_id.get())
    payload["params"] = params
    revision = int(parent.get("revision", 1)) + 1 if parent else 1
    context.jobs[job_id] = {
        "id": job_id, "kind": kind, "status": "queued", "request": payload, "created_at": time.time(),
        "width": params.get("width") if kind in {"image", "video"} else None,
        "height": params.get("height") if kind in {"image", "video"} else None,
        "duration_seconds": payload.get("duration_seconds") if kind == "video" else None,
        "parent_job_id": parent_job_id,
        "revision": revision,
        "project_id": project["id"],
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
    return {"job_id": job_id, "kind": kind, "status": "queued", "job_url": f"/v1/jobs/{job_id}", "project_id": project["id"]}

@router.post("/v1/tts/generate", dependencies=[Depends(auth)])
async def tts(request: TTSRequest): return await submit("tts", request)

@router.post("/v1/image/generate", dependencies=[Depends(auth)])
async def image(request: GenerateRequest): return await submit("image", request)

@router.post("/v1/video/generate", dependencies=[Depends(auth)])
async def video(request: GenerateRequest): return await submit("video", request)

@router.post("/v1/music/generate", dependencies=[Depends(auth)])
async def music(request: GenerateRequest): return await submit("music", request)

@router.get("/v1/jobs/{job_id}", dependencies=[Depends(auth)])
async def job(job_id: str):
    item = context.jobs.get(job_id) or context.db.job(job_id)
    if not item: raise HTTPException(404, "job not found")
    return public_job(item)


@router.post("/v1/agent/translate-h3", dependencies=[Depends(auth)])
async def translate_h3(request: H3TranslationRequest):
    prompt = (
        "Translate the complete Chinese MiniMax H3 draft faithfully into English. "
        "Preserve every section name and its order, <Subject N>, <Picture N>, [Shot N], and all XML-like tags. "
        "Keep Chinese dialogue inside <d>[Chinese]...</d> unchanged. Do not optimize, add, omit, summarize, "
        "or comment. Return one JSON object only: {\"english_prompt\": \"...\"}."
    )
    raw = await asyncio.to_thread(call_agent_model, [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps({"mode": request.mode, "chinese_draft": request.text}, ensure_ascii=False)},
    ], 7000)
    result = parse_agent_json(raw) or {}
    english = str(result.get("english_prompt", "")).strip()
    if not english:
        raise HTTPException(502, "AI 未返回完整英文译稿，请重试")
    return {"english_prompt": english}


def validate_refine_dimensions(params: dict[str, Any], request: RefineRequest) -> None:
    source_width = int(params.get("latent_width") or params.get("width") or 0)
    source_height = int(params.get("latent_height") or params.get("height") or 0)
    if not source_width or not source_height:
        raise HTTPException(409, "初稿缺少 latent 尺寸信息，无法二采")
    source_ratio = source_width / source_height
    if abs(request.width / request.height - source_ratio) / source_ratio > 0.03:
        raise HTTPException(422, "二采分辨率必须保持初稿画幅比例")
    if request.width < source_width or request.height < source_height:
        raise HTTPException(422, "二采分辨率不能低于初稿")
    if request.mode in {"h3_refine", "preview_refine_fast", "preview_refine_stable"} and min(request.width, request.height) > 768:
        raise HTTPException(422, "H3 高清二采短边最高支持 768；更高分辨率请使用 LTX 2.5 超清二采")


@router.post("/v1/jobs/{job_id}/refine", dependencies=[Depends(auth)])
async def refine_job(job_id: str, refine: RefineRequest):
    source = context.jobs.get(job_id) or context.db.job(job_id)
    if not source:
        raise HTTPException(404, "job not found")
    request = hydrate_job_request(source)
    params = dict(request.get("params") or {})
    if source.get("kind") != "video" or source.get("status") != "completed":
        raise HTTPException(409, "只有已完成的视频初稿可以二采")
    if not params.get("latent_checkpoint_ready"):
        raise HTTPException(409, "该任务没有可用的 H3 原生 latent")
    checkpoint = h3_checkpoint_path(str(params.get("latent_checkpoint", "")))
    if not checkpoint:
        raise HTTPException(409, "H3 原生 latent 已不存在，请重新生成初稿")
    validate_refine_dimensions(params, refine)
    checkpoint_kind = str(params.get("h3_checkpoint_kind") or "completed_draft_latent")
    if refine.mode in {"preview_refine_fast", "preview_refine_stable"} and params.get("speed") != "preview":
        raise HTTPException(409, "极速预览专用二采只能用于4步极速预览初稿")
    variant = (
        "staged_refine" if refine.mode == "h3_refine" and checkpoint_kind in {"sigma_intermediate", "denoised_preview_latent"}
        else refine.mode if refine.mode in {"preview_refine_fast", "preview_refine_stable"}
        else "latent_refine" if refine.mode == "h3_refine"
        else "latent_ultra_refine"
    )
    for child in context.db.jobs(limit=None):
        child_params = (child.get("request") or {}).get("params", {})
        if (
            child.get("parent_job_id") == job_id
            and child_params.get("speed") == variant
            and int(child_params.get("width", 0)) == refine.width
            and int(child_params.get("height", 0)) == refine.height
            and child.get("status") in {"queued", "running"}
        ):
            raise HTTPException(409, "相同规格的二采任务正在运行")

    params.update(
        speed=variant,
        refine_mode=refine.mode,
        latent_upscaler=("2d" if refine.mode == "preview_refine_fast" else "3d" if refine.mode == "preview_refine_stable" else refine.upscaler),
        width=refine.width,
        height=refine.height,
        parent_job_id=job_id,
        latent_checkpoint_owner=str(params.get("latent_checkpoint_owner") or job_id),
        latent_checkpoint_ready=False,
        h3_checkpoint_kind="completed_draft_latent",
        h3_resume_stage="post_sampling",
        h3_resume_step=0,
        h3_total_steps=0,
        h3_sigma_schedule_persisted=False,
    )
    if refine.mode == "ltx_ultra":
        request["references"] = []
        params["videos"] = []
        params["audios"] = []
    request["params"] = params
    return await submit("video", GenerateRequest(**request))


@router.post("/v1/jobs/{job_id}/cancel", dependencies=[Depends(auth)])
async def cancel_job(job_id: str):
    item = context.jobs.get(job_id) or context.db.job(job_id)
    if not item:
        raise HTTPException(404, "job not found")
    if item.get("status") not in {"queued", "running"}:
        raise HTTPException(409, "任务已结束，无法取消")
    if job_id not in context.jobs:
        context.jobs[job_id] = item
    previous_status = item["status"]
    set_status(job_id, "cancelled")
    prompt_id = item.get("comfy_prompt_id")
    if prompt_id:
        try:
            await asyncio.to_thread(comfy, "/queue", "POST", json.dumps({"delete": [prompt_id]}).encode())
            if previous_status == "running":
                await asyncio.to_thread(comfy, "/interrupt", "POST", b"{}")
        except Exception:
            pass
    return {"id": job_id, "status": "cancelled"}

@router.get("/v1/jobs/{job_id}/manifest", dependencies=[Depends(auth)])
async def job_manifest(job_id: str):
    item = context.jobs.get(job_id) or context.db.job(job_id)
    if not item:
        raise HTTPException(404, "job not found")
    path = Path(item.get("manifest_path") or (task_directory(job_id) / "manifest.json"))
    if not path.is_file():
        raise HTTPException(404, "task manifest not found")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(500, "task manifest is invalid") from exc

@router.delete("/v1/jobs/{job_id}", dependencies=[Depends(auth)])
async def delete_job(job_id: str):
    item = context.jobs.get(job_id) or context.db.job(job_id)
    if not item:
        raise HTTPException(404, "job not found")
    if item.get('status') in {'queued', 'running'}:
        raise HTTPException(409, 'Cannot delete an active job')
    if any(
        child.get("parent_job_id") == job_id and child.get("status") in {"queued", "running"}
        for child in context.db.jobs(limit=None)
    ):
        raise HTTPException(409, "二采任务仍在运行，暂时不能删除它的初稿")
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
    delete_h3_checkpoint(item)
    task_dir = Path(item.get("task_dir", task_directory(job_id)))
    if task_dir.resolve().parent.parent == TASKS.resolve() and task_dir.is_dir():
        shutil.rmtree(task_dir)


@router.delete("/v1/jobs", dependencies=[Depends(auth)])
async def clear_jobs():
    project_id = ProjectService(context).current(context.current_workspace_id.get())["id"]
    items = context.db.jobs(limit=None, project_id=project_id)
    if any(item.get("status") in {"queued", "running"} for item in items):
        raise HTTPException(409, "仍有任务正在排队或生成，请先取消后再清空工作台")
    for item in items:
        delete_job_files(item)
        context.db.delete_job(item["id"])
        context.jobs.pop(item["id"], None)
    return {"deleted": len(items)}

@router.get("/v1/jobs", dependencies=[Depends(auth)])
async def job_list(limit: int | None = None):
    if limit is not None and (limit < 1 or limit > 500): raise HTTPException(400, "invalid limit")
    project_id = ProjectService(context).current(context.current_workspace_id.get())["id"]
    return {"items": [public_job(item) for item in context.db.jobs(limit=limit, project_id=project_id)]}

@router.get("/v1/artifacts/{name}")
async def artifact(name: str, _: None = Depends(auth)):
    path = ARTIFACTS / Path(name).name
    if not path.exists(): raise HTTPException(404, "artifact not found")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "public, max-age=3600"})

@router.get("/v1/tasks/{task_id}/files/{path:path}", dependencies=[Depends(auth)])
async def task_file(task_id: str, path: str):
    task_root = task_directory(Path(task_id).name).resolve()
    target = (task_root / path).resolve()
    if ((task_root != target and task_root not in target.parents) or not target.is_file()):
        raise HTTPException(404, "task file not found")
    return FileResponse(target, media_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream")


