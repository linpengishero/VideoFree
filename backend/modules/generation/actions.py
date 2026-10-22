# Copyright (c) 2026 VideoFree Studio individual project author and contributors.
# Part of VideoFree Studio: https://github.com/linpengishero/VideoFreeStudio
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Plugin-declared action discovery and execution preparation."""

import mimetypes
import asyncio
import inspect
import json
from pathlib import Path
import shutil
from typing import Any
import uuid

from jsonschema import Draft202012Validator
from referencing.exceptions import Unresolvable

from ..settings.plugins import PluginSettings
from ..shared.plugin_runtime import PluginRuntime
from ...core.schemas import GenerateRequest, TTSRequest
from ...core.errors import GatewayError
from .plugin_ui import form_values
from .plugins import PluginCatalog, validate_parameters


PRIVATE_ACTION_FIELDS = {"handler", "availability_handler", "plugin_folder", "plugin_revision"}


def action_matches_source(action: dict[str, Any], source: dict[str, Any]) -> bool:
    if action.get("scope") != "resource":
        return False
    if source.get("status") != "completed" or source.get("kind") not in action.get("source_types", []):
        return False
    try:
        return Draft202012Validator(action.get("source_schema", {})).is_valid(source)
    except (Unresolvable, ValueError, TypeError):
        return False


def action_availability(catalog, action, source, context=None):
    if not action_matches_source(action, source):
        return {"available": False, "reason": "素材类型、状态或来源不符合插件要求"}
    try:
        handler = catalog.availability(action)
        if not handler:
            return {"available": True}
        runtime = PluginRuntime(action["plugin_id"], PluginSettings(context).runtime(action["plugin_id"]), context, project_id=source.get("project_id"), category_id=source.get("category_id")) if context else None
        result = handler({"action": action, "source": source}, runtime)
        if not isinstance(result, dict) or type(result.get("available")) is not bool:
            raise ValueError("Invalid availability result")
        return result
    except Exception:
        return {"available": False, "reason": "插件无法验证所需源文件，请检查源素材和插件"}


def discover_actions(catalog: PluginCatalog, *, scope: str | None = None,
                     source: dict[str, Any] | None = None,
                     automation_only: bool = False, context=None,
                     include_unavailable: bool = False) -> list[dict[str, Any]]:
    result = []
    for action in catalog.actions().values():
        if scope and action["scope"] != scope:
            continue
        if automation_only and not action.get("automation", False):
            continue
        if source is not None:
            if not action_matches_source(action, source):
                continue
            availability = action_availability(catalog, action, source, context)
            if not availability["available"] and not include_unavailable:
                continue
            action = {**action, **availability}
        result.append(action)
    return result


def public_action(action: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in action.items() if key not in PRIVATE_ACTION_FIELDS}


def public_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [public_action(action) for action in actions]


def uploaded_source(context, upload_id):
    """Build a server-trusted source descriptor; never accept client provenance."""
    from .task_store import TaskStore
    value = f"upload:{upload_id}"
    path = TaskStore(context.paths.tasks, context.paths.uploads).upload_path(value)
    if not path or not path.is_file():
        raise GatewayError(404, "上传的源素材不存在或已过期")
    kind = (mimetypes.guess_type(path.name)[0] or "").split("/", 1)[0]
    if kind not in {"image", "video", "audio"}:
        raise GatewayError(422, "不支持的源素材格式")
    return {"kind": kind, "status": "completed", "external": True, "upload": value}


def _validate_input_schema(schema: dict[str, Any], values: dict[str, Any]) -> None:
    json.dumps(values, allow_nan=False)
    error = next(Draft202012Validator(schema).iter_errors(values), None)
    if error:
        path = ".".join(str(part) for part in error.absolute_path) or "inputs"
        raise ValueError(f"{path}: {error.message}")


def _snapshot_action_inputs(action: dict[str, Any], supplied: dict[str, Any], options: dict[str, Any]) -> dict[str, Any]:
    """Persist the effective public action values without UI-only containers."""
    result = dict(supplied)
    for field in action.get("ui", {}).get("fields", []):
        bind = field.get("bind", "")
        if field.get("component") == "dimensions":
            continue
        parts = bind.split(".")
        if len(parts) == 2:
            value = options.get(parts[0], {}).get(parts[1])
            if value is not None:
                result.setdefault(parts[0], {})[parts[1]] = value
        elif bind in options and options[bind] is not None:
            result[bind] = options[bind]
    return result


async def prepare_action(catalog: PluginCatalog, action_id: str, inputs: dict[str, Any],
                         context, source: dict[str, Any] | None = None, project_id=None, category_id=None,
                         submit=None, invoke_capability=None):
    action = catalog.actions().get(action_id)
    if not action:
        raise GatewayError(404, f"插件动作不存在: {action_id}")
    if action["scope"] == "resource":
        if source is None:
            raise GatewayError(422, "当前素材不支持此插件动作")
        availability = await asyncio.to_thread(action_availability, catalog, action, source, context)
        if not availability["available"]:
            raise GatewayError(422, availability.get("reason", "当前素材不支持此插件动作"))
    try:
        _validate_input_schema(action["input_schema"], inputs)
        options = form_values(action["ui"], inputs) if "ui" in action else dict(inputs)
    except (ValueError, TypeError, Unresolvable) as exc:
        raise GatewayError(422, str(exc)) from exc

    configs = catalog.capabilities()
    config = configs.get(action.get("capability_id"))
    try:
        if config and ("ui" in action or not action.get("handler")):
            options["parameters"] = validate_parameters(config, options.get("parameters", {}))
        configuration = PluginSettings(context).runtime(action["plugin_id"])
    except ValueError as exc:
        raise GatewayError(422, str(exc)) from exc
    from ..collaboration.service import call_agent_model
    runtime = PluginRuntime(
        plugin_id=action["plugin_id"],
        configuration=configuration,
        _context=context,
        project_id=project_id,
        category_id=category_id,
        _call_model=call_agent_model,
        _submit=submit,
        _invoke_capability=invoke_capability,
    )
    try:
        handler = catalog.action_handler(action)
    except ValueError as exc:
        # A plugin revision can change after the catalog snapshot was loaded.
        # Surface that operational condition as a retryable conflict instead
        # of leaking it as an unhandled 500 from the HTTP route.
        if "插件文件已修改" in str(exc):
            raise GatewayError(409, str(exc), headers={"X-Plugin-Restart-Required": "true"}) from exc
        raise GatewayError(422, str(exc)) from exc
    if handler:
        try:
            request = {"action": action, "source": source, "inputs": options}
            if inspect.iscoroutinefunction(handler):
                result = await handler(request, runtime)
            else:
                result = await asyncio.to_thread(handler, request, runtime)
                if inspect.isawaitable(result):
                    result = await result
        except ValueError as exc:
            raise GatewayError(422, str(exc)) from exc
        except RuntimeError as exc:
            raise GatewayError(409, str(exc)) from exc
        if isinstance(result, dict):
            try:
                json.dumps(result, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise GatewayError(502, "插件动作返回了不可序列化的结果") from exc
            return result
        if not isinstance(result, tuple) or len(result) != 2 or not isinstance(result[1], (GenerateRequest, TTSRequest)):
            raise GatewayError(502, "插件动作必须返回 JSON 对象或 (kind, 生成请求)")
        if not config or result[0] != config["kind"]:
            raise GatewayError(502, "插件动作生成类型与注册能力不一致")
        result[1].params["capability_id"] = action["capability_id"]
        result[1].params["_action_id"] = action["id"]
        result[1].params["_action_name"] = action["name"]
        result[1].params["_action_inputs"] = _snapshot_action_inputs(action, inputs, options)
        if action.get("model_name"):
            result[1].params["_action_model_name"] = action["model_name"]
        return result
    if source is None or config is None:
        raise GatewayError(422, "该动作需要插件处理器或源素材")
    result = _prepare_generation_action(source, action, config, options, context, runtime)
    result[1].params["_action_id"] = action["id"]
    result[1].params["_action_name"] = action["name"]
    result[1].params["_action_inputs"] = _snapshot_action_inputs(action, inputs, options)
    if action.get("model_name"):
        result[1].params["_action_model_name"] = action["model_name"]
    return result


async def execute_action(catalog, action_id, inputs, context, submit, *, source=None, project_id=None,
                         category_id=None, invoke_capability=None):
    """Resolve project ownership before executing any plugin code or side effects."""
    from ..projects import ProjectService
    if action_id not in catalog.actions():
        raise GatewayError(404, f"插件动作不存在: {action_id}")
    source_project = (source or {}).get("project_id")
    if source_project and project_id and source_project != project_id:
        raise GatewayError(422, "源素材与目标项目不一致")
    project_id = project_id or source_project
    if project_id:
        project = context.db.project(project_id)
        if not project or project.get("status") != "active":
            raise GatewayError(404, "项目不存在或已归档")
    else:
        try:
            project_id = ProjectService(context).current()["id"]
        except ValueError as exc:
            raise GatewayError(409, str(exc)) from exc
    prepared = await prepare_action(catalog, action_id, inputs, context, source, project_id, category_id,
                                    submit, invoke_capability)
    if isinstance(prepared, dict):
        return {"action_id": action_id, "status": "completed", "result": prepared}
    kind, request = prepared
    request.internal_project_id = project_id
    # Explicit action context wins; an empty source category must not erase it.
    request.category_id = category_id or (source.get("category_id") if source and not source.get("external") else None)
    if source and not source.get("external"):
        if isinstance(request, GenerateRequest):
            request.params["parent_job_id"] = source["id"]
        else:
            request.parent_job_id = source["id"]
    result = await submit(kind, request)
    return {**result, "status": result.get("status", "queued"), "action_id": action_id,
            "capability_id": catalog.actions()[action_id].get("capability_id")}


def _prepare_generation_action(source: dict[str, Any], action: dict[str, Any],
                               config: dict[str, Any], options: dict[str, Any],
                               context, runtime: PluginRuntime):
    artifacts = source.get("artifacts") or []
    name = artifacts[0].get("name") if artifacts else source.get("artifact_name")
    if source.get("external"):
        from .task_store import TaskStore
        path = TaskStore(context.paths.tasks, context.paths.uploads).upload_path(source["upload"])
    else:
        path = context.paths.artifacts / Path(name or "").name
    if not path or not path.is_file():
        raise GatewayError(404, "任务产物不存在")
    media = (mimetypes.guess_type(path.name)[0] or "application/octet-stream").split("/", 1)[0]
    if media not in {"image", "video", "audio"}:
        raise GatewayError(422, "不支持此产物格式")
    limits = config.get("references", {}).get(media, {})
    if not int(limits.get("min", 0)) <= 1 <= int(limits.get("max", 0)):
        raise GatewayError(422, "插件不接受此类型的源素材")
    original = source.get("request", {}) if source.get("external") else runtime.job_request(source)
    original_params = original.get("params", {})
    upload_id = uuid.uuid4().hex
    context.paths.uploads.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, context.paths.uploads / f"{upload_id}{path.suffix.lower()}")
    context.db.register_upload(upload_id)
    value = f"upload:{upload_id}"
    params = {
        "capability_id": action["capability_id"], "plugin_parameters": options["parameters"],
        "videos": [value] if media == "video" else [],
        "audios": [value] if media == "audio" else [],
        "parent_job_id": None if source.get("external") else source["id"],
        "width": original_params.get("width") or source.get("width") or 768,
        "height": original_params.get("height") or source.get("height") or 432,
        "execution_prompt_en": original_params.get("execution_prompt_en", ""),
        "confirmed_prompt_zh": original_params.get("confirmed_prompt_zh", ""),
        "speed": "normal", "video_model": config.get("model_family", ""),
    }
    return config["kind"], GenerateRequest(
        prompt=original_params.get("execution_prompt_en") or original.get("prompt") or "后期处理",
        mode=config["mode"], references=[value] if media == "image" else [], params=params,
        duration_seconds=original.get("duration_seconds") or source.get("duration_seconds") or 5,
    )
