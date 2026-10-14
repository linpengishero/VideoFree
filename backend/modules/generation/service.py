"""Generation domain services, durable task packages, and workers."""

import asyncio
import base64
import hashlib
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import time
from typing import Any
import urllib.error
import urllib.parse
import uuid

from ...bootstrap import context, comfyui_client
from ...core.errors import JobCancelled
from ...integrations.comfyui.compiler import (
    apply_h3_reference_bindings, apply_image_dimensions, apply_input_overrides,
    apply_media_bindings, apply_parameter_bindings, apply_storyboard_grid,
    comfy_queue_contains, configure_h3_generation_loras, configure_h3_lms_guide,
    configure_h3_latent_upscaler as _configure_h3_latent_upscaler,
    configure_qwen_image21_references,
    fit_aligned_dimensions, history_is_complete, history_media,
    inject_h3_checkpoint_save, prune_workflow, replace_h3_video_savers,
    replace_prompt, validate_reference_counts,
)
from ...integrations.comfyui.workflow_loader import convert_workflow, workflow_from_png
from ...integrations.native import NativeExecutionCancelled, NativeExecutionContext, execute_native
from ..presets.style_library import apply_style, catalog
from ..presets.voices import VOICE_PRESETS
from ..settings import SettingsService
from ..shared.schemas import GenerateRequest, TTSRequest
from ..projects import ProjectService
from .state import assert_job_transition
from .task_store import TaskStore
from .workflow_registry import WorkflowRegistry

ARTIFACTS = context.paths.artifacts
TASKS = context.paths.tasks
UPLOAD_CACHE = context.paths.uploads
WORKFLOWS = context.paths.workflows
WORKFLOW_REGISTRY = context.paths.workflow_registry
settings_service = SettingsService(context, comfyui_client)
logger = logging.getLogger(__name__)


def registry_service() -> WorkflowRegistry:
    return WorkflowRegistry(WORKFLOWS, WORKFLOW_REGISTRY, node_definitions)


def task_store() -> TaskStore:
    return TaskStore(TASKS, UPLOAD_CACHE)

def configured_grsai_key(settings: dict[str, Any] | None = None) -> str:
    return settings_service.configured_grsai_key(settings)

def comfy(path: str, method="GET", body: bytes | None = None) -> Any:
    return comfyui_client.request(path, method, body)


def normalize_combo_values(workflow):
    from ...integrations.comfyui.workflow_loader import is_dynamic_file_input, validate_choices
    definitions = node_definitions(n['class_type'] for n in workflow.values())
    # ComfyUI model folders are sometimes included in canvas exports but not
    # in the live dropdown value. Resolve only an unambiguous basename match.
    for node in workflow.values():
        fields = definitions.get(node['class_type'], {}).get('input', {})
        for key, spec in {**fields.get('required', {}), **fields.get('optional', {})}.items():
            if is_dynamic_file_input(node['class_type'], key):
                continue
            value = node.get('inputs', {}).get(key)
            if not isinstance(value, str) or not isinstance(spec, list):
                continue
            choices = spec[0] if isinstance(spec[0], list) else (spec[1].get('options') if spec[0] == 'COMBO' and len(spec) > 1 else None)
            if not choices or value in choices:
                continue
            matches = [choice for choice in choices if Path(str(choice)).name == Path(value).name]
            if len(matches) == 1:
                node['inputs'][key] = matches[0]
    validate_choices(workflow, definitions)


def node_definitions(kinds):
    from ...integrations.comfyui.workflow_loader import NODE_ALIASES
    return comfyui_client.node_definitions(kinds, NODE_ALIASES)


def free_comfy_memory() -> None:
    comfyui_client.free_memory()


def upload_cache_path(value: str) -> Path | None:
    return task_store().upload_path(value)


def media_value(value: str, job_id: str) -> tuple[bytes, str]:
    return task_store().media_value(value, job_id)


def upload_reference(value: str, job_id: str, index: int) -> str:
    body, media_type = media_value(value, job_id)
    suffix = task_extension(media_type) if media_type.startswith("image/") else ".png"
    return comfyui_client.upload_input(body, media_type, f"{job_id}_{index}{suffix}")


def upload_file(value: str, job_id: str, index: int, kind: str) -> str:
    body, detected_type = media_value(value, job_id)
    if kind == "video":
        ext = ".mp4" if detected_type == "video/mp4" else ".webm"
        content_type = "video/mp4" if ext == ".mp4" else "video/webm"
    else:
        if detected_type == "audio/wav": ext, content_type = ".wav", "audio/wav"
        elif detected_type == "audio/flac": ext, content_type = ".flac", "audio/flac"
        elif detected_type in {"audio/mp4", "audio/x-m4a"}: ext, content_type = ".m4a", "audio/mp4"
        elif detected_type == "audio/ogg": ext, content_type = ".ogg", "audio/ogg"
        else: ext, content_type = ".mp3", "audio/mpeg"
    return comfyui_client.upload_input(body, content_type, f"{job_id}_{index}{ext}")


def upload_local_file(path: Path, job_id: str, index: int) -> str:
    if not path.is_file():
        raise ValueError(f"本地音频不存在: {path.name}")
    media_type = mimetypes.guess_type(path.name)[0] or "audio/mpeg"
    return comfyui_client.upload_input(path.read_bytes(), media_type, f"{job_id}_{index}{path.suffix.lower() or '.mp3'}")


def download_output(value: dict[str, Any]) -> bytes:
    return comfyui_client.download_output(value)


