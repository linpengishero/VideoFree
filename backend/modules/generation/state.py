# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS = {
    JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.RUNNING: {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED},
    JobStatus.COMPLETED: set(),
    JobStatus.FAILED: set(),
    JobStatus.CANCELLED: set(),
}


def assert_job_transition(current: str, target: str) -> None:
    try:
        current_status = JobStatus(current)
        target_status = JobStatus(target)
    except ValueError as exc:
        raise ValueError(f"未知任务状态: {exc}") from exc
    if current_status == target_status:
        return
    if target_status not in _ALLOWED_TRANSITIONS[current_status]:
        raise ValueError(f"非法任务状态迁移: {current_status.value} -> {target_status.value}")
