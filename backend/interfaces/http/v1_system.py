import asyncio
import mimetypes
import os
from pathlib import Path
import subprocess
import shutil
import time
import urllib.parse
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from ...bootstrap import ROOT, context, comfyui_client
from ...modules.generation.service import (
    configured_grsai_key, generation_runtime_health, run_tts, style_items, workflow_registry,
)
from ...modules.settings import SettingsService
from ...modules.shared.schemas import AIModelsRequest, SettingsRequest, TTSRequest
from .dependencies import auth


router = APIRouter()
settings_service = SettingsService(context, comfyui_client)
DIST = context.paths.static_dist
VOICE_SAMPLE_CACHE = context.paths.voice_samples
WORKFLOWS = context.paths.workflows
SETTINGS_FILE = context.paths.legacy_settings


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


def fetch_ai_models(base_url, api_key=""):
    return settings_service.fetch_ai_models(base_url, api_key)

@router.get("/", response_class=HTMLResponse)
@router.get("/studio", response_class=HTMLResponse)
async def index() -> str:
    page = DIST / "index.html"
    if page.exists():
        return page.read_text(encoding="utf-8")
    return (ROOT / "static" / "index.html").read_text(encoding="utf-8")

@router.get("/v1/health")
async def health(_: None = Depends(auth)):
    runtime = generation_runtime_health()
    comfyui_status = "ok" if await asyncio.to_thread(comfyui_client.is_available) else "unavailable"
    status = "ok" if comfyui_status == "ok" and runtime["local_workers_alive"] > 0 else "degraded"
    return {"status": status, "comfyui": context.comfyui_url, "comfyui_status": comfyui_status, **runtime}

@router.get("/v1/voices")
async def voices(_: None = Depends(auth)): return {"voices": context.db.presets()}

@router.get("/v1/music-presets", dependencies=[Depends(auth)])
async def music_presets():
    return {
        "styles": context.db.creative_presets("music", "style"),
        "singers": context.db.creative_presets("music", "singer"),
        "voice_textures": context.db.creative_presets("music", "voice_texture"),
    }

class VoicePresetRequest(BaseModel):
    preset_key: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=1, max_length=2000)
    speaker: str = ""
    language: str = "Chinese"
    model: str = ""

class VoicePreviewRequest(BaseModel):
    draft_id: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=1, max_length=2000)

@router.post("/v1/voices", dependencies=[Depends(auth)])
async def create_voice(request: VoicePresetRequest):
    try: return {"voice": context.db.create_preset(request.model_dump())}
    except Exception as exc: raise HTTPException(400, f"voice preset already exists or invalid: {exc}") from exc

@router.put("/v1/voices/{preset_key}", dependencies=[Depends(auth)])
async def update_voice(preset_key: str, request: VoicePresetRequest):
    if request.preset_key != preset_key:
        raise HTTPException(400, "preset key cannot be changed")
    voice = context.db.update_preset(preset_key, request.model_dump())
    if not voice:
        raise HTTPException(404, "voice preset not found")
    return {"voice": voice}

VOICE_SAMPLE_TEXT = (
    "你好，我是你的专属声音助手。今天也请放心地把想法交给我。"
    "这段语音用于建立稳定的预设音色，包含自然的陈述、停顿和不同长短的句子。"
    "无论是讲述故事、解释信息，还是提醒重要事项，我都会保持清楚、平稳、自然的表达。"
    "请听清每一个字，也注意语气中温度、力度和节奏的变化。"
    "当内容需要强调时，我会适当加重重点；当内容需要安静时，我会放慢语速并保留自然呼吸。"
    "这是一段用于音色参考的标准样本，后续生成会尽量保持相同的声音特征。"
)

def safe_sample_name(value: str) -> str:
    return "".join(char for char in value if char.isalnum() or char in "_-")[:80] or "voice"

def cache_voice_sample(sample_id: str, instruction: str) -> Path:
    job_id = f"voice-sample-{safe_sample_name(sample_id)}-{uuid.uuid4().hex[:8]}"
    context.jobs[job_id] = {
        "id": job_id,
        "kind": "tts",
        "status": "queued",
        "request": {},
        "created_at": time.time(),
    }
    try:
        target = VOICE_SAMPLE_CACHE / f"{safe_sample_name(sample_id)}.mp3"
        temporary = run_tts(job_id, TTSRequest(text=VOICE_SAMPLE_TEXT, mode="describe", instruction=instruction))
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            cropped = VOICE_SAMPLE_CACHE / f".{safe_sample_name(sample_id)}-{uuid.uuid4().hex}.mp3"
            try:
                subprocess.run(
                    [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(temporary),
                     "-t", "25", "-map_metadata", "0", "-c:a", "libmp3lame", "-q:a", "2", str(cropped)],
                    check=True,
                    timeout=120,
                )
                cropped.replace(target)
            finally:
                cropped.unlink(missing_ok=True)
        else:
            temporary.replace(target)
        return target
    finally:
        context.jobs.pop(job_id, None)