def set_status(job_id: str, status: str, **extra: Any) -> None:
    with context.state_lock:
        assert_job_transition(str(context.jobs[job_id].get("status", "")), status)
        context.jobs[job_id].update(status=status, updated_at=time.time(), **extra)
    context.db.update_job(job_id, {"status": status, **extra, "completed_at": time.time() if status in {"completed", "failed", "cancelled"} else None})
    update_task_manifest(job_id, status=status, **{key: value for key, value in extra.items() if key in {"error", "elapsed_seconds"}})


def data_url_bytes(value: str) -> tuple[bytes, str]:
    return TaskStore.data_url_bytes(value)


def task_extension(media_type: str) -> str:
    return TaskStore.extension(media_type)


def task_directory(job_id: str) -> Path:
    return task_store().directory(job_id)


def write_json_atomic(path: Path, value: Any) -> None:
    TaskStore.write_json(path, value)


def create_task_package(job: dict[str, Any], parent_job_id: str | None = None) -> Path:
    return task_store().create(job, parent_job_id)


def hydrate_job_request(job: dict[str, Any]) -> dict[str, Any]:
    return task_store().hydrate(job)


def update_task_manifest(job_id: str, **values: Any) -> None:
    task_store().update_manifest(job_id, **values)


def h3_checkpoint_root() -> Path:
    return context.comfyui_output_dir / "MiniMaxH3" / "latent_checkpoints"


def h3_checkpoint_roots() -> tuple[Path, ...]:
    """Search both the configured path and ComfyUI's live local output path.

    Project assets are copied into the gateway library after completion, while
    H3 checkpoint nodes write their files directly into ComfyUI's output tree.
    The second location repairs installations that retained the former gateway
    fallback directory after project-library migration.
    """
    roots = [h3_checkpoint_root()]
    try:
        live_output = settings_service.local_comfyui_output_directory(settings_service.read())
    except (OSError, RuntimeError, ValueError, TypeError, KeyError):
        live_output = None
    if live_output:
        live_root = live_output / "MiniMaxH3" / "latent_checkpoints"
        if live_root.resolve() != roots[0].resolve():
            roots.append(live_root)
    return tuple(roots)


def h3_checkpoint_path(relative: str) -> Path | None:
    """Resolve a stored checkpoint filename without allowing path traversal."""
    filename = Path(relative).name
    if not filename or filename != relative:
        return None
    for root in h3_checkpoint_roots():
        candidate = (root / filename).resolve()
        if candidate.parent == root.resolve() and candidate.is_file():
            return candidate
    return None


