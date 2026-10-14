from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ...bootstrap import context, comfyui_client
from ...modules.generation.service import (
    hydrate_job_request, style_items, workflow_registry,
)
from ...modules.settings import SettingsService
from ...modules.shared.schemas import AgentChatRequest, GenerateRequest, TTSRequest
from .legacy_exports import *  # noqa: F401,F403

settings_service = SettingsService(context, comfyui_client)
DATA = context.paths.data
ARTIFACTS = context.paths.artifacts
CACHE = context.paths.cache
TASKS = context.paths.tasks
COLLABORATIONS = context.paths.collaborations
VOICE_SAMPLE_CACHE = context.paths.voice_samples
UPLOAD_CACHE = context.paths.uploads
WORKFLOWS = context.paths.workflows
WORKFLOW_REGISTRY = context.paths.workflow_registry
AGENT_SKILLS = context.paths.agent_skills
SETTINGS_FILE = context.paths.legacy_settings
API_TOKEN = context.config.api_token
MAX_TEXT = context.config.max_text
MAX_UPLOAD_BYTES = context.config.max_upload_bytes
MAX_TOTAL_UPLOAD_BYTES = context.config.max_total_upload_bytes
CONCURRENCY = context.config.generation_concurrency
MAX_QUEUE_SIZE = context.config.max_queue_size
MAX_AGENT_QUEUE_SIZE = context.config.max_agent_queue_size
UPLOAD_MAX_AGE_SECONDS = context.config.upload_max_age_seconds
COLLABORATION_MAX_AGE_SECONDS = context.config.collaboration_max_age_seconds
AGENT_TIMEOUT_SECONDS = context.config.agent_timeout_seconds



def read_settings() -> dict[str, Any]:
    settings_service.legacy_settings_path = SETTINGS_FILE
    return settings_service.read()


def effective_output_directory(settings: dict[str, Any]) -> Path:
    return settings_service.effective_output_directory(settings)


def ai_is_configured(settings: dict[str, Any] | None = None) -> bool:
    return settings_service.ai_is_configured(settings)


def apply_settings(values: dict[str, str]) -> dict[str, Any]:
    settings_service.legacy_settings_path = SETTINGS_FILE
    return settings_service.apply(values)



def configured_grsai_key(settings: dict[str, Any] | None = None) -> str:
    return settings_service.configured_grsai_key(settings)


def fetch_ai_models(base_url: str, api_key: str = "") -> list[str]:
    return settings_service.fetch_ai_models(base_url, api_key)


from .v1_collaboration import *  # noqa: F401,F403
from .v1_collaboration import router as collaboration_router

from ...lifecycle import clean_collaborations, clean_upload_cache, lifespan, start, stop


app = FastAPI(title="videofree", version="1.1.0", lifespan=lifespan)
DIST = context.paths.static_dist
if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
if (DIST / "contact").is_dir():
    app.mount("/contact", StaticFiles(directory=DIST / "contact"), name="contact")

from .v1_system import *  # noqa: F401,F403
from .v1_system import router as system_router

app.include_router(system_router)
app.include_router(collaboration_router)
from .v1_assets import *  # noqa: F401,F403
from .v1_assets import router as assets_router

app.include_router(assets_router)
from .v1_projects import router as projects_router

app.include_router(projects_router)
from .v1_generation import *  # noqa: F401,F403
from .v1_generation import _submit, router as generation_router

app.include_router(generation_router)
from .dependencies import auth
from .api_v2 import build_router
from .mcp import build_router as build_mcp_router

app.include_router(build_router(
    db=context.db,
    auth=auth,
    workflow_registry=workflow_registry,
    workflows_path=WORKFLOWS,
    submit=submit,
    generate_model=GenerateRequest,
    tts_model=TTSRequest,
    jobs=lambda: context.jobs,
    public_job=public_job,
    hydrate_job=hydrate_job_request,
    artifacts_path=ARTIFACTS,
    upload_cache=UPLOAD_CACHE,
    upload_handler=upload_media,
    style_items=style_items,
    cancel_handler=cancel_job,
    delete_handler=delete_job,
    voice_sample_handler=generate_voice_sample,
    agent_handler=agent_chat,
    agent_model=AgentChatRequest,
    agent_enqueue_handler=enqueue_existing_agent_collaboration,
    agent_cancel_handler=cancel_existing_agent_collaboration,
    agent_delete_handler=delete_existing_agent_collaboration,
    library_handler=library,
))
app.include_router(build_mcp_router())
