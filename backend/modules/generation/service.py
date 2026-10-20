# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Generation domain services, durable task packages, and workers."""

import asyncio
import base64
import json
import hashlib
import logging
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import time
from typing import Any
import urllib.error
import urllib.parse
import uuid

from ...bootstrap import context, comfyui_client
from ...core.errors import JobCancelled
from ...integrations.comfyui.compiler import (
    apply_input_overrides, apply_media_bindings, apply_parameter_bindings,
    comfy_queue_contains,
    fit_aligned_dimensions, history_is_complete, history_media,
    prune_workflow,
    replace_prompt, validate_reference_counts,
)
from ...integrations.comfyui.workflow_loader import convert_workflow, workflow_from_png
from ...integrations.comfyui.errors import describe_failure
from ...integrations.native import NativeExecutionCancelled, NativeExecutionContext, NativeExecutionResult
from ..presets.style_library import apply_style, catalog
from ..presets.voices import VoicePresets
from ..settings import SettingsService
from ..settings.plugins import PluginSettings
from ...core.schemas import GenerateRequest, TTSRequest
from ..shared.plugin_runtime import PluginRuntime
from ..projects import ProjectService
from .state import assert_job_transition
from .task_store import TaskStore
from .workflow_registry import WorkflowRegistry
from .plugins import PluginCatalog


