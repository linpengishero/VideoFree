"""Shared processing runtime; model-specific modes are installed by plugins."""

import asyncio
import time
import uuid

from ...bootstrap import context
from ...core.errors import GatewayError
from ..generation.plugins import PluginCatalog
from ..settings.plugins import PluginSettings
from ..shared.plugin_runtime import PluginRuntime
from .analysis import parse_agent_result
from . import service
from .prompts import agent_skill_prompt, agent_capability


def confirmation_overrides(config, source, result, project_id=None):
    """Apply plugin-owned generation adjustments without changing session identity."""
    handler = PluginCatalog(context.paths.plugins, context).confirmation(config)
    if handler is None:
        return {}
    runtime = PluginRuntime(config["plugin_id"], PluginSettings(context).runtime(config["plugin_id"]),
                            context, project_id=project_id, category_id=(source or {}).get("category_id"))
    patch = handler(source, result, runtime)
    if not isinstance(patch, dict) or set(patch) - {"settings", "parameters", "lyrics"}:
        raise ValueError("Invalid plugin confirmation result")
    for field in ("settings", "parameters"):
        if field in patch and not isinstance(patch[field], dict):
            raise ValueError(f"Plugin confirmation {field} must be an object")
    return patch


async def single(request):
    progress_id = request.progress_id or f"progress-{uuid.uuid4().hex[:12]}"
    session = context.agent_sessions.get(request.session_id) if request.session_id else None
    if request.session_id and not session:
        raise ValueError("智能体会话已失效，请重新发送生成需求")
    if session is None:
        session = {"id": f"agent-{uuid.uuid4().hex[:12]}", "created_at": time.time(), "messages": [
            {"role": "system", "content": agent_skill_prompt(request.model, request.mode, request.params.get("capability_id"))},
            {"role": "user", "content": service.initial_agent_message(request)},
        ]}
        context.agent_sessions[session["id"]] = session
        if len(context.agent_sessions) > 50:
            oldest = min(context.agent_sessions.values(), key=lambda item: item["created_at"])
            context.agent_sessions.pop(oldest["id"], None)
    else:
        session["messages"].append({"role": "user", "content": request.message})
    try:
        service.start_agent_progress(progress_id, [{"id": "optimize", "label": "提示词优化"}])
        content = await asyncio.to_thread(service.call_agent_model, session["messages"], 2500)
        result = await asyncio.to_thread(service.repair_agent_result, session["messages"], parse_agent_result(content), request.model, request.mode)
    except Exception as exc:
        service.fail_agent_progress(progress_id, str(exc))
        raise
    session["messages"].append({"role": "assistant", "content": content})
    service.finish_agent_progress(progress_id, result["status"])
    return {"session_id": session["id"], "progress_id": progress_id, **result}


def resolve_processing(request):
    catalog = PluginCatalog(context.paths.plugins, context)
    capability_id = request.params.get("capability_id")
    try:
        config = agent_capability(request.model, request.mode, capability_id, request.kind)
    except ValueError as exc:
        raise GatewayError(422, "当前模型与模式未注册智能处理能力") from exc
    processing_mode = request.params.get("processing_mode") or ("compile" if request.collaboration_mode == "quick" else "director")
    pinned = request.params.get("_plugin_revision")
    if pinned and pinned != config["plugin_revision"]:
        raise GatewayError(409, "插件已更新，请新建协作会话，避免旧会话使用新的处理规则")
    if processing_mode not in {item['id'] for item in config.get('processing_modes', [])} or processing_mode == 'direct':
        raise GatewayError(422, '当前能力不支持此智能处理模式')
    return config, processing_mode


async def dispatch(request):
    config, processing_mode = resolve_processing(request)
    catalog = PluginCatalog(context.paths.plugins, context)
    try:
        handler = catalog.handler(config, processing_mode)
        if handler is None:
            raise ValueError("直接生成模式不创建智能会话")
        runtime = PluginRuntime(
            plugin_id=config["plugin_id"],
            configuration=PluginSettings(context).runtime(config["plugin_id"]),
            _single=single,
            _call_model=service.call_agent_model,
            _context=context,
            project_id=request.project_id,
            category_id=request.category_id,
        )
        result = await handler(request, runtime)
        if not isinstance(result, dict) or result.get("status") not in {"ready", "needs_input"}:
            raise ValueError("插件处理结果必须返回 ready 或 needs_input")
        if result["status"] == "needs_input" and (not result.get("session_id") or not result.get("questions")):
            raise ValueError("插件需要补充信息，但没有返回会话 ID 和问题")
        return result
    except ValueError as exc:
        raise GatewayError(502, str(exc)) from exc
