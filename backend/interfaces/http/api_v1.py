# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ...core.version import PLATFORM_VERSION

from ...bootstrap import context
from ...core.errors import GatewayError
from ...modules.generation.service import (
    hydrate_job_request, style_items, workflow_registry,
)
from ...core.schemas import AgentChatRequest, GenerateRequest, TTSRequest
from ...lifecycle import lifespan
from .v1_collaboration import (
    agent_chat, enqueue_existing_agent_collaboration,
    cancel_existing_agent_collaboration,
)
from .v1_system import router as system_router
from .v1_assets import library, upload_media, router as assets_router
from .v1_projects import router as projects_router
from .v1_generation import (
    submit, public_job, cancel_job, router as generation_router,
)
from .dependencies import auth
from .api_v2 import build_router
from .mcp import build_router as build_mcp_router

UPLOAD_CACHE = context.paths.uploads
WORKFLOWS = context.paths.plugins


app = FastAPI(title="videofree", version=PLATFORM_VERSION, lifespan=lifespan)


@app.exception_handler(GatewayError)
async def gateway_error(_: Request, exc: GatewayError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.exception_handler(PermissionError)
async def permission_error(request: Request, _: PermissionError):
    """Turn OS file-lock/permission failures into an actionable API error."""
    deleting = request.method.upper() in {"DELETE", "PATCH"}
    message = (
        "文件正在被其他程序占用或当前账户没有删除权限，请先停止 ComfyUI 或相关任务，"
        "等待几秒后重试。"
        if deleting else
        "文件正在被其他程序占用或当前账户没有访问权限，请检查 ComfyUI 和存储目录权限。"
    )
    return JSONResponse(
        status_code=409 if deleting else 503,
        content={"detail": message, "code": "file_access_denied"},
    )


DIST = context.paths.static_dist
if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")
if (DIST / "contact").is_dir():
    app.mount("/contact", StaticFiles(directory=DIST / "contact"), name="contact")

app.include_router(system_router)
app.include_router(assets_router)
app.include_router(projects_router)
app.include_router(generation_router)

app.include_router(build_router(
    context=context,
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
    upload_cache=UPLOAD_CACHE,
    upload_handler=upload_media,
    style_items=style_items,
    cancel_handler=cancel_job,
    agent_handler=agent_chat,
    agent_model=AgentChatRequest,
    agent_enqueue_handler=enqueue_existing_agent_collaboration,
    agent_cancel_handler=cancel_existing_agent_collaboration,
    library_handler=library,
))
app.include_router(build_mcp_router())
