# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Durable collaboration queue processing and reference persistence."""

import asyncio
import logging
import mimetypes
from pathlib import Path
import shutil
import socket
import time
from typing import Any

from ...bootstrap import context
from ...core.errors import AgentCollaborationCancelled
from ...core.schemas import AgentChatRequest
from ..shared.media_inputs import data_url_bytes, upload_path
from .media import collaboration_directory
from .modes import dispatch


logger = logging.getLogger(__name__)


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
        source = upload_path(context.paths.uploads, value) if value.startswith("upload:") else None
        if source:
            target = root / f"{index:03d}{source.suffix}"
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


async def process_agent_collaboration(collaboration_id: str) -> None:
    started_at = time.time()
    item = context.db.collaboration(collaboration_id)
    if not item or item.get("status") != "queued":
        return
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
        result = await dispatch(request)
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
            "status": status, "result": result, "state": session_state,
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
    except Exception as exc:
        session_state = take_session_state()
        current = context.db.collaboration(collaboration_id)
        if current and current.get("status") not in {"cancelled", "abandoned", "interrupted"}:
            detail = getattr(exc, "detail", str(exc))
            context.db.update_collaboration(collaboration_id, {
                "status": "failed", "error": str(detail), "state": session_state,
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
    if not connection:
        return
    try:
        if connection.sock:
            connection.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        connection.close()
    except OSError:
        pass
