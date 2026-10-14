import asyncio
import json
import logging
import mimetypes
import shutil
import socket
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ...bootstrap import context
from ...core.errors import AgentCollaborationCancelled
from ...modules.collaboration.analysis import parse_agent_result, parse_requirements_result
from ...modules.collaboration.prompts import (
    AGENT_MODEL_ALIASES, agent_skill_prompt, h3_quick_prompt,
    requirements_stage_prompt,
)
from ...modules.collaboration.service import (
    call_agent_model, fail_agent_progress, finish_agent_progress,
    initial_agent_message, repair_agent_result, run_h3_production_pipeline,
    staged_generation_context, start_agent_progress, update_agent_progress,
)
from ...modules.generation.service import data_url_bytes, upload_cache_path
from ...modules.shared.schemas import (
    AgentChatRequest, AgentGenerateRequest, AgentSubmittedRequest,
    GenerateRequest, TTSRequest,
)
from ...modules.projects import ProjectService
from .dependencies import auth
from .v1_generation import _submit
from .v1_system import ai_is_configured


router = APIRouter()
logger = logging.getLogger(__name__)
COLLABORATIONS = context.paths.collaborations
UPLOAD_CACHE = context.paths.uploads
MAX_AGENT_QUEUE_SIZE = context.config.max_agent_queue_size

def collaboration_directory(collaboration_id: str) -> Path:
    return COLLABORATIONS / collaboration_id










def validate_agent_generation_context(request: AgentChatRequest) -> None:
    model = AGENT_MODEL_ALIASES.get(request.model, request.model)
    if request.collaboration_mode == "quick" and model != "minimax-h3":
        raise HTTPException(422, "快速转换目前仅支持 MiniMax H3")
    if request.kind == "video" and model == "minimax-h3" and request.duration_seconds > 15:
        raise HTTPException(422, "MiniMax H3 视频时长不能超过 15 秒")








