@router.post("/v1/voices/{preset_key}/sample", dependencies=[Depends(auth)])
async def generate_voice_sample(preset_key: str):
    voice = context.db.preset(preset_key)
    if not voice:
        raise HTTPException(404, "voice preset not found")
    try:
        path = await asyncio.to_thread(cache_voice_sample, preset_key, voice["instruction"])
        voice = context.db.update_sample(preset_key, path.name)
        return {"voice": voice}
    except Exception as exc:
        raise HTTPException(502, f"预设试听生成失败: {exc}") from exc

@router.get("/v1/voices/{preset_key}/sample", dependencies=[Depends(auth)])
async def voice_sample(preset_key: str):
    voice = context.db.preset(preset_key)
    if not voice or not voice.get("sample_audio_name"):
        raise HTTPException(404, "voice sample not found")
    path = VOICE_SAMPLE_CACHE / Path(voice["sample_audio_name"]).name
    if not path.is_file():
        raise HTTPException(404, "voice sample not found")
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "audio/mpeg")

@router.post("/v1/voices/preview", dependencies=[Depends(auth)])
async def preview_voice(request: VoicePreviewRequest):
    try:
        path = await asyncio.to_thread(cache_voice_sample, f"draft_{request.draft_id}", request.instruction)
        return {"audio_url": f"/v1/voice-previews/{urllib.parse.quote(path.name)}"}
    except Exception as exc:
        raise HTTPException(502, f"预生成试听失败: {exc}") from exc

@router.get("/v1/voice-previews/{name}", dependencies=[Depends(auth)])
async def voice_preview(name: str):
    path = VOICE_SAMPLE_CACHE / Path(name).name
    if not path.is_file() or not path.name.startswith("draft_"):
        raise HTTPException(404, "voice preview not found")
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "audio/mpeg")

@router.get("/v1/models")
async def models(_: None = Depends(auth)):
    return {"comfyui": context.comfyui_url, "workflows": list(workflow_registry().values())}


@router.get('/v1/styles', dependencies=[Depends(auth)])
async def styles():
    items, errors = await asyncio.to_thread(style_items)
    return {'items': [{'id': s['id'], 'name': s.get('name_cn') or s['name'], 'original_name': s['name'], 'category': s['category'], 'thumbnail': '/v1/styles/' + s['id'] + '/thumbnail' if s.get('thumbnail_path') else None} for s in items], 'errors': errors}

@router.get('/v1/styles/{style_id}/thumbnail', dependencies=[Depends(auth)])
async def style_thumbnail(style_id: str):
    item = next((s for s in (await asyncio.to_thread(style_items))[0] if s['id'] == style_id), None)
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
    grsai_key = configured_grsai_key()
    if not reveal_secrets:
        values["ai_api_key"] = "********" if values.get("ai_api_key") else ""
        grsai_key = "********" if grsai_key else ""
    values["grsai_api_key"] = grsai_key
    return values

@router.get("/v1/settings/status", dependencies=[Depends(auth)])
async def settings_status(runtime: bool = False):
    stored = context.db.settings()
    values = read_settings()
    configured_directory = str(stored.get("comfyui_output_dir", "")).strip()
    acceleration = {"available": False, "sage_attention": False, "connected": False}
    if runtime:
        # These probes have different meanings. A missing optional node must
        # not make a reachable ComfyUI instance look offline.
        acceleration["connected"] = await asyncio.to_thread(comfyui_client.is_available)
        try:
            stats = await asyncio.to_thread(comfy, "/system_stats")
            argv = stats.get("system", {}).get("argv", [])
            acceleration["sage_attention"] = "--use-sage-attention" in argv
        except Exception:
            pass
        if acceleration["connected"]:
            try:
                node = await asyncio.to_thread(comfy, "/object_info/SolAttnPatch")
                acceleration["available"] = "SolAttnPatch" in node
            except Exception:
                acceleration["available"] = False
    return {
        "resource_directory": {
            "configured": bool(configured_directory),
            "exists": bool(configured_directory and Path(configured_directory).expanduser().is_dir()),
        },
        "ai": {"configured": ai_is_configured(values)},
        "minimax_acceleration": acceleration,
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
$dialog.Description = '选择 ComfyUI 输出资源目录'
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
async def update_settings(request: SettingsRequest):
    values = request.model_dump(exclude_none=True)
    current = read_settings()
    if values.get("ai_api_key") == "********": values["ai_api_key"] = current.get("ai_api_key", "")
    if values.get("grsai_api_key") == "********": values.pop("grsai_api_key")
    try:
        saved = apply_settings(values)
        saved["ai_api_key"] = "********" if saved.get("ai_api_key") else ""
        saved["grsai_api_key"] = "********" if configured_grsai_key() else ""
        return saved
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc

@router.post("/v1/settings/clear-secrets", dependencies=[Depends(auth)])
async def clear_sensitive_settings():
    context.db.save_settings({"ai_api_key": "", "grsai_api_key": ""})
    return {"cleared": ["ai_api_key", "grsai_api_key"]}

@router.post("/v1/settings/ai-models", dependencies=[Depends(auth)])
async def list_ai_models(request: AIModelsRequest):
    current = read_settings()
    key = current.get("ai_api_key", "") if request.ai_api_key == "********" else request.ai_api_key.strip()
    try:
        return {"items": await asyncio.to_thread(fetch_ai_models, request.ai_base_url, key)}
    except ValueError as exc:
        raise HTTPException(502, str(exc)) from exc