def persist_h3_checkpoint(job_id: str, request: GenerateRequest) -> None:
    matches = sorted(
        (
            path for root in h3_checkpoint_roots()
            for path in root.glob(f"{job_id}_*.h3latent.safetensors")
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not matches:
        raise RuntimeError("H3 初稿完成，但未找到原生 latent 检查点")
    checkpoint = matches[0]
    relative = checkpoint.name
    digest = hashlib.sha256()
    with checkpoint.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)

    frames = max(5, round(request.duration_seconds * 24))
    request.params.update(
        latent_checkpoint=relative,
        latent_checkpoint_owner=job_id,
        latent_sha256=digest.hexdigest().upper(),
        latent_checkpoint_ready=True,
        latent_width=int(request.params.get("width", 768)),
        latent_height=int(request.params.get("height", 432)),
        latent_frames=frames + (5 - frames % 17) % 17,
        latent_fps=24,
        latent_size=checkpoint.stat().st_size,
        h3_checkpoint_kind=str(request.params.get("h3_checkpoint_kind") or "completed_draft_latent"),
        h3_resume_stage=str(request.params.get("h3_resume_stage") or "post_sampling"),
        h3_resume_step=int(request.params.get("h3_resume_step") or 0),
        h3_total_steps=int(request.params.get("h3_total_steps") or 0),
        h3_sigma_schedule_persisted=bool(request.params.get("h3_sigma_schedule_persisted", False)),
        h3_conditioning_cache_key=hashlib.sha256(
            json.dumps({
                "mode": request.mode,
                "speed": request.params.get("speed", "normal"),
                "prompt": request.prompt,
                "width": request.params.get("width"),
                "height": request.params.get("height"),
                "duration": request.duration_seconds,
            }, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    )
    stored = dict(context.jobs[job_id]["request"])
    stored["params"] = {**stored.get("params", {}), **request.params}
    context.jobs[job_id]["request"] = stored
    compact = dict(stored)
    compact.pop("references", None)
    compact.pop("reference_audio", None)
    compact["params"] = dict(compact.get("params", {}))
    compact["params"].pop("videos", None)
    compact["params"].pop("audios", None)
    context.db.update_job_request(job_id, compact)

    manifest_path = task_directory(job_id) / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        parameters = dict(manifest.get("parameters", {}))
        parameters["params"] = {**parameters.get("params", {}), **compact["params"]}
        manifest.pop("latent_checkpoint_warning", None)
        manifest.update(parameters=parameters, latent_checkpoint_ready=True)
        write_json_atomic(manifest_path, manifest)
        write_json_atomic(task_directory(job_id) / "config" / "request.json", compact)


def delete_h3_checkpoint(item: dict[str, Any]) -> None:
    params = (item.get("request") or {}).get("params", {})
    owner = str(params.get("latent_checkpoint_owner", "")).strip()
    if owner and owner != item.get("id"):
        return
    if not owner and (item.get("parent_job_id") or params.get("refine_mode")):
        return
    relative = str(params.get("latent_checkpoint", "")).strip()
    if not relative:
        return
    target = h3_checkpoint_path(relative)
    if target:
        target.unlink()


def recover_h3_checkpoints() -> int:
    """Restore H3 refine eligibility for completed jobs affected by old paths."""
    restored = 0
    for job in context.jobs.values():
        request_data = job.get("request") or {}
        params = request_data.get("params") or {}
        if (
            job.get("kind") != "video"
            or job.get("status") != "completed"
            or params.get("latent_checkpoint_ready")
            or params.get("video_model") != "minimax"
        ):
            continue
        try:
            persist_h3_checkpoint(job["id"], GenerateRequest(**request_data))
            restored += 1
        except (OSError, RuntimeError, TypeError, ValueError, KeyError):
            continue
    return restored


def workflow_registry() -> dict[str, dict[str, Any]]:
    return registry_service().all()


def registered_workflow(kind: str, mode: str, model: str = "", variant: str = "") -> dict[str, Any]:
    return registry_service().resolve(kind, mode, model, variant)


MODEL_NAMES = {
    "krea2": "Krea2",
    "qwen": "Qwen Image",
    "gpt_image": "GPT-Image",
    "minimax": "MiniMax H3",
    "ltx2_5": "LTX-2.5",
    "minimax_music3": "MiniMax Music 3",
    "ace_step": "ACE-Step 1.5",
    "qwen3_tts": "Qwen3-TTS",
    "cosyvoice3": "CosyVoice3",
    "rife": "RIFE",
    "gateway": "videofree",
}


MODE_NAMES = {
    "text_to_image": "文生图", "image_to_image": "图生图", "character": "角色版",
    "scene": "场景图", "storyboard_4": "四宫格", "storyboard_6": "六宫格",
    "text_to_video": "文生视频", "image_to_video": "图生视频",
    "first_last_frame": "首尾帧生视频", "multi_reference": "多主体参考视频",
    "reference": "全能参考", "create": "音乐创作", "background": "背景配乐", "preset": "预设音色",
    "describe": "声音设计", "split": "宫格分割", "krea2_upscale": "Krea2 高清增强",
    "interpolate": "视频补帧", "upscale": "视频放大", "lms_enhance": "LMS 清晰度增强",
}


def generation_metadata(kind: str, payload: dict[str, Any]) -> dict[str, str]:
    """Create one durable identity snapshot for every generation task."""
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    mode = str(payload.get("mode", ""))
    variant = str(params.get("speed", "")) if kind == "video" else ""
    if kind == "image":
        family = str(params.get("image_model") or ({"split": "gateway", "krea2_upscale": "krea2"}.get(mode, "krea2")))
    elif kind == "video":
        family = str(params.get("video_model") or ({"upscale": "ltx2_5", "interpolate": "rife"}.get(mode, "minimax")))
    elif kind == "music":
        family = str(params.get("music_model") or "minimax_music3")
    elif kind == "tts":
        family = str(payload.get("voice_model") or "qwen3_tts")
    else:
        family = "qwen3_tts"
    if family != "minimax":
        variant = ""
    capability_id = str(params.get("capability_id") or f"{kind}.{family}.{mode}")
    registry = workflow_registry()
    if capability_id not in registry:
        simple_id = f"{kind}.{mode}"
        capability_id = simple_id if simple_id in registry else capability_id
    config = registered_workflow(
        kind,
        mode,
        str(params.get("image_model", "")) if kind == "image" else str(params.get("video_model", "")) if kind == "video" else str(params.get("music_model", "")) if kind == "music" else "",
        variant if kind == "video" and family == "minimax" else "",
    )
    if kind == "tts":
        config = registered_workflow("tts", mode, family)
    executor = str(config.get("executor", "comfyui"))
    execution_plane = str(config.get("execution_plane", "local"))
    native_model = str(params.get("native_model") or config.get("model") or "")
    model_id = native_model if family == "gpt_image" and native_model else family
    provider_name = "GrisAI" if executor == "grsai" else "videofree" if executor == "image_split" else "ComfyUI"
    existing = payload.get("generation") if isinstance(payload.get("generation"), dict) else {}
    return {
        **{key: str(value) for key, value in existing.items() if value is not None},
        "capability_id": capability_id,
        "provider_id": executor,
        "provider_name": provider_name,
        "model_family": family,
        "model_id": model_id,
        "model_name": MODEL_NAMES.get(family, family),
        "model_version": native_model if native_model and native_model != family else "",
        "mode_id": mode,
        "mode_name": MODE_NAMES.get(mode, mode),
        "variant_id": variant,
        "variant_name": str(config.get("label", variant)),
        "executor": executor,
        "execution_plane": execution_plane,
        "workflow_id": capability_id,
    }


def job_execution_plane(job: dict[str, Any]) -> str:
    request = job.get("request") if isinstance(job.get("request"), dict) else {}
    generation = request.get("generation") if isinstance(request.get("generation"), dict) else {}
    plane = str(generation.get("execution_plane", "")).strip()
    if plane:
        return plane
    try:
        if job.get("kind") == "tts":
            return "local"
        config = generation_config(str(job.get("kind", "")), GenerateRequest(**request))
        return str(config.get("execution_plane", "local"))
    except (FileNotFoundError, RuntimeError, TypeError, ValueError):
        return "local"


def generation_runtime_health() -> dict[str, Any]:
    workers = list(context.worker_tasks)
    alive = sum(1 for task in workers if not task.done())
    failed = sum(1 for task in workers if task.done() and not task.cancelled())
    queue_size = context.job_queue.qsize() if context.job_queue else 0
    return {
        "queue": queue_size,
        "local_queue_size": queue_size,
        "local_workers_configured": context.config.generation_concurrency,
        "local_workers_alive": alive,
        "local_workers_failed": failed,
        "local_worker_failures_total": context.generation_worker_failures,
        "cloud_tasks_active": sum(1 for task in context.direct_generation_tasks.values() if not task.done()),
    }


def migrate_generation_metadata() -> None:
    """Backfill old task snapshots without changing their generation parameters."""
    for job in context.db.jobs(limit=None):
        request = dict(job.get("request") or {})
        if request.get("generation"):
            continue
        try:
            request["generation"] = generation_metadata(job["kind"], request)
        except (FileNotFoundError, RuntimeError, ValueError):
            continue
        context.db.update_job_request(job["id"], request)
        manifest_path = Path(job.get("manifest_path") or task_directory(job["id"]) / "manifest.json")
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                parameters = dict(manifest.get("parameters") or {})
                parameters["generation"] = request["generation"]
                manifest["parameters"] = parameters
                write_json_atomic(manifest_path, manifest)
                config_path = manifest_path.parent / "config" / "request.json"
                if config_path.is_file():
                    write_json_atomic(config_path, request)
            except (OSError, json.JSONDecodeError):
                continue


def workflow_for(kind: str, name: str | None) -> dict[str, Any]:
    return registry_service().load(kind, name)


def configure_h3_latent_upscaler(workflow: dict[str, Any], request: GenerateRequest) -> None:
    _configure_h3_latent_upscaler(workflow, request, comfy)


def run_tts(job_id: str, request: TTSRequest) -> None:
    config = registered_workflow("tts", request.mode, request.voice_model)
    workflow_path = WORKFLOWS / config["file"]
    if workflow_path.exists():
        workflow = workflow_for("tts", config["file"])
        validate_reference_counts(config, 0, 0, 1 if request.reference_audio else 0)
        if request.mode == "describe" and not request.instruction.strip():
            raise ValueError("voice description is required")
        preset = context.db.preset(request.character) or VOICE_PRESETS.get(request.character, {})
        instruction = request.instruction.strip() if request.mode == "describe" else preset.get("instruction", "")
        reference_source = request.reference_audio
        if request.voice_model == "cosyvoice3" and request.mode == "preset":
            sample_name = Path(str(preset.get("sample_audio_name", ""))).name
            sample_path = context.paths.voice_samples / sample_name if sample_name else None
            if sample_path and sample_path.is_file():
                reference_source = str(sample_path)
            elif not request.speaker_preset:
                raise ValueError("CosyVoice3 预设缺少参考音频或可用 speaker preset")
        reference_audio = (
            upload_local_file(Path(reference_source), job_id, 0)
            if reference_source and Path(reference_source).is_file()
            else upload_file(reference_source, job_id, 0, "audio") if reference_source else None
        )
        for node in workflow.values():
            if node.get('class_type') == 'Qwen3VoiceClone':
                node['inputs']['text'] = request.text
            if node.get("class_type") == "Qwen3VoiceDesign":
                node["inputs"]["text"] = request.text
                node["inputs"]["instruct"] = instruction or node["inputs"].get("instruct", "")
            if node.get("class_type") in {"FL_CosyVoice3_ZeroShot", "FL_CosyVoice3_Instruct2"}:
                node["inputs"]["text"] = request.text
                node["inputs"]["speed"] = request.speed
                if node.get("class_type") == "FL_CosyVoice3_Instruct2":
                    node["inputs"]["instruct_text"] = instruction or "请自然、清楚地说这句话。"
            if node.get("class_type") in {"FL_CosyVoice3_SpeakerClone", "FL_CosyVoice3_SpeakerInstruct2"}:
                node["inputs"]["text"] = request.text
                node["inputs"]["speed"] = request.speed
                node["inputs"]["speaker_preset"] = request.speaker_preset
            if reference_audio and node.get("class_type") == "LoadAudio":
                node["inputs"]["audio"] = reference_audio
        pid = context.jobs[job_id].get("comfy_prompt_id")
        if not pid:
            result = comfy("/prompt", "POST", json.dumps({"prompt": workflow, "client_id": job_id}).encode())
            pid = result.get("prompt_id")
            if not pid:
                raise RuntimeError(f"ComfyUI rejected prompt: {result}")
            set_status(job_id, "running", comfy_prompt_id=pid)
        deadline=time.time()+600
        while time.time()<deadline:
            if context.jobs[job_id].get("status") == "cancelled":
                raise JobCancelled()
            item=comfy(f"/history/{pid}").get(pid,{})
            if item.get("status", {}).get("status_str") == "error": raise RuntimeError(json.dumps(item.get("status"), ensure_ascii=False))
            for _, value in history_media(item.get("outputs", {})):
                name = value["filename"]
                target = ARTIFACTS / f"{job_id}_{Path(name).name}"
                target.write_bytes(download_output(value))
                return target
            time.sleep(2)
        raise TimeoutError("TTS job timed out")
    preset = VOICE_PRESETS.get(request.voice)
    command = preset.get("command") if preset else os.getenv("TTS_COMMAND")
    if not command:
        raise RuntimeError("TTS is not configured: set TTS_COMMAND or VOICE_PRESETS_JSON")
    out = ARTIFACTS / f"{job_id}.{request.format}"
    rendered = command.format(text=request.text, output=str(out), voice=request.voice)
    subprocess.run(shlex.split(rendered, posix=os.name != "nt"), shell=False, check=True, timeout=600)
    return out


def generation_config(kind: str, request: GenerateRequest) -> dict[str, Any]:
    config = registered_workflow(
        kind,
        request.mode,
        request.params.get('image_model', '') if kind == 'image' else request.params.get('video_model', '') if kind == 'video' else request.params.get('music_model', '') if kind == 'music' else '',
        request.params.get('speed', '') if kind == 'video' and request.params.get('video_model', 'minimax') != 'ltx2_5' else '',
    )
    native_model = str(request.params.get("native_model", "")).strip()
    if native_model and config.get("executor", "comfyui") != "comfyui":
        allowed = config.get("models", [config.get("model")])
        if native_model not in allowed:
            raise ValueError(f"unsupported native model: {native_model}")
        config = {**config, "model": native_model}
    return config


def run_native(job_id: str, kind: str, request: GenerateRequest, config: dict[str, Any]) -> list[Path]:
    if request.workflow:
        raise ValueError("原生能力不接受自定义工作流")
    validate_reference_counts(config, len(request.references), len(request.params.get("videos", [])), len(request.params.get("audios", [])))
    prompt = request.prompt
    if config.get("task_instruction"):
        prompt = config["task_instruction"] + "\n用户需求：\n" + prompt
    if kind == "image" and request.params.get("style_prompt"):
        prompt = f"{prompt}\n\n风格要求：{request.params['style_prompt']}"
    if kind == "image" and request.params.get("style_id"):
        from ..presets.style_library import apply_style
        selected = next((item for item in style_items()[0] if item["id"] == request.params["style_id"]), None)
        if selected is None:
            raise ValueError("Selected style no longer exists; refresh the style library")
        prompt = apply_style({}, selected, prompt)
    snapshot = task_directory(job_id) / "config" / "executor_snapshot.json"
    snapshot.write_text(json.dumps({"registry": config, "prompt": prompt}, ensure_ascii=False, indent=2), encoding="utf-8")
    update_task_manifest(job_id, executor=config["executor"], executor_model=config.get("model", ""))
    try:
        result = execute_native(config["executor"], NativeExecutionContext(
            job_id=job_id,
            config=config,
            prompt=prompt,
            references=request.references,
            params=request.params,
            api_key=configured_grsai_key() if config["executor"] == "grsai" else "",
            output_dir=ARTIFACTS,
            media_loader=lambda value: media_value(value, job_id),
            cancelled=lambda: context.jobs[job_id].get("status") == "cancelled",
        ))
    except NativeExecutionCancelled as exc:
        raise JobCancelled() from exc
    if result.width and result.height:
        set_status(job_id, "running", width=result.width, height=result.height)
    return result.paths


def run_generation(job_id: str, kind: str, request: GenerateRequest) -> list[Path]:
    config = generation_config(kind, request)
    if config.get("executor", "comfyui") == "comfyui":
        return run_comfy(job_id, kind, request, config)
    return run_native(job_id, kind, request, config)


def run_comfy(job_id: str, kind: str, request: GenerateRequest, config: dict[str, Any] | None = None) -> list[Path]:
    config = config or generation_config(kind, request)
    if config.get("h3_checkpoint_kind"):
        request.params.update(
            h3_checkpoint_kind=config["h3_checkpoint_kind"],
            h3_resume_stage=config.get("h3_resume_stage", config["h3_checkpoint_kind"]),
            h3_resume_step=int(config.get("h3_resume_step", 0)),
            h3_total_steps=int(config.get("h3_total_steps", 0)),
            h3_sigma_schedule_persisted=True,
        )
    if request.workflow and request.workflow != config["file"]:
        raise ValueError("custom workflow selection is disabled; use a registered mode")
    validate_reference_counts(
        config,
        len(request.references),
        len(request.params.get("videos", [])),
        len(request.params.get("audios", [])),
    )
    if kind == "video" and request.params.get("video_model", "minimax") in {"", "minimax", "minimax-h3"}:
        multiple = 64 if config.get("variant") == "latent_ultra_refine" else 32
        width, height = fit_aligned_dimensions(
            request.params.get("width", 768), request.params.get("height", 432), multiple,
        )
        request.params.update(width=width, height=height)
    prompt = request.prompt
    if config.get('task_instruction'):
        prompt = config['task_instruction'] + '\n用户需求：\n' + prompt
    if kind == "image" and request.params.get("style_prompt"):
        prompt = f"{prompt}\n\n风格要求：{request.params['style_prompt']}"
    workflow = workflow_for(kind, config['file'])
    task_config = task_directory(job_id) / "config" / "workflow_snapshot.json"
    if task_config.parent.is_dir():
        task_config.write_text(json.dumps({"registry": config, "workflow": workflow}, ensure_ascii=False, indent=2), encoding="utf-8")
        update_task_manifest(job_id, workflow_file=config.get("file"), workflow_variant=config.get("variant", ""))
    if kind == 'image':
        from ..presets.style_library import apply_style
        selected = None
        if request.params.get('style_id'):
            selected = next((s for s in style_items()[0] if s['id'] == request.params['style_id']), None)
            if selected is None:
                raise ValueError('Selected style no longer exists; refresh the style library')
        prompt = apply_style(workflow, selected, prompt)
    workflow = replace_prompt(workflow, prompt)
    apply_input_overrides(workflow, config)
    if kind == "image":
        apply_image_dimensions(workflow, config, request)
    if config.get('shot_nodes'):
        from ..presets.style_library import apply_style
        shots = request.params.get('shots', [])
        if not isinstance(shots, list) or len(shots) != len(config['shot_nodes']) or any(not isinstance(s, str) or not s.strip() for s in shots):
            raise ValueError('Four nonempty shot descriptions are required')
        shot_instruction = config.get(
            'shot_instruction',
            'Generate one cinematic frame. Image1 is the scene reference, image2 is character A, image3 is character B. Preserve identity, clothing and scene geometry. No collage, no text.',
        )
        for node_id, shot in zip(config['shot_nodes'], shots):
            styled = apply_style({}, selected, shot)
            workflow[node_id]['inputs']['prompt'] = shot_instruction + ' ' + styled
    for binding in config.get('prompt_bindings', []):
        inputs = workflow[binding['node']]['inputs']
        key = binding['input']
        source = binding.get('source', 'prompt')
        value = prompt if source == 'prompt' else str(request.params.get(source, ''))
        inputs[key] = str(inputs.get(key, '')) + '\n' + value if binding.get('append') else value
    if kind == 'music':
        for node in workflow.values():
            if node.get('class_type') == 'MiniMaxMusic3TextEncode':
                node['inputs']['max_duration'] = float(request.duration_seconds)
            elif node.get('class_type') == 'TextEncodeAceStepAudio1.5':
                node['inputs']['duration'] = float(request.duration_seconds)
                node['inputs']['lyrics'] = ''
            elif node.get('class_type') == 'EmptyAceStep1.5LatentAudio':
                node['inputs']['seconds'] = float(request.duration_seconds)
    if kind == "video": free_comfy_memory()
    uploaded = [upload_reference(value, job_id, i) for i, value in enumerate(request.references)]
    audios = [upload_file(value, job_id, i, "audio") for i, value in enumerate(request.params.get("audios", []))]
    videos = [upload_file(value, job_id, i, "video") for i, value in enumerate(request.params.get("videos", []))]
    apply_media_bindings(workflow, config, {"image": uploaded, "video": videos, "audio": audios})
    configure_qwen_image21_references(workflow, config, request, uploaded)
    for node in workflow.values():
        if config.get('prompt', {}).get('preserve_all'):
            continue
        if node.get("class_type") in {"CLIPTextEncode", "easy showAnything", "PrimitiveStringMultiline", "Krea2EditGroundedEncode"}:
            for key in ("text", "string", "value"):
                if key in node["inputs"]:
                    current = node["inputs"][key]
                    # Character four-view workflows intentionally carry a fixed
                    # layout/instruction suffix.  Do not erase it when the API
                    # injects the user's subject prompt; the workflow loader has
                    # already expanded {{prompt}} in that template.
                    if not (
                        node.get("class_type") == "PrimitiveStringMultiline"
                        and isinstance(current, str)
                        and "character reference sheet" in current.lower()
                        and "four" in current.lower()
                    ):
                        node["inputs"][key] = prompt
                    break
        if node.get("class_type") == "CreateVideo":
            node["inputs"].update(fps=24, bit_depth=8)
        if node.get("class_type") == "SaveVideo":
            # Current ComfyUI releases require this dynamic combo even if the
            # workflow was exported by an older release that omitted it.
            node["inputs"].setdefault("codec", "auto")
        if kind == "image" and node.get("class_type") == "SaveImage":
            node["inputs"]["filename_prefix"] = config.get("output_prefix", "MediaGateway/image")
    if uploaded and not config.get("media_bindings", {}).get("image"):
        loaders = [node for node in workflow.values() if node.get("class_type") == "LoadImage"]
        for node, filename in zip(loaders, uploaded):
            node["inputs"]["image"] = filename
    frame_nodes = [n for n in workflow.values() if n.get('class_type') == 'MiniMaxH3ImageToVideo']
    for frame_index, frame_node in enumerate(frame_nodes):
        frames = max(5, round(request.duration_seconds * 24))
        width, height = fit_aligned_dimensions(
            request.params.get('width', 768), request.params.get('height', 432), 32,
        )
        dimensions = {'width': width, 'height': height}
        for key, value in dimensions.items():
            frame_node['inputs'][key] = value
        frame_node['inputs']['length'] = frames + (5 - frames % 17) % 17
        for key in ('first_frame', 'last_frame'):
            frame_node['inputs'].pop(key, None)
        for i, filename in enumerate(uploaded):
            node_id = f'gateway_frame_{frame_index}_{i}'
            workflow[node_id] = {'class_type':'LoadImage', 'inputs':{'image':filename}}
            frame_node['inputs'][('first_frame','last_frame')[i]] = [node_id,0]
    apply_h3_reference_bindings(workflow, config, request, uploaded, videos, audios)
    apply_parameter_bindings(workflow, config, request)
    configure_h3_lms_guide(workflow, request)
    configure_h3_generation_loras(workflow, request)
    configure_h3_latent_upscaler(workflow, request)
    inject_h3_checkpoint_save(workflow, config, job_id)
    replace_h3_video_savers(workflow)
    for node in workflow.values():
        if node.get("class_type") == "MiniMaxH3NativeLatentCheckpointSaveT8Advanced":
            node["inputs"].update(filename_prefix=job_id, checkpoint_id=job_id)
    output_prefix = ProjectService(context).output_prefix(context.jobs[job_id], kind)
    for node in workflow.values():
        if node.get("class_type") in {"SaveImage", "SaveVideo", "SaveAudio", "VHS_VideoCombine"}:
            node.setdefault("inputs", {})["filename_prefix"] = output_prefix
    apply_storyboard_grid(
        workflow,
        config,
        request.params.get("width", 1024),
        request.params.get("height", 1024),
    )
    ltx_nodes = [node for node in workflow.values() if node.get("class_type") == "EmptyLTXVLatentVideo"]
    if ltx_nodes and config.get("dynamic_ltx_dimensions", True):
        # LTX canvas examples wire dimensions through helper nodes.  API input
        # values may safely replace those links, giving the gateway one stable
        # width/height/duration contract regardless of the canvas layout.
        width, height = fit_aligned_dimensions(
            request.params.get("width", 768), request.params.get("height", 432), 64,
        )
        frames = max(9, 1 + (round(request.duration_seconds * 24) // 8) * 8)
        for node in ltx_nodes:
            # These values are often linked to canvas helper nodes.  A linked
            # socket ignores a replacement widget value in API prompts.
            for key in ("width", "height", "length"):
                node["inputs"].pop(key, None)
            node["inputs"].update(width=width, height=height, length=frames)
        for node in workflow.values():
            if node.get("class_type") == "LTXVEmptyLatentAudio":
                node["inputs"].pop("frames_number", None)
                node["inputs"].pop("frame_rate", None)
                node["inputs"].update(frames_number=frames, frame_rate=24)
            if node.get("class_type") == "VHS_VideoCombine":
                node["inputs"].update(filename_prefix=output_prefix, save_output=True)
    if config.get("prune_to_outputs"):
        prune_workflow(workflow, config.get("output_nodes", []))
    normalize_combo_values(workflow)
    # Persist the exact API prompt after every registry binding and normalization.
    task_config.write_text(
        json.dumps({"registry": config, "workflow": workflow}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    prompt_id = context.jobs[job_id].get("comfy_prompt_id")
    if not prompt_id:
        result = comfy("/prompt", "POST", json.dumps({"prompt": workflow, "client_id": job_id}).encode())
        prompt_id = result.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI rejected prompt: {result}")
        set_status(job_id, "running", comfy_prompt_id=prompt_id)
    connection_failures = 0
    missing_prompt_polls = 0
    failure_limit = max(1, int(os.getenv("COMFYUI_FAILURE_LIMIT", "12")))
    while True:
        if context.jobs[job_id].get("status") == "cancelled":
            raise JobCancelled()
        try:
            history = comfy(f"/history/{prompt_id}")
            item = history.get(prompt_id, {})
            if not item:
                queue_state = comfy("/queue")
                connection_failures = 0
                if comfy_queue_contains(queue_state, prompt_id):
                    missing_prompt_polls = 0
                else:
                    missing_prompt_polls += 1
                    if missing_prompt_polls >= 5:
                        raise RuntimeError("ComfyUI 已丢失该任务：历史记录和执行队列中均不存在 prompt_id")
                time.sleep(2)
                continue
            connection_failures = 0
            missing_prompt_polls = 0
            if item.get("status", {}).get("status_str") == "error":
                raise RuntimeError(json.dumps(item.get("status"), ensure_ascii=False))
            status = item.get("status", {})
            status_name = status.get("status_str", "")
            if status_name == "error":
                raise RuntimeError(json.dumps(status, ensure_ascii=False))
            outputs = item.get("outputs", {})
            media_types = {"images": "image", "gifs": "video", "audio": "audio", "videos": "video"}
            # Wait for the final history state. LTX and video nodes may expose
            # a preview file before the execution has actually completed.
            completed = history_is_complete(status, outputs)
            if outputs and completed:
                paths = []
                seen = set()
                for media_key, value in history_media(outputs, config.get("output_nodes")):
                    identity = (media_key, value.get("filename"), value.get("subfolder", ""), value.get("type", "output"))
                    if identity in seen:
                        continue
                    seen.add(identity)
                    data = download_output(value)
                    if not data:
                        continue
                    output_kind = media_types[media_key]
                    name = value["filename"]
                    suffix = Path(name).suffix.lower() or {"image": ".png", "audio": ".wav", "video": ".mp4"}[output_kind]
                    target = ARTIFACTS / f"{job_id}_{len(paths)}{suffix}"
                    target.write_bytes(data)
                    paths.append(target)
                if paths:
                    if config.get("save_h3_latent"):
                        try:
                            persist_h3_checkpoint(job_id, request)
                        except Exception as exc:
                            request.params["latent_checkpoint_ready"] = False
                            set_status(job_id, "running", latent_checkpoint_warning=str(exc))
                            update_task_manifest(job_id, latent_checkpoint_ready=False, latent_checkpoint_warning=str(exc))
                        finally:
                            free_comfy_memory()
                    return paths
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            connection_failures += 1
            if connection_failures >= failure_limit:
                raise RuntimeError(f"ComfyUI API 连续 {connection_failures} 次不可达: {exc}") from exc
        time.sleep(2)


def process(job_id: str) -> None:
    job = context.jobs[job_id]
    started_at = time.time()
    logger.info("generation started", extra={"job_id": job_id, "stage": "generation", "kind": job.get("kind")})
    try:
        if job.get("status") == "cancelled":
            return
        job["request"] = hydrate_job_request(job)
        if job.get("status") == "cancelled":
            return
        set_status(job_id, "running")
        if job["kind"] == "tts":
            paths = [run_tts(job_id, TTSRequest(**job["request"]))]
        else:
            paths = run_generation(job_id, job["kind"], GenerateRequest(**job["request"]))
        if job.get("status") == "cancelled":
            raise JobCancelled()
        path = paths[0]
        published = ProjectService(context).publish(job, paths)
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        artifacts = [{
            "name": item.name,
            "url": f"/v1/artifacts/{item.name}",
            "media_type": mimetypes.guess_type(item.name)[0] or media_type,
            "size": item.stat().st_size if item.exists() else 0,
            "project_path": published[index]["relative_path"],
        } for index, item in enumerate(paths)]
        task_output_dir = task_directory(job_id) / "output"
        if task_output_dir.is_dir():
            for item in paths:
                destination = task_output_dir / item.name
                try:
                    os.link(item, destination)
                except OSError:
                    shutil.copy2(item, destination)
            update_task_manifest(job_id, status="completed", outputs=[{"type": "audio" if job["kind"] in {"tts", "music"} else job["kind"], "path": f"output/{item.name}", "media_type": mimetypes.guess_type(item.name)[0] or "application/octet-stream", "size": item.stat().st_size if item.exists() else 0} for item in paths])
        set_status(
            job_id,
            "completed",
            artifact_name=path.name,
            artifact_url=f"/v1/artifacts/{path.name}",
            elapsed_seconds=round(time.time() - started_at, 2),
            artifact_media_type=media_type,
            artifact_size=path.stat().st_size if path.exists() else 0,
            artifacts=artifacts,
            artifacts_json=json.dumps(artifacts, ensure_ascii=False),
        )
        for item in paths:
            context.db.add_artifact(job_id, item, mimetypes.guess_type(item.name)[0] or media_type)
        release_job_media(job)
        logger.info("generation completed", extra={"job_id": job_id, "stage": "generation", "duration_seconds": round(time.time() - started_at, 2)})
    except JobCancelled:
        set_status(job_id, "cancelled", elapsed_seconds=round(time.time() - started_at, 2))
        release_job_media(job)
        logger.info("generation cancelled", extra={"job_id": job_id, "stage": "generation", "duration_seconds": round(time.time() - started_at, 2)})
    except Exception as exc:
        if job.get("status") == "cancelled":
            update_task_manifest(job_id, status="cancelled", elapsed_seconds=round(time.time() - started_at, 2))
            release_job_media(job)
            return
        set_status(job_id, "failed", error=str(exc), elapsed_seconds=round(time.time() - started_at, 2))
        update_task_manifest(job_id, status="failed", error=str(exc), elapsed_seconds=round(time.time() - started_at, 2))
        release_job_media(job)
        logger.exception("generation failed", extra={"job_id": job_id, "stage": "generation", "duration_seconds": round(time.time() - started_at, 2), "error_code": type(exc).__name__})


async def worker() -> None:
    assert context.job_queue
    while True:
        job_id = await context.job_queue.get()
        try:
            await asyncio.to_thread(process, job_id)
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            job = context.jobs.get(job_id) or context.db.job(job_id)
            if job and job.get("status") in {"queued", "running"}:
                set_status(job_id, "failed", error=f"生成执行器异常退出: {exc}")
                update_task_manifest(job_id, status="failed", error=str(exc))
                release_job_media(job)
            logger.exception(
                "generation worker recovered from an unexpected failure",
                extra={"job_id": job_id, "stage": "generation", "error_code": type(exc).__name__},
            )
        finally:
            context.job_queue.task_done()


async def run_direct_generation(job_id: str) -> None:
    try:
        await asyncio.to_thread(process, job_id)
    except asyncio.CancelledError:
        raise
    except BaseException as exc:
        job = context.jobs.get(job_id) or context.db.job(job_id)
        if job and job.get("status") in {"queued", "running"}:
            set_status(job_id, "failed", error=f"云端执行器异常退出: {exc}")
            update_task_manifest(job_id, status="failed", error=str(exc))
            release_job_media(job)
        logger.exception(
            "direct generation failed unexpectedly",
            extra={"job_id": job_id, "stage": "generation", "error_code": type(exc).__name__},
        )


def start_direct_generation(job_id: str) -> asyncio.Task:
    existing = context.direct_generation_tasks.get(job_id)
    if existing and not existing.done():
        return existing
    task = asyncio.create_task(run_direct_generation(job_id), name=f"cloud-generation-{job_id}")
    context.direct_generation_tasks[job_id] = task

    def discard(completed: asyncio.Task) -> None:
        if context.direct_generation_tasks.get(job_id) is completed:
            context.direct_generation_tasks.pop(job_id, None)
        if not completed.cancelled():
            completed.exception()

    task.add_done_callback(discard)
    return task


def style_items():
    from ..presets.style_library import catalog
    root = Path(os.getenv('MEDIA_STYLE_DIR', str(context.comfyui_output_dir.parent / 'custom_nodes' / 'ComfyUI-Easy-Use' / 'styles')))
    return catalog(root)


def release_job_media(job: dict[str, Any]) -> None:
    """Drop large request payloads after the worker no longer needs them."""
    request = job.get("request")
    if not isinstance(request, dict):
        return
    request.pop("references", None)
    request.pop("reference_audio", None)
    if isinstance(request.get("params"), dict):
        request["params"].pop("videos", None)
        request["params"].pop("audios", None)
