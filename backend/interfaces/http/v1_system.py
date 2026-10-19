import asyncio
import mimetypes
import os
from pathlib import Path
import subprocess

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse

from ...bootstrap import ROOT, context, comfyui_client
from ...modules.generation.service import (
    generation_runtime_health, style_items, workflow_registry,
)
from ...modules.settings import SettingsService
from ...modules.settings.plugins import PluginSettings
from ...modules.presets.voices import VoicePresets
from ...modules.projects import ProjectService
from ...core.schemas import AIModelsRequest, SettingsRequest
from .dependencies import auth, set_session


router = APIRouter()
settings_service = SettingsService(context, comfyui_client)
DIST = context.paths.static_dist
WORKFLOWS = context.paths.plugins
SETTINGS_FILE = context.paths.legacy_settings


@router.post("/v1/auth/session", dependencies=[Depends(auth)])
async def browser_session(request: Request, response: Response):
    set_session(response, request, SettingsService.access_token(context))
    return {"authenticated": True}


def read_settings():
    settings_service.legacy_settings_path = SETTINGS_FILE
    return settings_service.read()


def effective_output_directory(settings):
    return settings_service.effective_output_directory(settings)


def ai_is_configured(settings=None):
    return settings_service.ai_is_configured(settings)


def apply_settings(values):
    settings_service.legacy_settings_path = SETTINGS_FILE
    return settings_service.apply(values)


@router.get("/", response_class=HTMLResponse)
@router.get("/studio", response_class=HTMLResponse)
async def index() -> str:
    page = DIST / "index.html"
    if page.exists():
        return page.read_text(encoding="utf-8")
    raise HTTPException(503, "前端构建文件缺失，请在 frontend 目录运行 npm ci 和 npm run build，或下载完整发行包。")

@router.get("/v1/health")
async def health(_: None = Depends(auth)):
    runtime = generation_runtime_health()
    comfyui_status = "ok" if await asyncio.to_thread(comfyui_client.is_available) else "unavailable"
    status = "ok" if comfyui_status == "ok" and runtime["local_workers_alive"] > 0 else "degraded"
    return {"status": status, "comfyui": context.comfyui_url, "comfyui_status": comfyui_status, **runtime}

@router.get("/v1/voices")
async def voices(_: None = Depends(auth)): return {"voices": VoicePresets(context).items()}

@router.get("/v1/voices/{preset_key}/sample", dependencies=[Depends(auth)])
async def voice_sample(preset_key: str):
    voice = VoicePresets(context).get(preset_key)
    if not voice or not voice.get("sample_audio_name"):
        raise HTTPException(404, "voice sample not found")
    path = VoicePresets(context).sample_path(voice)
    if not path.is_file():
        raise HTTPException(404, "voice sample not found")
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "audio/mpeg")


@router.get("/v1/models")
async def models(_: None = Depends(auth)):
    return {"comfyui": context.comfyui_url, "workflows": list(workflow_registry().values())}


@router.get('/v1/styles', dependencies=[Depends(auth)])
async def styles(plugin_id: str = ""):
    items, errors = await asyncio.to_thread(style_items, plugin_id or None)
    return {'items': [{'id': s['id'], 'name': s.get('name_cn') or s['name'], 'original_name': s['name'], 'category': s['category'], 'default': s.get('default', False), 'thumbnail': f"/v1/styles/{s['id']}/thumbnail?plugin_id={s['plugin_id']}" if s.get('thumbnail_path') else None} for s in items], 'errors': errors}

@router.get('/v1/styles/{style_id}/thumbnail', dependencies=[Depends(auth)])
async def style_thumbnail(style_id: str, plugin_id: str = ''):
    item = next((s for s in (await asyncio.to_thread(style_items, plugin_id or None))[0] if s['id'] == style_id), None)
    if not item or not item.get('thumbnail_path'):
        raise HTTPException(404, 'Thumbnail not found')
    return FileResponse(item['thumbnail_path'])

