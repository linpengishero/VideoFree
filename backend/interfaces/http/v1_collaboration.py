# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

import asyncio
import shutil
import time
import uuid
from typing import Any

from fastapi import HTTPException

from ...bootstrap import context
from ...modules.collaboration.media import collaboration_directory
from ...modules.collaboration.worker import close_agent_connection, persist_agent_references
from ...modules.projects import ProjectService
from ...core.schemas import AgentChatRequest
from .v1_system import ai_is_configured


MAX_AGENT_QUEUE_SIZE = context.config.max_agent_queue_size

def _authorized(item: dict[str, Any]) -> dict[str, Any]:
    try:
        return ProjectService(context).authorize(str(item.get("project_id") or ""))
    except ValueError as exc:
        raise HTTPException(404, "智能协作会话不存在") from exc

async def _enqueue_existing_agent_collaboration(collaboration_id: str, request: AgentChatRequest) -> dict[str, Any]:
    assert context.agent_queue is not None
    if not ai_is_configured():
        raise HTTPException(422, "请先在设置中配置智能协作的模型服务")
    if context.agent_queue.full():
        raise HTTPException(429, f"智能协作队列已满，最多等待 {MAX_AGENT_QUEUE_SIZE} 个任务")
    item = context.db.collaboration(collaboration_id)
    if not item:
        raise HTTPException(404, "智能协作会话不存在")
    _authorized(item)
    request_id = request.client_request_id or f"turn-{uuid.uuid4().hex}"
    existing = context.db.collaboration_for_turn(request_id)
    if existing:
        return existing
    if item['status'] in {'running', 'cancelled', 'submitted', 'deleted'} or (
            item['status'] == 'queued' and '_source_request' in item.get('request', {}).get('params', {})):
        raise HTTPException(409, "当前会话正在处理或已结束，不能重复入队")
    payload = await asyncio.to_thread(persist_agent_references, collaboration_id, request.model_dump())
    item = context.db.collaboration(collaboration_id)
    if not item or item['status'] in {'cancelled', 'submitted', 'deleted'}:
        raise HTTPException(409, "当前会话已结束")
    previous = item.get("request", {})
    source_request = previous.get("params", {}).get("_source_request", previous) if isinstance(previous, dict) else {}
    payload.setdefault("params", {})["_source_request"] = source_request
    context.db.update_collaboration(collaboration_id, {
        "status": "queued", "request": payload, "error": None, "completed_at": None,
        "result": {key: value for key, value in item.get("result", {}).items() if key != "enqueue_failed"},
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
    _authorized(item)
    if item["status"] in {"queued", "running", "needs_input", "awaiting_confirmation"}:
        item = context.db.update_collaboration(collaboration_id, {
            "status": "cancelled", "completed_at": time.time(),
            "progress": {**(item.get("progress") or {}), "status": "cancelled", "updated_at": time.time()},
        })
        close_agent_connection(collaboration_id)
    return item

async def delete_existing_agent_collaboration(collaboration_id: str) -> bool:
    item = context.db.collaboration(collaboration_id)
    if not item:
        raise HTTPException(404, "智能协作会话不存在")
    _authorized(item)
    deleted = context.db.delete_collaboration(collaboration_id)
    if deleted:
        await asyncio.to_thread(shutil.rmtree, collaboration_directory(collaboration_id), True)
    return deleted

async def agent_chat(request: AgentChatRequest):
    from ...modules.collaboration.modes import dispatch
    return await dispatch(request)

