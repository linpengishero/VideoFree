# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

import asyncio
import contextvars
from dataclasses import dataclass, field
import http.client
from pathlib import Path
import threading
from typing import Any, TYPE_CHECKING

from .config import EnvironmentConfig, ProjectPaths

if TYPE_CHECKING:
    from ..persistence import Database


@dataclass(slots=True)
class ApplicationContext:
    paths: ProjectPaths
    config: EnvironmentConfig
    db: "Database"
    comfyui_url: str
    comfyui_output_dir: Path
    system_services: Any = None
    storage_provider: Any = None
    comfyui_provider: Any = None
    comfyui_output_locations: dict[str, tuple[float, Path | None]] = field(default_factory=dict)
    plugin_catalogs: dict[str, Any] = field(default_factory=dict)
    plugin_catalog_lock: threading.RLock = field(default_factory=threading.RLock)
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    executing_jobs: set[str] = field(default_factory=set)
    agent_sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    agent_progress: dict[str, dict[str, Any]] = field(default_factory=dict)
    active_agent_connections: dict[str, http.client.HTTPConnection] = field(default_factory=dict)
    node_definition_cache: dict[tuple[str, ...], tuple[float, dict[str, Any]]] = field(default_factory=dict)
    library_cache: dict[str, Any] = field(
        default_factory=lambda: {"directory": "", "created_at": 0.0, "items": []}
    )
    job_queue: asyncio.Queue[str] | None = None
    agent_queue: asyncio.Queue[str] | None = None
    worker_tasks: list[asyncio.Task] = field(default_factory=list)
    direct_generation_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    application_tasks: dict[tuple, asyncio.Task] = field(default_factory=dict)
    application_semaphores: dict[str, asyncio.Semaphore] = field(default_factory=dict)
    worker_supervisor_task: asyncio.Task | None = None
    generation_worker_failures: int = 0
    agent_worker_tasks: list[asyncio.Task] = field(default_factory=list)
    submission_lock: asyncio.Lock | None = None
    generation_idempotency_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    collaboration_submission_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    state_lock: threading.RLock = field(default_factory=threading.RLock)
    job_file_lock: threading.RLock = field(default_factory=threading.RLock)
    library_lock: threading.Lock = field(default_factory=threading.Lock)
    current_collaboration_id: contextvars.ContextVar[str | None] = field(
        default_factory=lambda: contextvars.ContextVar("current_collaboration_id", default=None)
    )