def persist_agent_references(collaboration_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    references = payload.get("references")
    if not isinstance(references, list) or not references:
        return payload
    root = collaboration_directory(collaboration_id) / "inputs"
    root.mkdir(parents=True, exist_ok=True)
    stored = []
    for index, raw in enumerate(references, 1):
        item = dict(raw) if isinstance(raw, dict) else {}
        value = str(item.get("data_url") or "")
        source = upload_cache_path(value) if value.startswith("upload:") else None
        if source:
            extension = source.suffix
            target = root / f"{index:03d}{extension}"
            shutil.copy2(source, target)
        elif value.startswith("data:"):
            body, media_type = data_url_bytes(value)
            extension = mimetypes.guess_extension(media_type) or Path(str(item.get("name", ""))).suffix or ".bin"
            target = root / f"{index:03d}{extension}"
            target.write_bytes(body)
        else:
            stored.append(item)
            continue
        item["data_url"] = f"collaboration:inputs/{target.name}"
        stored.append(item)
    return {**payload, "references": stored}


def restore_collaboration_media(payload: dict[str, Any], source_request: dict[str, Any]) -> list[Path]:
    """Restore persisted collaboration inputs as upload references for generation."""
    grouped: dict[str, list[str]] = {"image": [], "video": [], "audio": []}
    created: list[Path] = []
    if not isinstance(payload.get("params"), dict):
        payload["params"] = {}
    params = payload["params"]
    needs = {
        "image": not payload.get("references"),
        "video": not params.get("videos"),
        "audio": not (payload.get("reference_audio") if payload.get("mode") == "clone" else params.get("audios")),
    }
    for reference in source_request.get("references", []):
        if not isinstance(reference, dict) or reference.get("kind") not in grouped:
            continue
        if not needs[str(reference["kind"])]:
            continue
        value = str(reference.get("data_url") or "")
        if not value.startswith("collaboration:"):
            continue
        relative = value.split(":", 1)[1].lstrip("/")
        owner = str(source_request.get("_collaboration_id") or "")
        root = collaboration_directory(owner).resolve()
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            continue
        upload_id = uuid.uuid4().hex
        target = UPLOAD_CACHE / f"{upload_id}{path.suffix or '.bin'}"
        shutil.copy2(path, target)
        created.append(target)
        grouped[str(reference["kind"])].append(f"upload:{upload_id}")

    if grouped["image"] and not payload.get("references"):
        payload["references"] = grouped["image"]
    if grouped["video"] and not params.get("videos"):
        params["videos"] = grouped["video"]
    if grouped["audio"]:
        if payload.get("mode") == "clone" and not payload.get("reference_audio"):
            payload["reference_audio"] = grouped["audio"][0]
        elif not params.get("audios"):
            params["audios"] = grouped["audio"]
    return created































































































def public_agent_collaboration(item: dict[str, Any]) -> dict[str, Any]:
    result = item.get("result") if isinstance(item.get("result"), dict) else {}
    source = item.get("request") if isinstance(item.get("request"), dict) else {}
    request_summary = {
        key: source.get(key) for key in (
            "message", "kind", "model", "mode", "duration_seconds", "ratio", "resolution", "params", "collaboration_mode",
        ) if key in source
    }
    request_summary["reference_count"] = len(source.get("references", [])) if isinstance(source.get("references"), list) else 0
    return {
        "id": item["id"],
        "session_id": item["id"],
        "status": item["status"],
        "model": item["model_id"],
        "mode": item["mode_id"],
        "revision": item.get("revision", 0),
        "result": result,
        "request": request_summary,
        "progress": item.get("progress") or {},
        "messages": context.db.collaboration_messages(item["id"]),
        "error": item.get("error", ""),
        "job_id": item.get("job_id"),
        "project_id": item.get("project_id"),
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
    }

async def process_agent_collaboration(collaboration_id: str) -> None:
    started_at = time.time()
    item = context.db.collaboration(collaboration_id)
    if not item or item.get("status") != "queued":
        return
    # Cancellation may race with dequeue. Claiming must be conditional so a
    # cancelled queue item can never be resurrected as running.
    if not context.db.claim_collaboration(collaboration_id):
        return
    logger.info("collaboration started", extra={"collaboration_id": collaboration_id, "stage": "collaboration"})
    request = AgentChatRequest.model_validate(item["request"])
    state = item.get("state") if isinstance(item.get("state"), dict) else {}
    if state.get("id"):
        context.agent_sessions[state["id"]] = state
        request.session_id = state["id"]
    else:
        request.session_id = None
    request.progress_id = collaboration_id
    known_sessions = set(context.agent_sessions)
    if request.session_id:
        known_sessions.discard(request.session_id)

    def take_session_state() -> dict[str, Any]:
        session_id = request.session_id
        if not session_id:
            created = [key for key in context.agent_sessions if key not in known_sessions]
            session_id = created[-1] if created else None
        return context.agent_sessions.pop(session_id, {}) if session_id else {}

    try:
        result = await agent_chat(request)
        current = context.db.collaboration(collaboration_id)
        if not current or current.get("status") == "cancelled":
            take_session_state()
            return
        internal_session_id = result.get("session_id")
        session_state = context.agent_sessions.pop(internal_session_id, {}) if internal_session_id else {}
        status = "awaiting_confirmation" if result.get("status") == "ready" else "needs_input"
        message = str(result.get("optimized_prompt_zh") or result.get("message") or "智能协作已完成").strip()
        context.db.add_collaboration_message(collaboration_id, "assistant", message)
        context.db.update_collaboration(collaboration_id, {
            "status": status,
            "result": result,
            "state": session_state,
            "revision": int(item.get("revision", 0)) + (1 if status == "awaiting_confirmation" else 0),
            "completed_at": time.time(),
        })
        logger.info("collaboration completed", extra={"collaboration_id": collaboration_id, "stage": "collaboration", "duration_seconds": round(time.time() - started_at, 2)})
    except AgentCollaborationCancelled:
        take_session_state()
        current = context.db.collaboration(collaboration_id)
        if current and current.get("status") not in {"cancelled", "abandoned", "interrupted"}:
            context.db.update_collaboration(collaboration_id, {"status": "cancelled", "completed_at": time.time()})
        logger.info("collaboration cancelled", extra={"collaboration_id": collaboration_id, "stage": "collaboration", "duration_seconds": round(time.time() - started_at, 2)})
    except HTTPException as exc:
        session_state = take_session_state()
        current = context.db.collaboration(collaboration_id)
        if current and current.get("status") not in {"cancelled", "abandoned", "interrupted"}:
            context.db.update_collaboration(collaboration_id, {
                "status": "failed", "error": str(exc.detail), "state": session_state,
                "completed_at": time.time(),
            })
    except Exception as exc:
        session_state = take_session_state()
        current = context.db.collaboration(collaboration_id)
        if current and current.get("status") not in {"cancelled", "abandoned", "interrupted"}:
            context.db.update_collaboration(collaboration_id, {
                "status": "failed", "error": str(exc), "state": session_state,
                "completed_at": time.time(),
            })
        logger.exception("collaboration failed", extra={"collaboration_id": collaboration_id, "stage": "collaboration", "duration_seconds": round(time.time() - started_at, 2), "error_code": type(exc).__name__})

async def agent_worker() -> None:
    assert context.agent_queue
    while True:
        collaboration_id = await context.agent_queue.get()
        token = context.current_collaboration_id.set(collaboration_id)
        try:
            await process_agent_collaboration(collaboration_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            item = context.db.collaboration(collaboration_id)
            if item and item.get("status") not in {"cancelled", "abandoned"}:
                context.db.update_collaboration(collaboration_id, {
                    "status": "failed", "error": str(exc), "completed_at": time.time(),
                })
        finally:
            context.current_collaboration_id.reset(token)
            context.agent_queue.task_done()

def close_agent_connection(collaboration_id: str) -> None:
    with context.state_lock:
        connection = context.active_agent_connections.pop(collaboration_id, None)
    if connection:
        try:
            if connection.sock:
                connection.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            connection.close()
        except OSError:
            pass



@router.get("/v1/agent/progress/{progress_id}", dependencies=[Depends(auth)])
async def get_agent_progress(progress_id: str):
    with context.state_lock:
        progress = context.agent_progress.get(progress_id)
        if progress:
            return json.loads(json.dumps(progress, ensure_ascii=False))
    item = context.db.collaboration(progress_id)
    if item and item.get("progress"):
        return item["progress"]
    raise HTTPException(404, "agent progress not found")

@router.get("/v1/agent/collaborations", dependencies=[Depends(auth)])
async def list_agent_collaborations(active: bool = False):
    statuses = ("queued", "running", "needs_input", "awaiting_confirmation") if active else None
    project_id = ProjectService(context).current(context.current_workspace_id.get())["id"]
    items = [
        public_agent_collaboration(item)
        for item in context.db.collaborations(statuses, limit=50)
        if str(item.get("capability_id", "")).startswith("studio.")
        and str(item.get("project_id", "")) == project_id
    ]
    return {"items": items}

@router.get("/v1/agent/collaborations/{collaboration_id}", dependencies=[Depends(auth)])
async def get_agent_collaboration(collaboration_id: str):
    item = context.db.collaboration(collaboration_id)
    if not item or not str(item.get("capability_id", "")).startswith("studio."):
        raise HTTPException(404, "智能协作会话不存在")
    return public_agent_collaboration(item)

@router.post("/v1/agent/collaborations/cancel-all", dependencies=[Depends(auth)])
async def cancel_all_agent_collaborations():
    cancelled = []
    project_id = ProjectService(context).current(context.current_workspace_id.get())["id"]
    for item in context.db.collaborations(("queued", "running"), limit=100):
        if not str(item.get("capability_id", "")).startswith("studio."):
            continue
        if str(item.get("project_id", "")) != project_id:
            continue
        context.db.update_collaboration(item["id"], {
            "status": "cancelled",
            "progress": {**(item.get("progress") or {}), "status": "cancelled", "updated_at": time.time()},
            "completed_at": time.time(),
        })
        close_agent_connection(item["id"])
        cancelled.append(item["id"])
    return {"cancelled": cancelled, "count": len(cancelled)}

async def _enqueue_agent_collaboration(request: AgentChatRequest):
    assert context.agent_queue is not None
    if not ai_is_configured():
        raise HTTPException(422, "请先在设置中配置智能协作的模型服务")
    request_id = request.client_request_id or f"turn-{uuid.uuid4().hex}"
    existing_turn = context.db.collaboration_for_turn(request_id)
    if existing_turn:
        return public_agent_collaboration(existing_turn)
    if context.agent_queue.full():
        raise HTTPException(429, f"智能协作队列已满，最多等待 {MAX_AGENT_QUEUE_SIZE} 个任务")
    if request.session_id:
        item = context.db.collaboration(request.session_id)
        if not item or not str(item.get("capability_id", "")).startswith("studio."):
            raise HTTPException(404, "智能协作会话不存在")
        if item["status"] in {"queued", "running"}:
            return public_agent_collaboration(item)
        if item["status"] in {"cancelled", "submitted"}:
            raise HTTPException(409, "当前会话已经结束，请新建智能协作")
        payload = dict(item["request"])
        payload.update({"message": request.message, "client_request_id": request_id})
        context.db.add_collaboration_message(item["id"], "user", request.message)
        item = context.db.update_collaboration(item["id"], {
            "status": "queued", "request": payload, "error": None,
            "completed_at": None,
        })
        collaboration_id = item["id"]
    else:
        collaboration_id = f"collab-{uuid.uuid4().hex[:16]}"
        try:
            payload = await asyncio.to_thread(persist_agent_references, collaboration_id, request.model_dump())
            project_id = request.project_id or ProjectService(context).current(context.current_workspace_id.get())["id"]
            project = context.db.project(project_id)
            if not project or project.get("status") != "active":
                raise HTTPException(409, "任务所属项目不存在或已归档")
            payload.setdefault("params", {})["_project_id"] = project_id
            item = context.db.create_collaboration({
                "id": collaboration_id,
                "capability_id": f"studio.{request.kind}",
                "model_id": AGENT_MODEL_ALIASES.get(request.model, request.model),
                "mode_id": request.mode,
                "status": "queued",
                "project_id": project_id,
                "request": payload,
                "client_request_id": request_id,
            })
        except Exception:
            shutil.rmtree(collaboration_directory(collaboration_id), ignore_errors=True)
            raise
        context.db.add_collaboration_message(collaboration_id, "user", request.message)
    context.db.save_collaboration_turn(request_id, collaboration_id)
    context.agent_queue.put_nowait(collaboration_id)
    return public_agent_collaboration(context.db.collaboration(collaboration_id))

@router.post("/v1/agent/collaborations", status_code=202, dependencies=[Depends(auth)])
async def enqueue_agent_collaboration(request: AgentChatRequest):
    assert context.submission_lock is not None
    async with context.submission_lock:
        return await _enqueue_agent_collaboration(request)

async def _enqueue_existing_agent_collaboration(collaboration_id: str, request: AgentChatRequest) -> dict[str, Any]:
    assert context.agent_queue is not None
    if not ai_is_configured():
        raise HTTPException(422, "请先在设置中配置智能协作的模型服务")
    if context.agent_queue.full():
        raise HTTPException(429, f"智能协作队列已满，最多等待 {MAX_AGENT_QUEUE_SIZE} 个任务")
    item = context.db.collaboration(collaboration_id)
    if not item:
        raise HTTPException(404, "智能协作会话不存在")
    request_id = request.client_request_id or f"turn-{uuid.uuid4().hex}"
    existing = context.db.collaboration_for_turn(request_id)
    if existing:
        return existing
    payload = await asyncio.to_thread(persist_agent_references, collaboration_id, request.model_dump())
    previous = item.get("request", {})
    source_request = previous.get("params", {}).get("_source_request", previous) if isinstance(previous, dict) else {}
    payload.setdefault("params", {})["_source_request"] = source_request
    context.db.update_collaboration(collaboration_id, {
        "status": "queued", "request": payload, "error": None, "completed_at": None,
    })
    context.db.save_collaboration_turn(request_id, collaboration_id)
    context.agent_queue.put_nowait(collaboration_id)
    return context.db.collaboration(collaboration_id)

async def enqueue_existing_agent_collaboration(collaboration_id: str, request: AgentChatRequest) -> dict[str, Any]:
    assert context.submission_lock is not None
    async with context.submission_lock:
        return await _enqueue_existing_agent_collaboration(collaboration_id, request)

async def cancel_existing_agent_collaboration(collaboration_id: str) -> dict[str, Any]:
    item = context.db.collaboration(collaboration_id)
    if not item:
        raise HTTPException(404, "智能协作会话不存在")
    if item["status"] in {"queued", "running"}:
        item = context.db.update_collaboration(collaboration_id, {
            "status": "cancelled", "completed_at": time.time(),
            "progress": {**(item.get("progress") or {}), "status": "cancelled", "updated_at": time.time()},
        })
        close_agent_connection(collaboration_id)
    return item

async def delete_existing_agent_collaboration(collaboration_id: str) -> bool:
    deleted = context.db.delete_collaboration(collaboration_id)
    if deleted:
        await asyncio.to_thread(shutil.rmtree, collaboration_directory(collaboration_id), True)
    return deleted

@router.post("/v1/agent/collaborations/{collaboration_id}/cancel", dependencies=[Depends(auth)])
async def cancel_agent_collaboration(collaboration_id: str):
    item = context.db.collaboration(collaboration_id)
    if not item or not str(item.get("capability_id", "")).startswith("studio."):
        raise HTTPException(404, "智能协作会话不存在")
    if item["status"] not in {"queued", "running"}:
        return public_agent_collaboration(item)
    progress = item.get("progress") if isinstance(item.get("progress"), dict) else {}
    progress = {**progress, "status": "cancelled", "updated_at": time.time()}
    updated = context.db.update_collaboration(collaboration_id, {
        "status": "cancelled", "progress": progress, "completed_at": time.time(),
    })
    close_agent_connection(collaboration_id)
    return public_agent_collaboration(updated)

@router.post("/v1/agent/collaborations/{collaboration_id}/abandon", dependencies=[Depends(auth)])
async def abandon_agent_collaboration(collaboration_id: str):
    item = context.db.collaboration(collaboration_id)
    if not item or not str(item.get("capability_id", "")).startswith("studio."):
        raise HTTPException(404, "智能协作会话不存在")
    if item["status"] == "submitted":
        return public_agent_collaboration(item)
    updated = context.db.update_collaboration(collaboration_id, {
        "status": "abandoned", "completed_at": time.time(),
        "progress": {**(item.get("progress") or {}), "status": "abandoned", "updated_at": time.time()},
    })
    close_agent_connection(collaboration_id)
    return public_agent_collaboration(updated)

@router.post("/v1/agent/collaborations/{collaboration_id}/generate", status_code=202, dependencies=[Depends(auth)])
async def generate_agent_collaboration(collaboration_id: str, request: AgentGenerateRequest):
    assert context.submission_lock is not None and context.job_queue is not None
    async with context.submission_lock:
        item = context.db.collaboration(collaboration_id)
        if not item or not str(item.get("capability_id", "")).startswith("studio."):
            raise HTTPException(404, "智能协作会话不存在")
        if item.get("job_id"):
            existing = context.jobs.get(item["job_id"]) or context.db.job(item["job_id"])
            if existing:
                return {"job_id": existing["id"], "kind": existing["kind"], "status": existing["status"], "reused": True}
        if item["status"] != "awaiting_confirmation":
            raise HTTPException(409, "当前智能协作方案尚未达到可提交状态")
        if int(item.get("revision", 0)) != request.revision:
            raise HTTPException(409, f"方案版本已更新，当前版本为 {item.get('revision', 0)}")
        model = TTSRequest if request.kind == "tts" else GenerateRequest
        payload = json.loads(json.dumps(request.payload, ensure_ascii=False))
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        plan = result.get("production_plan") if isinstance(result.get("production_plan"), dict) else {}
        requirements = plan.get("requirements") if isinstance(plan.get("requirements"), dict) else {}
        selected_skills = plan.get("selected_skills") if isinstance(plan.get("selected_skills"), list) else []
        martial_plan = requirements.get("martial_arts_plan") if isinstance(requirements.get("martial_arts_plan"), dict) else {}
        payload.setdefault("params", {}).update(
            director_skills=[str(value) for value in selected_skills],
            martial_arts_required=bool(martial_plan.get("required")),
            _project_id=str(item.get("request", {}).get("params", {}).get("_project_id", "")),
        )
        source_request = {**item.get("request", {}), "_collaboration_id": collaboration_id}
        restored_uploads = await asyncio.to_thread(restore_collaboration_media, payload, source_request)
        try:
            created = await _submit(request.kind, model.model_validate(payload))
        except ValueError as exc:
            for path in restored_uploads:
                path.unlink(missing_ok=True)
            raise HTTPException(422, str(exc)) from exc
        except Exception:
            for path in restored_uploads:
                path.unlink(missing_ok=True)
            raise
        context.db.update_collaboration(collaboration_id, {
            "status": "submitted", "job_id": created["job_id"], "completed_at": time.time(),
        })
        return created

@router.post("/v1/agent/collaborations/{collaboration_id}/submitted", dependencies=[Depends(auth)])
async def submit_agent_collaboration(collaboration_id: str, request: AgentSubmittedRequest):
    item = context.db.collaboration(collaboration_id)
    if not item or not str(item.get("capability_id", "")).startswith("studio."):
        raise HTTPException(404, "智能协作会话不存在")
    updated = context.db.update_collaboration(collaboration_id, {
        "status": "submitted", "job_id": request.job_id, "completed_at": time.time(),
    })
    return public_agent_collaboration(updated)

@router.post("/v1/agent/chat", dependencies=[Depends(auth)])
async def agent_chat(request: AgentChatRequest):
    validate_agent_generation_context(request)
    progress_id = request.progress_id or f"progress-{uuid.uuid4().hex[:12]}"
    existing = context.agent_sessions.get(request.session_id) if request.session_id else None
    normalized_model = AGENT_MODEL_ALIASES.get(request.model, request.model)
    pipeline = (
        str(existing.get("pipeline")) if existing
        else "h3-quick" if normalized_model == "minimax-h3" and request.collaboration_mode == "quick"
        else "h3-staged" if normalized_model == "minimax-h3"
        else "single"
    )
    start_agent_progress(progress_id, pipeline)
    try:
        if request.session_id:
            session = context.agent_sessions.get(request.session_id)
            if not session:
                raise ValueError("智能体会话已失效，请重新发送生成需求")
            message_key = "requirements_messages" if session.get("pipeline") == "h3-staged" else "messages"
            session[message_key].append({"role": "user", "content": request.message})
            if session.get("pipeline") == "h3-staged" and session.get("last_final_result"):
                session[message_key].insert(-1, {
                    "role": "user",
                    "content": "当前已生成的中英文成稿如下。后续修改必须以它为基线，只修改用户明确提出的部分：\n"
                    + json.dumps(session["last_final_result"], ensure_ascii=False),
                })
            session.setdefault("user_requests", []).append(request.message)
        else:
            session_id = f"agent-{uuid.uuid4().hex[:12]}"
            session = {
                "id": session_id,
                "created_at": time.time(),
                "model": normalized_model,
                "mode": request.mode,
                "pipeline": pipeline,
                "generation": staged_generation_context(request),
                "user_requests": [request.message],
            }
            if session["pipeline"] == "h3-staged":
                session["requirements_messages"] = [
                    {"role": "system", "content": requirements_stage_prompt()},
                    {"role": "user", "content": initial_agent_message(request)},
                ]
            else:
                session["messages"] = [
                    {"role": "system", "content": (
                        h3_quick_prompt(request.mode)
                        if session["pipeline"] == "h3-quick"
                        else agent_skill_prompt(request.model, request.mode)
                    )},
                    {"role": "user", "content": initial_agent_message(request)},
                ]
            context.agent_sessions[session_id] = session
            if len(context.agent_sessions) > 50:
                oldest = min(context.agent_sessions.values(), key=lambda item: item["created_at"])
                context.agent_sessions.pop(oldest["id"], None)

        if session.get("pipeline") == "h3-staged":
            messages = session["requirements_messages"]
            source_text = "\n".join(str(item) for item in session.get("user_requests", []))
            update_agent_progress(progress_id, "requirements", "running", "正在策划需求、素材职责、声音与可行性")
            content = await asyncio.to_thread(call_agent_model, messages, 6000)
            requirements = parse_requirements_result(content, session["generation"], source_text)
            if requirements["status"] == "needs_input" and not requirements["questions"] and not requirements.get("_contract_issues"):
                correction = {"role": "user", "content": (
                    "You returned needs_input without any question. If all necessary choices are resolved, "
                    "return status=ready with every required field complete. Otherwise ask one necessary question "
                    "with at least two clickable options. Return the complete corrected JSON contract."
                )}
                content = await asyncio.to_thread(call_agent_model, messages + [{"role": "assistant", "content": content}, correction], 6000)
                requirements = parse_requirements_result(content, session["generation"], source_text)
            if requirements["status"] == "needs_input" and not requirements.get("_contract_issues"):
                allowed_questions = {"background_music_choice", "reference_role", "role_mapping", "dialogue", "ending", "central_action"}
                allowed_questions.update(
                    item.get("id") for item in requirements.get("questions", [])
                    if str(item.get("id", "")).startswith("text_normalization_")
                )
                extraneous = [item for item in requirements["questions"] if item.get("id") not in allowed_questions]
                if extraneous:
                    correction = {"role": "user", "content": (
                        "Do not ask the user to choose editing strategy, shot count, choreography, pacing, or other creative decisions. "
                        "Decide these yourself while preserving the user's action and dialogue. Only ask about missing "
                        "reference ownership, mandatory dialogue, ending, central action, or the required music decision. "
                        "Return the complete corrected JSON contract."
                    )}
                    content = await asyncio.to_thread(call_agent_model, messages + [{"role": "assistant", "content": content}, correction], 6000)
                    requirements = parse_requirements_result(content, session["generation"], source_text)
            if requirements.get("_contract_issues"):
                correction = {
                    "role": "user",
                    "content": "Your response claimed status=ready but violated the JSON contract: "
                    + "; ".join(requirements["_contract_issues"])
                    + ". Return one corrected, complete JSON object only. Do not ask the user to repair your formatting.",
                }
                corrected = await asyncio.to_thread(
                    call_agent_model,
                    messages + [{"role": "assistant", "content": content}, correction],
                    6000,
                )
                messages.extend([{"role": "assistant", "content": content}, correction])
                content = corrected
                requirements = parse_requirements_result(content, session["generation"], source_text)
                if requirements.get("_contract_issues"):
                    raise ValueError("需求策划阶段连续两次未返回完整结构，请重试或更换 AI 模型")
            messages.append({"role": "assistant", "content": content})
            requirements.pop("_contract_issues", None)
            session["requirements"] = requirements
            update_agent_progress(progress_id, "requirements", "completed", "需求、素材、声音与制作约束已整理")
            if requirements["status"] != "ready":
                finish_agent_progress(progress_id, "awaiting_input")
                return {
                    "session_id": session["id"],
                    "progress_id": progress_id,
                    "status": "needs_input",
                    "message": requirements["message"],
                    "questions": requirements["questions"],
                    "reference_map": requirements["reference_map"],
                    "decisions": requirements["decisions"],
                    "optimized_prompt_zh": "",
                    "optimized_prompt": "",
                    "optimized_shots": [],
                    "generation_payload": {},
                    "stage": "requirements",
                }
            progress_callback = lambda stage_id, status, message="": update_agent_progress(progress_id, stage_id, status, message)
            result = await asyncio.to_thread(run_h3_production_pipeline, session, requirements, progress_callback)
            session["production_plan"] = result.get("production_plan")
            session["last_final_result"] = {
                "optimized_prompt_zh": result.get("optimized_prompt_zh", ""),
                "optimized_prompt": result.get("optimized_prompt", ""),
            }
            finish_agent_progress(progress_id, "completed" if result.get("status") == "ready" else "awaiting_input")
            return {"session_id": session["id"], "progress_id": progress_id, "stage": "ready", **result}

        stage_id = "quick_convert" if session.get("pipeline") == "h3-quick" else "optimize"
        stage_message = "正在忠实转换为 MiniMax H3 中英文执行稿" if stage_id == "quick_convert" else "正在按当前模型与模式优化提示词"
        update_agent_progress(progress_id, stage_id, "running", stage_message)
        max_tokens = 7000 if session.get("pipeline") == "h3-quick" else 2500
        content = await asyncio.to_thread(call_agent_model, session["messages"], max_tokens)
        result = parse_agent_result(content)
        result = await asyncio.to_thread(
            repair_agent_result,
            session["messages"],
            result,
            session.get("model", request.model),
            session.get("mode", request.mode),
        )
        session["messages"].append({"role": "assistant", "content": content})
        update_agent_progress(progress_id, stage_id, "completed", "H3 提示词转换已完成" if stage_id == "quick_convert" else "提示词方案已完成")
        finish_agent_progress(progress_id, "completed" if result.get("status") == "ready" else "awaiting_input")
        return {"session_id": session["id"], "progress_id": progress_id, **result}
    except ValueError as exc:
        fail_agent_progress(progress_id, str(exc))
        raise HTTPException(502, str(exc)) from exc


