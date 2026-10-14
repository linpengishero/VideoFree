import asyncio
from contextlib import asynccontextmanager
import logging
import shutil
import time

from fastapi import FastAPI

from .bootstrap import context, comfyui_client
from .modules.generation.service import (
    generation_config, job_execution_plane, migrate_generation_metadata, recover_h3_checkpoints, set_status,
    start_direct_generation, worker,
)
from .modules.presets import MUSIC_PRESETS
from .modules.presets.voices import VOICE_PRESETS
from .modules.settings import SettingsService
from .modules.projects import ProjectService
from .modules.shared.schemas import GenerateRequest
from .interfaces.http.v1_collaboration import (
    agent_worker, close_agent_connection, collaboration_directory,
)


settings_service = SettingsService(context, comfyui_client)
logger = logging.getLogger(__name__)


def start_generation_worker() -> asyncio.Task:
    return asyncio.create_task(worker(), name="local-generation-worker")


async def supervise_generation_workers() -> None:
    while True:
        active: list[asyncio.Task] = []
        for task in context.worker_tasks:
            if not task.done():
                active.append(task)
                continue
            if not task.cancelled():
                context.generation_worker_failures += 1
                try:
                    error = task.exception()
                except asyncio.CancelledError:
                    error = None
                logger.error("generation worker stopped; restarting: %s", error or "unknown error")
        context.worker_tasks = active
        while len(context.worker_tasks) < context.config.generation_concurrency:
            context.worker_tasks.append(start_generation_worker())
        await asyncio.sleep(1)


def clean_upload_cache() -> None:
    cutoff = time.time() - context.config.upload_max_age_seconds
    protected = set()
    for item in context.db.collaborations(("queued", "running", "needs_input", "awaiting_confirmation"), limit=500):
        source = item.get("request", {})
        source = source.get("params", {}).get("_source_request", source) if isinstance(source, dict) else {}
        for asset in source.get("inputs", []) if isinstance(source, dict) else []:
            if isinstance(asset, dict) and asset.get("upload_id"):
                protected.add(str(asset["upload_id"]))
    for path in context.paths.uploads.iterdir():
        try:
            if path.is_file() and path.stem not in protected and path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def clean_collaborations() -> None:
    cutoff = time.time() - context.config.collaboration_max_age_seconds
    for collaboration_id in context.db.prune_collaborations(cutoff):
        shutil.rmtree(collaboration_directory(collaboration_id), ignore_errors=True)


async def start() -> None:
    context.db.initialize(VOICE_PRESETS, MUSIC_PRESETS)
    migrate_generation_metadata()
    runtime_settings = settings_service.read()
    context.comfyui_url = runtime_settings["comfyui_url"].rstrip("/")
    comfyui_client.configure(context.comfyui_url)
    # ComfyUI is optional at gateway startup; live output discovery happens later.
    context.comfyui_output_dir = settings_service.effective_output_directory(
        runtime_settings, detect_comfyui=False,
    )
    ProjectService(context).import_legacy_assets()
    context.jobs = {item["id"]: item for item in context.db.jobs()}
    restored = recover_h3_checkpoints()
    if restored:
        logger.info("restored H3 latent checkpoints for %s completed job(s)", restored)
    pending = context.db.pending_jobs()
    context.jobs.update({item["id"]: item for item in pending})
    context.job_queue = asyncio.Queue()
    context.agent_queue = asyncio.Queue(maxsize=context.config.max_agent_queue_size)
    context.submission_lock = asyncio.Lock()
    context.generation_worker_failures = 0
    clean_upload_cache()
    clean_collaborations()
    for item in pending:
        if item["status"] == "running" and not item.get("comfy_prompt_id"):
            try:
                executor = generation_config(item["kind"], GenerateRequest(**item.get("request", {}))).get("executor", "comfyui")
            except (TypeError, ValueError, FileNotFoundError):
                executor = "comfyui"
            error = "网关重启中断了云端生成请求，请重新生成" if executor != "comfyui" else "网关重启前未保存 ComfyUI 任务标识，无法恢复"
            set_status(item["id"], "failed", error=error)
            continue
        if job_execution_plane(item) == "cloud":
            start_direct_generation(item["id"])
        else:
            context.job_queue.put_nowait(item["id"])
    context.worker_tasks = [start_generation_worker() for _ in range(context.config.generation_concurrency)]
    context.worker_supervisor_task = asyncio.create_task(
        supervise_generation_workers(), name="generation-worker-supervisor",
    )
    for item in context.db.collaborations(("queued", "running"), limit=context.config.max_agent_queue_size + 50):
        if not str(item.get("capability_id", "")).startswith("studio."):
            continue
        if item["status"] == "running":
            context.db.update_collaboration(item["id"], {
                "status": "interrupted",
                "error": "网关重启导致智能协作中断，请手动重试，系统不会自动重复调用模型",
                "completed_at": time.time(),
            })
        elif not context.agent_queue.full():
            context.agent_queue.put_nowait(item["id"])
    context.agent_worker_tasks = [asyncio.create_task(agent_worker())]


async def stop() -> None:
    if context.worker_supervisor_task:
        context.worker_supervisor_task.cancel()
        await asyncio.gather(context.worker_supervisor_task, return_exceptions=True)
        context.worker_supervisor_task = None
    tasks = [*context.worker_tasks, *context.direct_generation_tasks.values(), *context.agent_worker_tasks]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    for collaboration_id in list(context.active_agent_connections):
        close_agent_connection(collaboration_id)
    context.worker_tasks.clear()
    context.direct_generation_tasks.clear()
    context.agent_worker_tasks.clear()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await start()
    try:
        yield
    finally:
        await stop()