async def submit_idempotent(ctx, db, request, key, submit):
    """Serialize keyed submissions within a project."""
    project_id = request.project_id or ProjectService(ctx).current()['id']
    ProjectService(ctx).validate_category(project_id, request.category_id)
    request = request.model_copy(update={'project_id': project_id})
    scoped_key = 'generate:' + hashlib.sha256(json.dumps([project_id, key]).encode()).hexdigest()
    fingerprint = hashlib.sha256(json.dumps(request.model_dump(), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    async with ctx.generation_idempotency_lock:
        existing = db.idempotent_job(scoped_key, fingerprint)
        if existing and (item := db.job(existing)):
            return {'job_id': existing, 'kind': item['kind'], 'status': item['status'], 'reused': True}
        result = await submit(request, parent_job_id=request.parent_job_id, project_id=project_id)
        db.save_idempotent_job(scoped_key, result['job_id'], fingerprint)
        return result
ARTIFACTS = context.paths.artifacts
TASKS = context.paths.tasks
UPLOAD_CACHE = context.paths.uploads
WORKFLOWS = context.paths.plugins
settings_service = SettingsService(context, comfyui_client)
logger = logging.getLogger(__name__)


def generation_error_info(message: str) -> dict[str, Any]:
    return describe_failure(message)


def registry_service() -> WorkflowRegistry:
    return WorkflowRegistry(WORKFLOWS, node_definitions, context)


def task_store() -> TaskStore:
    return TaskStore(TASKS, UPLOAD_CACHE)


def plugin_runtime(config, job_id):
    return PluginRuntime(
        config["plugin_id"], PluginSettings(context).runtime(config["plugin_id"]), context,
        project_id=context.jobs[job_id].get("project_id"),
        category_id=context.jobs[job_id].get("category_id"),
    )

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
    return comfyui_client.node_definitions(kinds, {})


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
        if context.jobs[job_id].get("status") == "cancelled" and status != "cancelled":
            raise JobCancelled()
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


def create_task_package(job: dict[str, Any], parent_job_id: str | None = None) -> Path:
    return task_store().create(job, parent_job_id)


def hydrate_job_request(job: dict[str, Any]) -> dict[str, Any]:
    return task_store().hydrate(job)


def update_task_manifest(job_id: str, **values: Any) -> None:
    task_store().update_manifest(job_id, **values)




def workflow_registry() -> dict[str, dict[str, Any]]:
    return registry_service().all()






def generation_metadata(kind: str, payload: dict[str, Any]) -> dict[str, str]:
    """Create one durable identity snapshot for every generation task."""
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    action_id = str(params.pop("_action_id", ""))
    action_name = str(params.pop("_action_name", ""))
    action_model_name = str(params.pop("_action_model_name", ""))
    explicit_id = params.get("capability_id")
    mode = str(payload.get("mode", ""))
    variant = str(params.get("speed", "")) if kind == "video" else ""
    if not explicit_id:
        raise ValueError("必须指定插件 capability_id")
    config = registry_service().capability(explicit_id, variant)
    capability_id = str(explicit_id)
    family = str(config.get("model_family", config.get("model_id", "")))
    executor = str(config.get("executor", "comfyui"))
    execution_plane = str(config.get("execution_plane", "local"))
    native_model = str(params.get("native_model") or config.get("model") or "")
    model_id = native_model or str(config.get("model_id", family))
    provider_name = str(config.get("provider_name", "ComfyUI" if executor == "comfyui" else executor))
    existing = payload.get("generation") if isinstance(payload.get("generation"), dict) else {}
    return {
        **{key: str(value) for key, value in existing.items() if value is not None},
        "capability_id": capability_id,
        "provider_id": executor,
        "provider_name": provider_name,
        "model_family": family,
        "model_id": model_id,
        "model_name": action_model_name or str(config.get("model_name") or config.get("selector_model", {}).get("name") or family),
        "model_version": native_model if native_model and native_model != family else "",
        "mode_id": action_id or mode,
        "mode_name": action_name or str(config.get("mode_name", config.get("name", mode))),
        "variant_id": variant,
        "variant_name": str(config.get("label", variant)),
        "executor": executor,
        "execution_plane": execution_plane,
        "workflow_id": capability_id,
        "plugin_id": str(config.get("plugin_id", "")),
        "plugin_version": str(config.get("plugin_version", "")),
        "plugin_revision": str(config.get("plugin_revision", "")),
    }


def job_execution_plane(job: dict[str, Any]) -> str:
    request = job.get("request") if isinstance(job.get("request"), dict) else {}
    generation = request.get("generation") if isinstance(request.get("generation"), dict) else {}
    plane = str(generation.get("execution_plane", "")).strip()
    if plane:
        return plane
    try:
        if job.get("kind") == "tts" and "text" in request:
            config = tts_config(TTSRequest(**request))
        else:
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


def workflow_for(kind: str, name: str | None) -> dict[str, Any]:
    return registry_service().load(kind, name)


def collect_outputs(job_id: str, outputs, config) -> list[Path]:
    paths, seen = [], set()
    media_types = {"images": ".png", "gifs": ".mp4", "audio": ".wav", "videos": ".mp4"}
    for media_key, value in history_media(outputs, config.get("output_nodes")):
        identity = (media_key, value.get("filename"), value.get("subfolder", ""), value.get("type", "output"))
        if identity in seen:
            continue
        seen.add(identity)
        data = download_output(value)
        if not data:
            raise RuntimeError(f"ComfyUI 返回了空产物: {value['filename']}")
        suffix = Path(value["filename"]).suffix.lower() or media_types[media_key]
        target = ARTIFACTS / f"{job_id}_{len(paths)}{suffix}"
        target.write_bytes(data)
        paths.append(target)
    if not paths:
        raise RuntimeError("ComfyUI 执行完成，但注册的最终输出节点没有返回素材")
    return paths


def validate_voice_preset(config: dict[str, Any], character: str) -> dict[str, Any]:
    if config.get("mode") != "preset":
        return {}
    presets = VoicePresets(context)
    preset = presets.get(character)
    if not preset:
        raise ValueError("声音预设不存在")
    if preset.get("plugin_id") != config.get("plugin_id"):
        raise ValueError("声音预设不属于当前插件")
    sample = presets.sample_path(preset)
    if not sample or not sample.is_file():
        raise ValueError("声音预设缺少可用参考音频")
    return preset


def tts_config(request: TTSRequest) -> dict[str, Any]:
    explicit = request.params.get("capability_id")
    if not explicit:
        raise ValueError("必须指定插件 capability_id")
    config = registry_service().capability(explicit)
    if config.get("kind", "tts") != "tts" or config.get("mode", request.mode) != request.mode:
        raise ValueError("声音能力与生成类型或模式不匹配")
    return config


def run_tts(job_id: str, request: TTSRequest) -> list[Path]:
    config = tts_config(request)
    PluginCatalog(WORKFLOWS, context).assert_current(config)
    pinned = request.generation.get("plugin_revision")
    if pinned and config.get("plugin_revision") != pinned:
        raise ValueError("插件已更新，请重新提交生成任务")
    validate_reference_counts(config, 0, 0, 1 if request.reference_audio else 0)
    preset = validate_voice_preset(config, request.character)
    speech = PluginCatalog(WORKFLOWS, context).speech(config)
    if speech:
        request = speech(request, preset, plugin_runtime(config, job_id))
        if not isinstance(request, TTSRequest):
            raise ValueError("Plugin speech_handler must return TTSRequest")
    instruction = request.instruction.strip() or preset.get("instruction", "")
    request = request.model_copy(update={"instruction": instruction})
    if config.get("executor", "comfyui") != "comfyui":
        params = {**request.params, "instruction": instruction, "voice_id": request.character,
                  "voice_speed": request.speed, "speaker_preset": request.speaker_preset,
                  "audios": [request.reference_audio] if request.reference_audio else []}
        return run_native(job_id, "tts", GenerateRequest(
            prompt=request.text, mode=request.mode, params=params, generation=request.generation,
        ), config)
    workflow = workflow_for("tts", config["file"])
    reference_source = request.reference_audio
    reference_audio = (
        upload_local_file(Path(reference_source), job_id, 0)
        if reference_source and Path(reference_source).is_file()
        else upload_file(reference_source, job_id, 0, "audio") if reference_source else None
    )
    apply_parameter_bindings(workflow, config, GenerateRequest(prompt=request.text, params=request.params))
    apply_media_bindings(workflow, config, {"audio": [reference_audio] if reference_audio else []})
    for binding in config.get("prompt_bindings", []):
        inputs = workflow[str(binding["node"])]["inputs"]
        key, source = binding["input"], binding.get("source", "prompt")
        value = request.text if source == "prompt" else str(request.params.get(source, request.params.get("plugin_parameters", {}).get(source, "")))
        inputs[key] = str(inputs.get(key, "")) + "\n" + value if binding.get("append") else value
    PluginCatalog(WORKFLOWS, context).prepare(
        config, workflow, request, {"audio": [reference_audio] if reference_audio else []},
        job_id, request.text, plugin_runtime(config, job_id),
    )
    for binding in config.get("output_bindings", []):
        workflow[str(binding["node"])]["inputs"][binding["input"]] = ProjectService(context).output_prefix(context.jobs[job_id], "tts")
    if config.get("prune_to_outputs"):
        prune_workflow(workflow, config.get("output_nodes", []))
    pid = context.jobs[job_id].get("comfy_prompt_id")
    if not pid:
        result = comfy("/prompt", "POST", json.dumps({"prompt": workflow, "client_id": job_id}).encode())
        pid = result.get("prompt_id")
        if not pid:
            raise RuntimeError(f"ComfyUI rejected prompt: {result}")
        set_status(job_id, "running", comfy_prompt_id=pid)
    deadline = time.time() + 600
    while time.time() < deadline:
        if context.jobs[job_id].get("status") == "cancelled":
            raise JobCancelled()
        item = comfy(f"/history/{pid}").get(pid, {})
        if item.get("status", {}).get("status_str") == "error":
            raise RuntimeError(json.dumps(item.get("status"), ensure_ascii=False))
        if history_is_complete(item.get("status", {}), item.get("outputs", {})):
            return collect_outputs(job_id, item.get("outputs", {}), config)
        time.sleep(2)
    raise TimeoutError("TTS job timed out")


def generation_config(kind: str, request: GenerateRequest) -> dict[str, Any]:
    explicit = request.params.get("capability_id")
    if not explicit:
        raise ValueError("必须指定插件 capability_id")
    config = registry_service().capability(explicit, request.params.get("speed", "") if kind == "video" else "")
    if config.get("kind") != kind or config.get("mode") != request.mode:
        raise ValueError("能力与生成类型或模式不匹配")
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
    if kind == "image":
        from ..presets.style_library import apply_style
        styles = style_items(config.get("plugin_id"))
        selected = next((item for item in styles[0] if item["id"] == request.params.get("style_id")), None)
        if request.params.get("style_id") and selected is None:
            raise ValueError("Selected style no longer exists; refresh the style library")
        selected = selected or next((item for item in styles[0] if item.get("default")), None)
        prompt = apply_style(selected, prompt)
    snapshot = task_directory(job_id) / "config" / "executor_snapshot.json"
    snapshot.write_text(json.dumps({"registry": config, "prompt": prompt}, ensure_ascii=False, indent=2), encoding="utf-8")
    update_task_manifest(job_id, executor=config["executor"], executor_model=config.get("model", ""))
    runtime_config = PluginSettings(context).runtime(config["plugin_id"])
    api_key = str(runtime_config.pop("api_key", ""))
    try:
        from .plugins import PluginCatalog
        executor = PluginCatalog(WORKFLOWS, context).execution(config)
        if executor is None:
            raise ValueError("Plugin has no registered native executor")
        result = executor(NativeExecutionContext(
            job_id=job_id,
            config={**config, **runtime_config},
            prompt=prompt,
            references=request.references,
            params=request.params,
            api_key=api_key,
            output_dir=ARTIFACTS,
            media_loader=lambda value: media_value(value, job_id),
            cancelled=lambda: context.jobs[job_id].get("status") == "cancelled",
        ))
    except NativeExecutionCancelled as exc:
        raise JobCancelled() from exc
    if not isinstance(result, NativeExecutionResult):
        raise ValueError("Plugin executor must return NativeExecutionResult")
    if not result.paths or any(not path.is_file() or not path.resolve().is_relative_to(ARTIFACTS.resolve()) for path in result.paths):
        raise ValueError("Plugin executor must return existing files inside its output directory")
    if result.width and result.height:
        set_status(job_id, "running", width=result.width, height=result.height)
    return result.paths


def run_generation(job_id: str, kind: str, request: GenerateRequest) -> list[Path]:
    config = generation_config(kind, request)
    PluginCatalog(WORKFLOWS, context).assert_current(config)
    pinned = request.generation.get("plugin_revision") if request.generation else None
    if pinned and pinned != config.get("plugin_revision"):
        raise ValueError("插件已更新，请重新提交任务，避免排队任务使用不同的工作流")
    if config.get("executor", "comfyui") == "comfyui":
        return run_comfy(job_id, kind, request, config)
    return run_native(job_id, kind, request, config)


def run_comfy(job_id: str, kind: str, request: GenerateRequest, config: dict[str, Any] | None = None) -> list[Path]:
    config = config or generation_config(kind, request)
    if request.workflow and request.workflow != config["file"]:
        raise ValueError("custom workflow selection is disabled; use a registered mode")
    validate_reference_counts(config, len(request.references), len(request.params.get("videos", [])), len(request.params.get("audios", [])))
    if config.get("dimension_alignment"):
        width, height = fit_aligned_dimensions(request.params.get("width", 768), request.params.get("height", 432), int(config["dimension_alignment"]))
        request.params.update(width=width, height=height)
    prompt = request.prompt
    if config.get("task_instruction"):
        prompt = config["task_instruction"] + "\n用户需求：\n" + prompt
    if kind == "image" and request.params.get("style_prompt"):
        prompt += "\n\n风格要求：" + request.params["style_prompt"]
    workflow = workflow_for(kind, config["file"])
    if kind == "image":
        styles = style_items(config.get("plugin_id"))
        selected = next((s for s in styles[0] if s["id"] == request.params.get("style_id")), None)
        if request.params.get("style_id") and selected is None:
            raise ValueError("Selected style no longer exists; refresh the style library")
        selected = selected or next((s for s in styles[0] if s.get("default")), None)
        prompt = apply_style(selected, prompt)
    workflow = replace_prompt(workflow, prompt)
    apply_input_overrides(workflow, config)
    if kind == "video":
        free_comfy_memory()
    media = {
        "image": [upload_reference(value, job_id, i) for i, value in enumerate(request.references)],
        "audio": [upload_file(value, job_id, i, "audio") for i, value in enumerate(request.params.get("audios", []))],
        "video": [upload_file(value, job_id, i, "video") for i, value in enumerate(request.params.get("videos", []))],
    }
    apply_media_bindings(workflow, config, media)
    output_prefix = ProjectService(context).output_prefix(context.jobs[job_id], kind)
    request.params["_output_prefix"] = output_prefix
    for binding in config.get("prompt_bindings", []):
        inputs = workflow[str(binding["node"])]["inputs"]
        key, source = binding["input"], binding.get("source", "prompt")
        value = prompt if source == "prompt" else str(request.params.get(source, request.params.get("plugin_parameters", {}).get(source, "")))
        inputs[key] = str(inputs.get(key, "")) + "\n" + value if binding.get("append") else value
    apply_parameter_bindings(workflow, config, request)
    from .plugins import PluginCatalog
    PluginCatalog(WORKFLOWS, context).prepare(
        config, workflow, request, media, job_id, prompt, plugin_runtime(config, job_id),
    )
    for binding in config.get("output_bindings", []):
        workflow[str(binding["node"])].setdefault("inputs", {})[binding["input"]] = output_prefix
    for node in workflow.values():
        if node.get("class_type") in {"SaveImage", "SaveVideo", "SaveAudio", "VHS_VideoCombine"}:
            node.setdefault("inputs", {})["filename_prefix"] = output_prefix
    task_config = task_directory(job_id) / "config" / "workflow_snapshot.json"
    update_task_manifest(job_id, workflow_file=config.get("file"), workflow_variant=config.get("variant", ""))
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
            # Wait for the final history state. LTX and video nodes may expose
            # a preview file before the execution has actually completed.
            completed = history_is_complete(status, outputs)
            if completed:
                return collect_outputs(job_id, outputs, config)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            connection_failures += 1
            if connection_failures >= failure_limit:
                raise RuntimeError(f"ComfyUI API 连续 {connection_failures} 次不可达: {exc}") from exc
        time.sleep(2)


def cancel_generation(job_id: str) -> dict[str, Any]:
    with context.state_lock:
        item = context.jobs.get(job_id) or context.db.job(job_id)
        if not item:
            raise ValueError("job not found")
        if item.get("status") not in {"queued", "running"} or item.get("_publishing"):
            raise RuntimeError("任务已结束或正在归档，无法取消")
        context.jobs[job_id] = item
        set_status(job_id, "cancelled")
    if prompt_id := item.get("comfy_prompt_id"):
        try:
            # ComfyUI's global interrupt may kill a different client's running prompt.
            comfy("/queue", "POST", json.dumps({"delete": [prompt_id]}).encode())
        except Exception:
            logger.warning("Could not remove cancelled prompt from ComfyUI queue", exc_info=True)
    return {"id": job_id, "status": "cancelled"}


def process(job_id: str) -> None:
    with context.state_lock:
        job = context.jobs.get(job_id)
        if not job or job.get("status") == "cancelled":
            return
        context.executing_jobs.add(job_id)
    try:
        _process(job_id)
    finally:
        with context.state_lock:
            job.pop("_publishing", None)
            context.executing_jobs.discard(job_id)


def _process(job_id: str) -> None:
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
        if job["kind"] == "tts" and "text" in job["request"]:
            request = TTSRequest(**job["request"])
            paths = run_tts(job_id, request)
            config = tts_config(request)
        else:
            request = GenerateRequest(**job["request"])
            config = generation_config(job["kind"], request)
            paths = run_generation(job_id, job["kind"], request)
        with context.state_lock:
            if job.get("status") == "cancelled":
                raise JobCancelled()
            job["_publishing"] = True
        PluginCatalog(WORKFLOWS, context).resource_event("completed", context, job=job, request=request, config=config)
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


def style_items(plugin_id=None):
    from ..presets.style_library import items
    return items(context, plugin_id)


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
