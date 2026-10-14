import asyncio
import contextvars
from dataclasses import dataclass, field
import http.client
from pathlib import Path
import threading
from typing import Any

from ..persistence import Database
from .config import EnvironmentConfig, ProjectPaths


@dataclass(slots=True)
class ApplicationContext:
    paths: ProjectPaths
    config: EnvironmentConfig
    db: Database
    comfyui_url: str
    comfyui_output_dir: Path
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
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
    worker_supervisor_task: asyncio.Task | None = None
    generation_worker_failures: int = 0
    agent_worker_tasks: list[asyncio.Task] = field(default_factory=list)
    submission_lock: asyncio.Lock | None = None
    state_lock: threading.Lock = field(default_factory=threading.Lock)
    library_lock: threading.Lock = field(default_factory=threading.Lock)
    current_collaboration_id: contextvars.ContextVar[str | None] = field(
        default_factory=lambda: contextvars.ContextVar("current_collaboration_id", default=None)
    )
    current_workspace_id: contextvars.ContextVar[str] = field(
        default_factory=lambda: contextvars.ContextVar("current_workspace_id", default="studio-default")
    )

    @classmethod
    def create(cls, root: Path) -> "ApplicationContext":
        paths = ProjectPaths.from_root(root)
        paths.ensure_runtime_directories()
        config = EnvironmentConfig.load(paths)
        return cls(
            paths=paths,
            config=config,
            db=Database(paths.data / "media_gateway.db"),
            comfyui_url=config.default_comfyui_url,
            comfyui_output_dir=config.default_comfyui_output_dir,
        )
