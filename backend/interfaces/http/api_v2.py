import asyncio
import base64
import hashlib
import json
import mimetypes
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from ...modules.presets.voices import VoicePresets
from ...modules.projects import ProjectService
from ...modules.generation.actions import discover_actions, execute_action, public_action, public_actions, uploaded_source
from ...modules.generation.plugins import PluginCatalog
from ...modules.generation.service import submit_idempotent
from ...modules.collaboration.modes import confirmation_overrides
from ...core.errors import GatewayError


from .v2_capabilities import (
    resolution_pixels,
    capability as _capability,
    dimensions as _dimensions,
    model_and_mode as _model_and_mode,
    named_dimensions as _named_dimensions,
    validate_duration as _validate_duration,
    validate_input_roles as _validate_input_roles,
    voice as _voice,
)
from .v2_schemas import (
    AssetInput,
    CollaborationConfirmRequest,
    CollaborationCreateRequest,
    CollaborationMessageRequest,
    CreateRequest,
    CreateSettings,
    ProjectCreateRequest,
    ProjectSelectRequest,
    PluginActionExecuteRequest,
    PluginActionResponse,
    RegenerateRequest,
)


def build_router(*, context, db, auth: Callable, workflow_registry: Callable, workflows_path: Path,
                 submit: Callable, generate_model, tts_model, jobs: Callable,
                 public_job: Callable, hydrate_job: Callable,
                 upload_cache: Path, upload_handler: Callable, style_items: Callable,
                 cancel_handler: Callable,
                 agent_handler: Callable, agent_model,
                 library_handler: Callable, agent_enqueue_handler: Callable | None = None,
                 agent_cancel_handler: Callable | None = None,
                 ) -> APIRouter:
    router = APIRouter(prefix="/api/v2", tags=["AI API v2"], dependencies=[Depends(auth)])

    def authorized_project(project_id: str) -> dict[str, Any]:
        try:
            return ProjectService(context).authorize(project_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    def registry() -> dict[str, dict[str, Any]]:
        values = {
            key: value for key, value in workflow_registry().items()
            if value.get("executor", "comfyui") != "comfyui" or (workflows_path / value.get("file", "")).is_file()
        }
        return values

    def resolve_capability(capability_id: str) -> dict[str, Any]:
        config = registry().get(capability_id)
        if not config:
            raise HTTPException(404, f"能力不存在: {capability_id}")
        return config

    def upload_value(upload_id: str) -> str:
        if not re.fullmatch(r"[a-fA-F0-9]{32}", upload_id):
            raise HTTPException(422, "无效的 upload_id")
        if not any(upload_cache.glob(f"{upload_id}.*")):
            raise HTTPException(404, f"上传素材不存在或已过期: {upload_id}")
        return f"upload:{upload_id}"

    def upload_path(upload_id: str) -> Path:
        upload_value(upload_id)
        return next(upload_cache.glob(f"{upload_id}.*"))

    def api_job(item: dict[str, Any]) -> dict[str, Any]:
        value = public_job(item)
        request = value.get("request", {})
        params = request.get("params", {}) if isinstance(request, dict) else {}
        result = {
            key: value[key] for key in (
                "id", "kind", "status", "created_at", "updated_at", "completed_at",
                "elapsed_seconds", "width", "height", "duration_seconds", "error", "error_info",
                "parent_job_id", "revision", "artifacts",
            ) if key in value
        }
        result["capability_id"] = params.get("capability_id")
        result["prompt"] = params.get("source_prompt") or request.get("prompt") or request.get("text") or ""
        result["prompt_zh"] = params.get("confirmed_prompt_zh", "")
        result["execution_prompt_en"] = params.get("execution_prompt_en", "")
        result["project_id"] = value.get("project_id")
        result["category_id"] = value.get("category_id") or ""
        if params.get("lyrics"):
            result["lyrics"] = params["lyrics"]
        result["job_url"] = f"/api/v2/jobs/{value['id']}"
        result["wait_url"] = f"/api/v2/jobs/{value['id']}/wait"
        return result

    def api_submission(result: dict[str, Any], capability_id: str | None = None) -> dict[str, Any]:
        job_id = result["job_id"]
        value = {**result, "job_url": f"/api/v2/jobs/{job_id}", "wait_url": f"/api/v2/jobs/{job_id}/wait"}
        if capability_id:
            value["capability_id"] = capability_id
        return value

    def public_collaboration(item: dict[str, Any], *, include_messages: bool = False) -> dict[str, Any]:
        result = item.get("result", {}) if isinstance(item.get("result"), dict) else {}
        value: dict[str, Any] = {
            "id": item["id"],
            "capability_id": item["capability_id"],
            "model_id": item["model_id"],
            "mode_id": item["mode_id"],
            "collaboration_mode": item.get("request", {}).get("collaboration_mode", "director"),
            "status": item["status"],
            "revision": item.get("revision", 0),
            "message": result.get("message", ""),
            "error": item.get("error", ""),
            "progress": item.get("progress", {}),
            "questions": result.get("questions", []),
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
            "collaboration_url": f"/api/v2/collaborations/{item['id']}",
            "messages_url": f"/api/v2/collaborations/{item['id']}/messages",
            "progress_url": f"/api/v2/collaborations/{item['id']}/progress",
        }
        value["project_id"] = item.get("project_id")
        if item["status"] == "awaiting_confirmation":
            value["confirmation"] = {
                "execution_prompt_en": result.get("optimized_prompt", ""),
                "confirmed_prompt_zh": result.get("optimized_prompt_zh", ""),
                "generation_payload": result.get("generation_payload", {}),
                "revision": item.get("revision", 0),
            }
            value["confirm_url"] = f"/api/v2/collaborations/{item['id']}/confirm"
        if result.get("review"):
            value["review"] = result["review"]
        if item.get("job_id"):
            value["job_id"] = item["job_id"]
            value["job_url"] = f"/api/v2/jobs/{item['job_id']}"
        if include_messages:
            value["messages"] = db.collaboration_messages(item["id"])
        return value

    def collaboration_agent_request(item: dict[str, Any], message: str):
        request = item["request"]
        request = request.get("params", {}).get("_source_request", request)
        settings = CreateSettings.model_validate(request.get("settings", {}))
        config = resolve_capability(request["capability_id"])
        agent_target = (config.get("model_family", item["model_id"]), item["mode_id"])
        references = []
        for asset in request.get("inputs", []):
            path = upload_path(asset["upload_id"])
            references.append({
                "kind": asset["type"],
                "name": f"{asset.get('role', 'reference')}:{path.name}",
                "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "data_url": f"upload:{asset['upload_id']}",
            })
        return agent_model(
            message=message,
            kind=item["request"]["kind"],
            model=agent_target[0],
            mode=agent_target[1],
            duration_seconds=settings.duration,
            ratio=settings.ratio,
            resolution=resolution_pixels(settings.resolution),
            references=references,
            params={"variant": settings.variant, **settings.model_dump(), "capability_id": request["capability_id"], "processing_mode": request.get("prompt_processing", "director"), "_plugin_revision": request.get("plugin_revision"), "plugin_parameters": request.get("parameters", {})},
            review_mode="external",
            collaboration_mode=request.get("collaboration_mode", "director"),
        )

    def conversation_prompt(collaboration_id: str) -> str:
        messages = db.collaboration_messages(collaboration_id)
        lines = ["请根据以下完整对话继续协作。不要重复已经得到回答的问题，只在确有必要时追问："]
        labels = {"user": "用户", "assistant": "智能体"}
        lines.extend(f"{labels.get(item['role'], item['role'])}: {item['content']}" for item in messages)
        return "\n\n".join(lines)

    async def run_collaboration(item: dict[str, Any]) -> dict[str, Any]:
        try:
            if agent_enqueue_handler is None:
                raise HTTPException(503, "智能协作队列未配置")
            request = collaboration_agent_request(item, conversation_prompt(item["id"]))
            request.client_request_id = f"v2-{uuid.uuid4().hex}"
            queued = await agent_enqueue_handler(item["id"], request)
        except (Exception, asyncio.CancelledError) as exc:
            if isinstance(exc, (HTTPException, GatewayError)) and exc.status_code == 409:
                raise
            db.update_collaboration(item["id"], {
                "status": "failed", "error": str(getattr(exc, "detail", exc)),
                "result": {**item.get("result", {}), "enqueue_failed": True},
                "completed_at": time.time(),
            })
            raise
        return public_collaboration(queued, include_messages=True)

    @router.get("")
    @router.get("/")
    async def api_index():
        return {
            "name": "videofree AI API",
            "version": "2",
            "status": "ok",
            "health_url": "/api/v2/health",
            "capabilities_url": "/api/v2/capabilities",
            "docs_url": "/docs",
        }

    async def create_generation(request: CreateRequest, parent_job_id: str | None = None, project_id: str | None = None):
        if project_id:
            authorized_project(project_id)
        config = resolve_capability(request.capability_id)
        request = normalize_form(request, config)
        from ...modules.generation.plugins import validate_parameters
        try:
            plugin_parameters = validate_parameters(config, request.parameters)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        capability = _capability(request.capability_id, config)
        is_postprocess = capability["operation"] == "postprocess"
        _validate_duration(capability, request.settings.duration)
        _validate_input_roles(capability, request.inputs)
        shot_count = len(config.get("shot_nodes", []))
        if shot_count:
            shots = request.settings.shots
            if shots and (len(shots) != shot_count or any(not isinstance(value, str) or not value.strip() for value in shots)):
                raise HTTPException(422, f"当前分镜模式需要 {shot_count} 条非空镜头描述，请使用 settings.shots 提交")
            request.settings.shots = [value.strip() for value in shots]
        kind, model, mode = _model_and_mode(request.capability_id, config)
        grouped = {media: [] for media in ("image", "video", "audio")}
        grouped_roles = {media: [] for media in grouped}
        role_order = {role: index for media_roles in capability["input_roles"].values() for index, role in enumerate(media_roles)}
        ordered_inputs = sorted(enumerate(request.inputs), key=lambda pair: (pair[1].type, role_order.get(pair[1].role, 1000 + pair[0])))
        for _, item in ordered_inputs:
            grouped[item.type].append(upload_value(item.upload_id))
            grouped_roles[item.type].append(item.role)
        for media, limits in capability["inputs"].items():
            if not limits["min"] <= len(grouped[media]) <= limits["max"]:
                raise HTTPException(422, f"{media} 素材需要 {limits['min']}-{limits['max']} 个，当前为 {len(grouped[media])}")
        plugin_settings = {}
        settings = request.settings.model_dump()
        for field in config.get("ui", {}).get("fields", []):
            if field["bind"].startswith("settings.") and field["component"] != "media":
                name = field["bind"].split(".")[1]
                if name in settings:
                    plugin_settings[name] = settings[name]
        if kind == "tts" and not is_postprocess and config.get("compiler", "builtin") == "builtin":
            if not request.prompt.strip():
                raise HTTPException(422, "声音生成需要文本")
            body = tts_model(
                category_id=request.category_id,
                text=request.prompt.strip(), mode=mode, character=request.settings.voice_id,
                voice_model=model,
                instruction=request.settings.instruction,
                speed=request.settings.voice_speed,
                reference_audio=grouped["audio"][0] if grouped["audio"] else None,
                params={**plugin_settings, "capability_id": request.capability_id,
                        "plugin_parameters": plugin_parameters, "api_settings": settings},
                parent_job_id=parent_job_id,
                internal_project_id=project_id,
            )
        else:
            prompt = request.prompt.strip() or ("后期处理" if is_postprocess else "")
            if kind == "music" and config.get("compiler", "builtin") == "builtin":
                if mode != "background" and not request.lyrics.strip():
                    raise HTTPException(422, "音乐生成需要歌词")
            if not prompt:
                raise HTTPException(422, "生成描述不能为空")
            width, height = _dimensions(request.settings.resolution, request.settings.ratio, kind)
            params: dict[str, Any] = {
                "width": width, "height": height,
                "videos": grouped["video"], "audios": grouped["audio"],
                "seed": request.settings.seed, "parent_job_id": parent_job_id,
                "capability_id": request.capability_id,
                "input_roles": grouped_roles,
                "api_settings": request.settings.model_dump(),
                "confirmed_prompt_zh": request.settings.confirmed_prompt_zh,
                "execution_prompt_en": request.settings.execution_prompt_en,
                "_project_id": project_id,
                "_category_id": request.category_id,
                "plugin_parameters": plugin_parameters,
            }
            # Only declared settings can extend the execution payload. Definitions,
            # defaults and validation stay in the selected plugin, not this adapter.
            for name, value in plugin_settings.items():
                params.setdefault(name, value)
            if kind == "image" and not is_postprocess:
                params["image_model"] = model
                params["native_model"] = request.settings.native_model
                params["shots"] = request.settings.shots
                if request.settings.style_id:
                    custom = db.creative_preset("image", "style", request.settings.style_id)
                    if custom:
                        params["style_prompt"] = custom["instruction"]
                    else:
                        params["style_id"] = request.settings.style_id
            elif kind == "video" and not is_postprocess:
                params.update(
                    video_model=model,
                    speed=request.settings.variant,
                )
            elif kind == "music":
                params["lyrics"] = request.lyrics.strip()
                params["music_model"] = model
            body = generate_model(
                prompt=prompt, mode=mode, references=grouped["image"],
                duration_seconds=request.settings.duration, params=params,
            )
        result = await submit(kind, body)
        return api_submission(result, request.capability_id)

    async def invoke_plugin_capability(payload: dict[str, Any], *, project_id: str,
                                       category_id: str | None = None,
                                       idempotency_key: str | None = None):
        """Adapt trusted plugin calls to the same direct-generation contract as HTTP/MCP."""
        request = CreateRequest.model_validate({
            **payload,
            "project_id": project_id,
            "category_id": category_id,
            "prompt_processing": "direct",
        })
        if idempotency_key:
            if len(idempotency_key) > 120:
                raise HTTPException(422, "幂等键过长")
            result = await submit_idempotent(context, db, request, idempotency_key, create_generation)
            return api_submission(result, request.capability_id)
        return await create_generation(request, parent_job_id=request.parent_job_id, project_id=project_id)

    def normalize_form(request, config):
        from ...modules.generation.plugin_ui import form_values
        try:
            payload = request.model_dump(exclude_unset=True)
            # CreateSettings has a compatibility default for older video
            # clients. When the caller omitted resolution, remove that
            # generic value so the selected plugin's declared default wins.
            # An explicitly supplied value remains subject to plugin validation.
            settings = dict(payload.get("settings") or {})
            if "resolution" not in request.settings.model_fields_set:
                settings.pop("resolution", None)
            payload["settings"] = settings
            return CreateRequest.model_validate(form_values(config.get("ui", {}), payload))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/health")
    async def health():
        from ...modules.generation.service import generation_runtime_health
        runtime = generation_runtime_health()
        return {
            "status": "ok" if runtime["local_workers_alive"] > 0 else "degraded",
            "api_version": "2", "capabilities": len(registry()), **runtime,
        }

    @router.get("/projects")
    async def projects():
        return {"items": ProjectService(context).list()}

    @router.post("/projects", status_code=201)
    async def create_project(request: ProjectCreateRequest):
        try:
            project = ProjectService(context).create(request.name, request.description, request.content_summary, ai_created=request.ai_created)
            return project
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/projects/current")
    async def current_project():
        try:
            return ProjectService(context).current()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/projects/{project_id}/categories")
    async def project_categories(project_id: str):
        try:
            authorized_project(project_id)
            return {"items": ProjectService(context).categories(project_id)}
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.put("/projects/current")
    async def select_project(request: ProjectSelectRequest):
        try:
            return ProjectService(context).select(request.project_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/capabilities")
    async def capabilities(operation: str = "generate", kind: str | None = None, category: str | None = None):
        items = [_capability(key, config) for key, config in registry().items()]
        items = [item for item in items if item["operation"] == operation and (not kind or item["type"] == kind) and (not category or item["category"] == category)]
        return {"items": items}

    @router.get("/plugins")
    async def plugins():
        from ...modules.generation.plugins import PluginCatalog
        catalog = PluginCatalog(workflows_path, context)
        result = catalog.public()
        try:
            project = ProjectService(context).current()
        except ValueError:
            project = None
        result["applications"] = [item for item in result["applications"]
                                  if not item.get("requires_project_flags")
                                  or project and all(bool(project.get(flag)) for flag in item["requires_project_flags"])]
        return result

    @router.get("/capabilities/{capability_id}")
    async def capability(capability_id: str):
        return _capability(capability_id, resolve_capability(capability_id))

    @router.get("/plugins/{plugin_id}/presets")
    async def plugin_presets(plugin_id: str):
        from ...modules.presets.plugins import plugin_presets as discover_presets
        try:
            return discover_presets(context, plugin_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/plugins/{plugin_id}/ui/{file_path:path}")
    async def plugin_ui_file(plugin_id: str, file_path: str):
        plugins, _ = PluginCatalog(workflows_path, context).scan()
        plugin = next((item for item in plugins if item["id"] == plugin_id), None)
        ui = (plugin or {}).get("application", {}).get("ui", {})
        if not plugin or not isinstance(ui, dict) or not ui.get("entry"):
            raise HTTPException(404, "插件没有独立 UI")
        root = (workflows_path / plugin["_plugin_folder"] / "ui" / "dist").resolve()
        target = (root / file_path).resolve()
        if root not in target.parents and target != root or not target.is_file():
            raise HTTPException(404, "插件 UI 资源不存在")
        return FileResponse(target)

    @router.post("/uploads")
    async def upload(file: UploadFile = File(...)):
        return await upload_handler(file)

    @router.get("/voices")
    async def voices():
        def preset_ready(item: dict[str, Any]) -> bool:
            sample_path = VoicePresets(context).sample_path(item)
            if not sample_path or not sample_path.is_file():
                return False
            ffprobe = shutil.which("ffprobe")
            if not ffprobe:
                return False
            try:
                result = subprocess.run(
                    [ffprobe, "-v", "error", "-show_entries", "format=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(sample_path)],
                    capture_output=True, text=True, check=True, timeout=10,
                )
                return 0 < float(result.stdout.strip())
            except (OSError, ValueError, subprocess.SubprocessError):
                return False

        return {"items": [
            {
                **_voice(item),
                "preset_id": item["preset_key"],
                "description": item.get("instruction", ""),
                "ready": preset_ready(item),
            }
            for item in VoicePresets(context).items()
        ]}

    def catalog_routes(domain: str, categories: set[str]):
        @router.get(f"/{domain}/presets")
        async def list_presets(category: str | None = None):
            if category and category not in categories:
                raise HTTPException(422, "无效的预设分类")
            return {"items": db.creative_presets(domain, category)}

    catalog_routes("music", {"style", "singer", "voice_texture", "preset"})
    catalog_routes("image", {"style"})

    @router.get("/image/styles")
    async def image_styles():
        file_styles, errors = await asyncio.to_thread(style_items)
        items = [{"id": item["id"], "name": item.get("name_cn") or item["name"], "source": "comfyui", "category": item.get("category", "")} for item in file_styles]
        items.extend(db.creative_presets("image", "style"))
        return {"items": items, "errors": errors}

    @router.get("/music/styles")
    async def music_styles():
        return {"items": db.creative_presets("music", "style")}

    @router.get("/music/singers")
    async def music_singers():
        return {"items": db.creative_presets("music", "singer")}

    @router.get("/music/voice-textures")
    async def music_voice_textures():
        return {"items": db.creative_presets("music", "voice_texture")}

    @router.get("/library")
    async def library(kind: str = "all", offset: int = 0, limit: int = 48, sort: str = "new", category_id: str | None = None, project_id: str | None = None):
        if project_id:
            authorized_project(project_id)
        result = await library_handler(kind=kind, offset=offset, limit=limit, sort=sort, category_id=category_id, _=None, project_id=project_id)
        result.pop("output_dir", None)
        return result

    @router.post("/collaborations", status_code=201)
    async def create_collaboration(request: CollaborationCreateRequest):
        config = resolve_capability(request.capability_id)
        capability = _capability(request.capability_id, config)
        if not capability["collaboration_supported"]:
            raise HTTPException(422, "当前能力不支持智能协作，请使用直接生成")
        if request.model_id != capability["model"] or request.mode_id != capability["mode"]:
            raise HTTPException(422, f"模型或模式与能力不匹配，应为 {capability['model']} / {capability['mode']}")
        if request.collaboration_mode not in capability["collaboration_modes"]:
            raise HTTPException(422, f"当前能力不支持 {request.collaboration_mode} 智能协作模式")
        _validate_duration(capability, request.settings.duration)
        _validate_input_roles(capability, request.inputs)
        counts = {media: sum(item.type == media for item in request.inputs) for media in ("image", "video", "audio")}
        for media, limits in capability["inputs"].items():
            if not limits["min"] <= counts[media] <= limits["max"]:
                raise HTTPException(422, f"{media} 素材需要 {limits['min']}-{limits['max']} 个，当前为 {counts[media]}")
        for asset in request.inputs:
            upload_path(asset.upload_id)
        collaboration_id = f"collab-{uuid.uuid4().hex[:16]}"
        kind, _, _ = _model_and_mode(request.capability_id, config)
        payload = request.model_dump()
        payload["kind"] = kind
        payload.update({
            "prompt_processing": "compile" if request.collaboration_mode == "quick" else request.collaboration_mode,
            "plugin_id": config.get("plugin_id"),
            "plugin_version": config.get("plugin_version"),
            "plugin_revision": config.get("plugin_revision"),
        })
        if request.project_id:
            authorized_project(request.project_id)
        try:
            payload["project_id"] = request.project_id or ProjectService(context).current()["id"]
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        try:
            payload["category_id"] = ProjectService(context).validate_category(payload["project_id"], request.category_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        item = db.create_collaboration({
            "id": collaboration_id,
            "capability_id": request.capability_id,
            "model_id": request.model_id,
            "mode_id": request.mode_id,
            "status": "queued",
            "project_id": payload["project_id"],
            "request": payload,
        })
        initial = request.message
        if request.prompt.strip():
            initial += f"\n\n现有描述词草稿：{request.prompt.strip()}"
        if request.lyrics.strip():
            initial += f"\n\n待创作歌词：\n{request.lyrics.strip()}"
        db.add_collaboration_message(collaboration_id, "user", initial)
        return await run_collaboration(item)

    @router.get("/collaborations")
    async def list_collaborations(project_id: str, active: bool = False):
        authorized_project(project_id)
        statuses = ("queued", "running", "needs_input", "awaiting_confirmation") if active else None
        return {"items": [public_collaboration(item) for item in db.collaborations(statuses, limit=1000, project_id=project_id)]}

    @router.post("/collaborations/{collaboration_id}/cancel")
    async def cancel_collaboration(collaboration_id: str):
        item = db.collaboration(collaboration_id)
        if not item:
            raise HTTPException(404, "智能协作会话不存在")
        authorized_project(item.get("project_id", ""))
        if not agent_cancel_handler:
            raise HTTPException(503, "协作取消服务不可用")
        return public_collaboration(await agent_cancel_handler(collaboration_id))

    @router.get("/collaborations/{collaboration_id}")
    async def get_collaboration(collaboration_id: str):
        item = db.collaboration(collaboration_id)
        if not item:
            raise HTTPException(404, "智能协作会话不存在")
        authorized_project(item.get("project_id", ""))
        return public_collaboration(item, include_messages=True)

    @router.post("/collaborations/{collaboration_id}/messages")
    async def send_collaboration_message(collaboration_id: str, request: CollaborationMessageRequest):
        async with context.collaboration_submission_lock:
            return await _send_collaboration_message(collaboration_id, request)

    async def _send_collaboration_message(collaboration_id: str, request: CollaborationMessageRequest):
        item = db.collaboration(collaboration_id)
        if not item:
            raise HTTPException(404, "智能协作会话不存在")
        authorized_project(item.get("project_id", ""))
        if item["status"] in {"submitted", "deleted"}:
            raise HTTPException(409, "当前会话已经提交，不能继续修改")
        if item["status"] in {"queued", "running"}:
            raise HTTPException(409, "当前会话仍在处理中")
        if item["status"] == "cancelled":
            raise HTTPException(409, "当前会话已经取消，不能继续修改")
        db.add_collaboration_message(collaboration_id, "user", request.message)
        return await run_collaboration(item)

    @router.get("/collaborations/{collaboration_id}/progress")
    async def collaboration_progress(collaboration_id: str):
        item = db.collaboration(collaboration_id)
        if not item:
            raise HTTPException(404, "智能协作会话不存在")
        authorized_project(item.get("project_id", ""))
        result = item.get("result", {})
        progress = item.get("progress", {})
        return {
            "id": collaboration_id,
            "status": item["status"],
            "revision": item.get("revision", 0),
            "stage": result.get("stage"),
            "progress_id": result.get("progress_id"),
            "stages": progress.get("stages", []),
            "updated_at": item["updated_at"],
        }

    async def _confirm_collaboration(collaboration_id: str, request: CollaborationConfirmRequest):
        item = db.collaboration(collaboration_id)
        if not item:
            raise HTTPException(404, "智能协作会话不存在")
        authorized_project(item.get("project_id", ""))
        if request.revision != item.get("revision"):
            raise HTTPException(409, f"方案版本已更新，当前版本为 {item.get('revision', 0)}")
        if item.get("job_id"):
            job = jobs().get(item["job_id"]) or db.job(item["job_id"])
            if job:
                return {**api_submission({"job_id": job["id"], "kind": job["kind"], "status": job["status"], "reused": True}, item["capability_id"]),
                        "collaboration_id": collaboration_id, "revision": item.get("revision", 0)}
        if item["status"] != "awaiting_confirmation":
            raise HTTPException(409, "当前方案尚未达到可确认状态")
        result = item.get("result", {})
        optimized_prompt = str(request.execution_prompt_en or result.get("optimized_prompt", "")).strip()
        optimized_prompt_zh = str(request.confirmed_prompt_zh or result.get("optimized_prompt_zh", "")).strip()
        if not optimized_prompt:
            raise HTTPException(409, "协作方案缺少可执行描述词")
        if not optimized_prompt_zh:
            raise HTTPException(409, "协作方案缺少对应的中文稿")
        source = item["request"].get("params", {}).get("_source_request", item["request"])
        pinned = source.get("plugin_revision")
        if pinned and pinned != resolve_capability(item["capability_id"]).get("plugin_revision"):
            raise HTTPException(409, "插件已更新，请新建会话并重新确认")
        settings = dict(source.get("settings", {}))
        patch = confirmation_overrides(resolve_capability(item["capability_id"]), source, result,
                                       item.get("project_id"))
        settings.update(patch.get("settings", {}))
        create_request = CreateRequest(
            capability_id=item["capability_id"],
            prompt=optimized_prompt,
            lyrics=patch.get("lyrics", source.get("lyrics", "")),
            inputs=[AssetInput.model_validate(value) for value in source.get("inputs", [])],
            settings=CreateSettings.model_validate(settings),
            parameters={**source.get("parameters", {}), **patch.get("parameters", {})},
        )
        create_request.settings.confirmed_prompt_zh = optimized_prompt_zh
        create_request.category_id = source.get("category_id")
        create_request.settings.execution_prompt_en = optimized_prompt
        optimized_shots = result.get("optimized_shots", [])
        if isinstance(optimized_shots, list) and optimized_shots:
            create_request.settings.shots = [str(value).strip() for value in optimized_shots if str(value).strip()]
        confirmation_key = f"confirm:{collaboration_id}:{request.revision}:{request.idempotency_key}" if request.idempotency_key else None
        if confirmation_key:
            existing = db.idempotent_job(confirmation_key)
            if existing:
                job = jobs().get(existing) or db.job(existing)
                if job:
                    db.update_collaboration(collaboration_id, {"status": "submitted", "job_id": existing})
                    return {**api_submission({"job_id": existing, "kind": job["kind"], "status": job["status"], "reused": True}, item["capability_id"]),
                            "collaboration_id": collaboration_id, "revision": request.revision}
        submission = await create_generation(
            create_request, parent_job_id=source.get("parent_job_id"),
            project_id=item.get("project_id") or source.get("project_id") or None,
        )
        if confirmation_key:
            db.save_idempotent_job(confirmation_key, submission["job_id"])
        db.update_collaboration(collaboration_id, {"status": "submitted", "job_id": submission["job_id"]})
        return {**submission, "collaboration_id": collaboration_id, "revision": request.revision}

    @router.post("/collaborations/{collaboration_id}/confirm", status_code=202)
    async def confirm_collaboration(collaboration_id: str, request: CollaborationConfirmRequest):
        async with context.collaboration_submission_lock:
            return await _confirm_collaboration(collaboration_id, request)

    @router.post("/assistant/chat")
    async def assistant_chat(request: agent_model):
        return await agent_handler(request)

    @router.post("/generations", status_code=202)
    async def create(request: CreateRequest, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
        async with context.collaboration_submission_lock:
            return await _create(request, idempotency_key)

    async def _create(request: CreateRequest, idempotency_key: str | None):
        # One public submission contract supports direct generation and the
        # model-aware collaboration path. The latter keeps the same session
        # until ambiguity is resolved, then confirms through this endpoint.
        if idempotency_key and len(idempotency_key) > 120:
            raise HTTPException(422, "Idempotency-Key 过长")
        if request.session_id:
            item = db.collaboration(request.session_id)
            if not item:
                raise HTTPException(404, "生成会话不存在")
            authorized_project(item.get("project_id", ""))
            if item["status"] in {"submitted", "deleted", "cancelled"}:
                raise HTTPException(409, "生成会话已经结束")
            if item["status"] in {"queued", "running"}:
                raise HTTPException(409, "生成会话仍在处理中，请稍后查询")
            if not request.answer.strip():
                raise HTTPException(422, "继续生成会话需要 answer")
            db.add_collaboration_message(request.session_id, "user", request.answer.strip())
            return await run_collaboration(item)

        if not request.capability_id:
            raise HTTPException(422, "capability_id 不能为空")
        if request.parent_job_id:
            parent = jobs().get(request.parent_job_id) or db.job(request.parent_job_id)
            if not parent:
                raise HTTPException(404, "原任务不存在")
            authorized_project(parent.get("project_id", ""))
            if request.project_id and request.project_id != parent.get("project_id"):
                raise HTTPException(422, "重新生成不能改变原任务的项目")
            request.project_id = parent.get("project_id")
            request.category_id = parent.get("category_id")
        if request.prompt_processing != "direct":
            config = resolve_capability(request.capability_id)
            capability = _capability(request.capability_id, config)
            supported_modes = {mode["id"] for mode in capability["processing_modes"]}
            if request.prompt_processing not in supported_modes:
                raise HTTPException(422, "当前能力不支持此 prompt_processing，可用值：" + ", ".join(sorted(supported_modes)))
        request = normalize_form(request, resolve_capability(request.capability_id))
        if request.prompt_processing != "direct":
            model_id = capability["model"]
            mode_id = capability["mode"]
            collaboration_mode = "quick" if request.prompt_processing == "compile" else "director"
            from ...modules.generation.plugins import validate_parameters
            try:
                request.parameters = validate_parameters(config, request.parameters)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            collaboration_id = f"collab-{uuid.uuid4().hex[:16]}"
            kind, _, _ = _model_and_mode(request.capability_id, config)
            payload = {
                "capability_id": request.capability_id,
                "parent_job_id": request.parent_job_id,
                "model_id": model_id,
                "mode_id": mode_id,
                "message": request.prompt.strip() or "请根据当前生成参数完成模型提示词处理。",
                "prompt": request.prompt,
                "lyrics": request.lyrics,
                "inputs": [item.model_dump() for item in request.inputs],
                "settings": request.settings.model_dump(),
                "collaboration_mode": collaboration_mode,
                "kind": kind,
                "prompt_processing": request.prompt_processing,
                "plugin_id": config.get("plugin_id"),
                "plugin_version": config.get("plugin_version"),
                "plugin_revision": config.get("plugin_revision"),
                "parameters": request.parameters,
            }
            if request.project_id:
                authorized_project(request.project_id)
            try:
                payload["project_id"] = request.project_id or ProjectService(context).current()["id"]
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            for asset in request.inputs:
                upload_path(asset.upload_id)
            try:
                payload["category_id"] = ProjectService(context).validate_category(payload["project_id"], request.category_id)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            value = {
                "id": collaboration_id,
                "capability_id": request.capability_id,
                "model_id": model_id,
                "mode_id": mode_id,
                "status": "queued",
                "project_id": payload["project_id"],
                "request": payload,
            }
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            scoped_key = hashlib.sha256(json.dumps([payload["project_id"], idempotency_key]).encode()).hexdigest() if idempotency_key else None
            try:
                item = db.create_collaboration(value, idempotency_key=scoped_key, fingerprint=fingerprint)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            if item["id"] != collaboration_id:
                if item["status"] == "failed" and item.get("result", {}).get("enqueue_failed"):
                    return {**await run_collaboration(item), "reused": True}
                return {**public_collaboration(item, include_messages=True), "reused": True}
            db.add_collaboration_message(collaboration_id, "user", payload["message"])
            return await run_collaboration(item)

        if idempotency_key:
            try:
                result = await submit_idempotent(context, db, request, idempotency_key, create_generation)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
            return api_submission(result, request.capability_id)
        return await create_generation(request, parent_job_id=request.parent_job_id, project_id=request.project_id)

    @router.get("/jobs")
    async def list_jobs(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), kind: str | None = None, status: str | None = None, project_id: str | None = None):
        try:
            project_id = project_id or ProjectService(context).current()["id"]
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        authorized_project(project_id)
        items = [api_job(item) for item in db.jobs(limit=None, project_id=project_id)]
        if kind:
            items = [item for item in items if item.get("kind") == kind]
        if status:
            items = [item for item in items if item.get("status") == status]
        return {"items": items[offset:offset + limit], "total": len(items), "next_offset": offset + limit if offset + limit < len(items) else None}

    @router.get("/jobs/{job_id}")
    async def get_job(job_id: str):
        item = jobs().get(job_id) or db.job(job_id)
        if not item:
            raise HTTPException(404, "任务不存在")
        authorized_project(item.get("project_id", ""))
        return api_job(item)

    @router.get("/jobs/{job_id}/wait")
    async def wait_job(job_id: str, timeout: int = Query(30, ge=0, le=120)):
        deadline = time.monotonic() + timeout
        while True:
            item = jobs().get(job_id) or db.job(job_id)
            if not item:
                raise HTTPException(404, "任务不存在")
            authorized_project(item.get("project_id", ""))
            if item.get("status") not in {"queued", "running"} or time.monotonic() >= deadline:
                return api_job(item)
            await asyncio.sleep(1)

    @router.get("/jobs/{job_id}/artifacts")
    async def job_artifacts(job_id: str):
        item = jobs().get(job_id) or db.job(job_id)
        if not item:
            raise HTTPException(404, "任务不存在")
        authorized_project(item.get("project_id", ""))
        return {"job_id": job_id, "items": api_job(item).get("artifacts", [])}

    @router.get("/jobs/{job_id}/inputs")
    async def job_inputs(job_id: str):
        item = jobs().get(job_id) or db.job(job_id)
        if not item:
            raise HTTPException(404, "任务不存在")
        authorized_project(item.get("project_id", ""))
        manifest_path = Path(item.get("manifest_path", ""))
        if not manifest_path.is_file():
            return {"job_id": job_id, "items": []}
        import json
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {"job_id": job_id, "items": [{
            "type": source.get("type"), "index": source.get("index"),
            "name": source.get("original_name"), "role": source.get("role"),
            "media_type": source.get("media_type"), "size": source.get("size"),
            "upload_id": source.get("upload_id"), "sha256": source.get("sha256"),
            "url": f"/v1/tasks/{job_id}/files/{source['path']}",
        } for source in manifest.get("inputs", [])]}

    @router.post("/jobs/{job_id}/cancel")
    async def cancel(job_id: str):
        item = jobs().get(job_id) or db.job(job_id)
        if not item:
            raise HTTPException(404, "任务不存在")
        authorized_project(item.get("project_id", ""))
        return await cancel_handler(job_id)

    @router.get("/plugin-actions")
    async def plugin_actions(scope: str | None = None, source_job_id: str | None = None,
                             automation: bool = False, source_kind: str | None = None,
                             include_unavailable: bool = False):
        if scope and scope not in {"resource", "workspace", "automation"}:
            raise HTTPException(422, "无效的插件动作范围")
        source = None
        if source_kind:
            if source_kind not in {"image", "video", "tts", "music", "audio"}:
                raise HTTPException(422, "无效的资源类型")
            source = {"kind": source_kind, "status": "completed", "external": True}
        if source_job_id:
            source = jobs().get(source_job_id) or db.job(source_job_id)
            if not source:
                raise HTTPException(404, "任务不存在")
        catalog = PluginCatalog(workflows_path, context)
        return {"items": public_actions(await asyncio.to_thread(discover_actions,
            catalog, scope=scope, source=source, automation_only=automation,
            context=context, include_unavailable=include_unavailable,
        ))}

    @router.get("/plugin-actions/{action_id}")
    async def plugin_action(action_id: str):
        action = PluginCatalog(workflows_path, context).actions().get(action_id)
        if not action:
            raise HTTPException(404, "插件动作不存在")
        return public_action(action)

    @router.post("/plugin-actions/{action_id}/execute", status_code=202,
                 response_model=PluginActionResponse, response_model_exclude_none=True)
    async def run_plugin_action(action_id: str, body: PluginActionExecuteRequest):
        if body.source_job_id and body.source_upload_id:
            raise HTTPException(422, "源任务和上传素材不能同时指定")
        source = None
        if body.source_upload_id:
            source = uploaded_source(context, body.source_upload_id)
        if body.source_job_id:
            source = jobs().get(body.source_job_id) or db.job(body.source_job_id)
            if not source:
                raise HTTPException(404, "任务不存在")
            authorized_project(source.get("project_id", ""))
        if body.project_id:
            authorized_project(body.project_id)
        catalog = PluginCatalog(workflows_path, context)
        result = await execute_action(catalog, action_id, body.inputs, context, submit,
                                      source=source, project_id=body.project_id, category_id=body.category_id,
                                      invoke_capability=invoke_plugin_capability)
        return api_submission(result, result.get("capability_id")) if result.get("job_id") else result

    @router.post("/jobs/{job_id}/regenerate", status_code=202)
    async def regenerate(job_id: str, request: RegenerateRequest):
        item = jobs().get(job_id) or db.job(job_id)
        if not item:
            raise HTTPException(404, "任务不存在")
        authorized_project(item.get("project_id", ""))
        original = hydrate_job(dict(item))
        capability_id = original.get("params", {}).get("capability_id") or original.get("generation", {}).get("capability_id")
        if not capability_id:
            raise HTTPException(422, "原任务缺少插件能力标识，请选择能力后重新提交")
        inputs = request.inputs
        if inputs is None:
            inputs = []
            manifest_path = Path(item.get("manifest_path", ""))
            if manifest_path.is_file():
                import json
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                for source in manifest.get("inputs", []):
                    source_path = manifest_path.parent / source["path"]
                    upload_id = uuid.uuid4().hex
                    shutil.copy2(source_path, upload_cache / f"{upload_id}{source_path.suffix}")
                    inputs.append(AssetInput(type=source["type"], upload_id=upload_id, role=source.get("role", "reference")))
        params = original.get("params", {})
        if request.settings is not None:
            settings = request.settings
        elif isinstance(params.get("api_settings"), dict):
            settings = CreateSettings.model_validate(params["api_settings"])
        else:
            ratio, resolution = _named_dimensions(item.get("width"), item.get("height"), item["kind"])
            settings = CreateSettings(
                ratio=ratio,
                resolution=resolution,
                duration=float(original.get("duration_seconds") or item.get("duration_seconds") or 5),
                variant=params.get("speed", "normal"),
                seed=params.get("seed"),
                style_id=params.get("style_id", ""),
                voice_id=original.get("character", ""),
                voice_speed=original.get("speed", 1.0),
                instruction=original.get("instruction", ""),
                shots=params.get("shots", []),
            )
        original_execution = str(
            params.get("execution_prompt_en") or settings.execution_prompt_en or ""
        ).strip()
        original_chinese = str(
            params.get("confirmed_prompt_zh") or settings.confirmed_prompt_zh or ""
        ).strip()
        if original_execution and request.prompt is not None and request.execution_prompt_en is None:
            raise HTTPException(422, "双语任务修改执行稿时请同时提交 execution_prompt_en 和 confirmed_prompt_zh")
        execution_prompt = str(request.execution_prompt_en or original_execution).strip()
        confirmed_prompt = str(request.confirmed_prompt_zh or original_chinese).strip()
        if execution_prompt or confirmed_prompt:
            if not execution_prompt or not confirmed_prompt:
                raise HTTPException(422, "英文执行稿和中文稿必须成对保存")
            settings.execution_prompt_en = execution_prompt
            settings.confirmed_prompt_zh = confirmed_prompt
        create_request = CreateRequest(
            capability_id=capability_id,
            category_id=item.get("category_id"),
            parameters=request.parameters if request.parameters is not None else params.get("plugin_parameters", {}),
            prompt=execution_prompt or (
                request.prompt if request.prompt is not None else original.get("prompt", original.get("text", ""))
            ),
            lyrics=request.lyrics if request.lyrics is not None else original.get("params", {}).get("lyrics", ""),
            inputs=inputs,
            settings=settings,
        )
        return await create_generation(create_request, parent_job_id=job_id, project_id=item.get("project_id"))

    return router
