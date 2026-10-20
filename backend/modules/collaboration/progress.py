# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

import json
import time

from ...bootstrap import context
from ...core.errors import AgentCollaborationCancelled


def start(progress_id: str, stages: list[dict[str, str]]) -> None:
    with context.state_lock:
        context.agent_progress[progress_id] = {
            "id": progress_id,
            "status": "running",
            "updated_at": time.time(),
            "stages": [{"id": stage["id"], "label": stage["label"], "status": "pending", "message": ""} for stage in stages],
        }
        if len(context.agent_progress) > 100:
            oldest = min(context.agent_progress.values(), key=lambda item: item["updated_at"])
            context.agent_progress.pop(oldest["id"], None)
        snapshot = json.loads(json.dumps(context.agent_progress[progress_id], ensure_ascii=False))
    if context.db.collaboration(progress_id):
        context.db.update_collaboration(progress_id, {"progress": snapshot})


def update(progress_id: str, stage_id: str, status: str, message: str = "") -> None:
    with context.state_lock:
        progress = context.agent_progress.get(progress_id)
        if not progress:
            return
        stage = next((item for item in progress["stages"] if item["id"] == stage_id), None)
        if stage:
            stage.update({"status": status, "message": message})
        progress["updated_at"] = time.time()
        if status == "error":
            progress["status"] = "error"
        snapshot = json.loads(json.dumps(progress, ensure_ascii=False))
    item = context.db.collaboration(progress_id)
    if item:
        if item.get("status") == "cancelled":
            raise AgentCollaborationCancelled()
        context.db.update_collaboration(progress_id, {"progress": snapshot})


def finish(progress_id: str, status: str) -> None:
    with context.state_lock:
        progress = context.agent_progress.get(progress_id)
        if progress:
            progress.update({"status": status, "updated_at": time.time()})
            snapshot = json.loads(json.dumps(progress, ensure_ascii=False))
        else:
            snapshot = None
    if snapshot is not None and context.db.collaboration(progress_id):
        context.db.update_collaboration(progress_id, {"progress": snapshot})


def fail(progress_id: str, message: str) -> None:
    with context.state_lock:
        progress = context.agent_progress.get(progress_id)
        if not progress:
            return
        stage = next((item for item in progress["stages"] if item["status"] == "running"), None)
        if stage:
            stage.update({"status": "error", "message": message})
        progress.update({"status": "error", "updated_at": time.time()})
        snapshot = json.loads(json.dumps(progress, ensure_ascii=False))
    if context.db.collaboration(progress_id):
        context.db.update_collaboration(progress_id, {"progress": snapshot})