@router.get("/v1/workflows")
async def workflows(_: None = Depends(auth)):
    """List registered local workflows and native gateway capabilities."""
    return {"items": [
        {"id": key, **config}
        for key, config in workflow_registry().items()
        if config.get("executor", "comfyui") != "comfyui" or (WORKFLOWS / config.get("file", "")).is_file()
    ]}

@router.get("/v1/settings", dependencies=[Depends(auth)])
async def settings(reveal_secrets: bool = False):
    values = read_settings()
    values["comfyui_output_dir"] = context.db.settings().get("comfyui_output_dir", "")
    if not reveal_secrets:
        values["ai_api_key"] = "********" if values.get("ai_api_key") else ""
        values["gateway_token"] = "********" if values.get("gateway_token") else ""
    return values


@router.get("/v1/settings/llm-providers", dependencies=[Depends(auth)])
async def llm_providers():
    return {"items": settings_service.llm_providers(),
            "errors": getattr(context.system_services, "errors", [])}


@router.get("/v1/settings/plugins", dependencies=[Depends(auth)])
async def plugin_settings_catalog():
    return {"items": PluginSettings(context).catalog()}


@router.get("/v1/settings/plugins/{plugin_id}", dependencies=[Depends(auth)])
async def read_plugin_settings(plugin_id: str):
    try:
        return {"values": PluginSettings(context).read(plugin_id)}
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.put("/v1/settings/plugins/{plugin_id}", dependencies=[Depends(auth)])
async def update_plugin_settings(plugin_id: str, values: dict):
    try:
        return {"values": PluginSettings(context).save(plugin_id, values)}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

@router.get("/v1/settings/status", dependencies=[Depends(auth)])
async def settings_status(runtime: bool = False):
    stored = context.db.settings()
    values = read_settings()
    configured_directory = str(stored.get("resource_directory", "")).strip()
    return {
        "resource_directory": {"configured": bool(configured_directory),
                               "exists": ProjectService(context).projects_root.is_dir()},
        "ai": {"configured": ai_is_configured(values)},
    }

@router.post("/v1/settings/select-directory", dependencies=[Depends(auth)])
async def select_settings_directory():
    if os.name != "nt":
        raise HTTPException(501, "当前系统不支持原生目录选择，请手动填写路径")

    def choose() -> str:
        script = r'''
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '选择 videofree 本地资源存储目录'
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::Write($dialog.SelectedPath)
}
'''
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "无法打开目录选择器")
        return result.stdout.strip()

    try:
        return {"path": await asyncio.to_thread(choose)}
    except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
        raise HTTPException(500, str(exc)) from exc

@router.put("/v1/settings", dependencies=[Depends(auth)])
async def update_settings(request: SettingsRequest, http_request: Request, response: Response):
    values = request.model_dump(exclude_none=True)
    current = read_settings()
    if values.get("ai_api_key") == "********": values["ai_api_key"] = current.get("ai_api_key", "")
    if values.get("gateway_token") == "********": values["gateway_token"] = current.get("gateway_token", "")
    try:
        saved = apply_settings(values)
        set_session(response, http_request, saved.get("gateway_token", ""))
        saved["ai_api_key"] = "********" if saved.get("ai_api_key") else ""
        saved["gateway_token"] = "********" if saved.get("gateway_token") else ""
        return saved
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc

@router.post("/v1/settings/clear-secrets", dependencies=[Depends(auth)])
async def clear_sensitive_settings():
    context.db.save_settings({"ai_api_key": ""})
    return {"cleared": ["ai_api_key"]}

@router.post("/v1/settings/ai-models", dependencies=[Depends(auth)])
async def list_ai_models(request: AIModelsRequest):
    current = read_settings()
    key = current.get("ai_api_key", "") if request.ai_api_key == "********" else request.ai_api_key.strip()
    try:
        return {"items": await asyncio.to_thread(
            settings_service.fetch_ai_models, request.ai_base_url, key, request.ai_provider
        )}
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc

