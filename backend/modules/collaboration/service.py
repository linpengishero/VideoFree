"""Director collaboration orchestration and model gateway."""

import base64
import http.client
import json
import mimetypes
from pathlib import Path
import socket
import time
from typing import Any
import urllib.parse
import uuid

from ...bootstrap import context, comfyui_client
from ...core.errors import AgentCollaborationCancelled
from ...modules.settings import SettingsService
from ...core.schemas import AgentChatRequest
from .analysis import parse_agent_json, parse_agent_result
from .prompts import agent_capability

settings_service = SettingsService(context, comfyui_client)
AGENT_TIMEOUT_SECONDS = context.config.agent_timeout_seconds


def read_settings() -> dict[str, Any]:
    return settings_service.read()


from .progress import (
    fail as fail_agent_progress,
    finish as finish_agent_progress,
    start as start_agent_progress,
    update as update_agent_progress,
)


def agent_endpoint(base_url: str) -> str:
    value = base_url.rstrip("/")
    return value if value.endswith("/chat/completions") else value + "/chat/completions"


def ensure_agent_not_cancelled() -> None:
    collaboration_id = context.current_collaboration_id.get()
    if not collaboration_id:
        return
    item = context.db.collaboration(collaboration_id)
    if not item or item.get("status") in {"cancelled", "abandoned", "interrupted"}:
        raise AgentCollaborationCancelled()


def agent_http_post(url: str, payload: bytes, headers: dict[str, str]) -> dict[str, Any]:
    ensure_agent_not_cancelled()
    parsed = urllib.parse.urlsplit(url)
    connection_class = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_class(parsed.hostname, parsed.port, timeout=AGENT_TIMEOUT_SECONDS or None)
    collaboration_id = context.current_collaboration_id.get()
    if collaboration_id:
        with context.state_lock:
            context.active_agent_connections[collaboration_id] = connection
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    try:
        connection.request("POST", path, body=payload, headers=headers)
        response = connection.getresponse()
        body = response.read()
        ensure_agent_not_cancelled()
        if response.status >= 400:
            detail = body.decode("utf-8", errors="replace")
            error = ValueError(f"AI 服务 HTTP {response.status}: {detail[:1000]}")
            error.status = response.status
            raise error
        return json.loads(body)
    except (OSError, http.client.HTTPException) as exc:
        ensure_agent_not_cancelled()
        raise ValueError(f"无法连接 AI 服务: {exc}") from exc
    finally:
        connection.close()
        if collaboration_id:
            with context.state_lock:
                if context.active_agent_connections.get(collaboration_id) is connection:
                    context.active_agent_connections.pop(collaboration_id, None)


def normalized_thinking_mode(value: Any) -> str:
    mode = str(value or "medium").lower()
    return {"auto": "medium", "on": "medium"}.get(mode, mode) if mode in {"auto", "on", "off", "low", "medium", "high"} else "medium"


def apply_thinking_options(request_body: dict[str, Any], settings: dict[str, str], *, disabled: bool = False) -> bool:
    provider = str(settings.get("ai_provider", "custom")).lower()
    mode = "off" if disabled else normalized_thinking_mode(settings.get("ai_thinking_mode"))
    model = str(settings.get("ai_model", "")).lower()
    if provider == "deepseek":
        request_body["thinking"] = {"type": "disabled" if mode == "off" else "enabled"}
        return True
    if provider == "custom":
        request_body["chat_template_kwargs"] = {"enable_thinking": mode != "off"}
        if mode != "off":
            request_body["reasoning_effort"] = mode
        return True
    if provider == "openai" and mode != "off" and model.startswith(("o1", "o3", "o4", "gpt-5")):
        request_body["reasoning_effort"] = mode
        return True
    return False


def call_agent_chat(
    messages: list[dict[str, Any]],
    max_tokens: int = 2500,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    *,
    _disable_thinking: bool = False,
    _plain_request: bool = False,
    _disable_rich_media: bool = False,
) -> dict[str, Any]:
    ensure_agent_not_cancelled()
    settings = read_settings()
    base_url = settings.get("ai_base_url", "").strip()
    model = settings.get("ai_model", "").strip()
    if not base_url or not model:
        raise ValueError("请先在设置中填写 AI API Base URL 和模型名称")
    outbound_messages = strip_rich_agent_media(messages) if _disable_rich_media else messages
    request_body = {
        "model": model,
        "messages": materialize_agent_messages(outbound_messages),
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if tools:
        request_body.update({"tools": tools, "tool_choice": tool_choice or "auto", "parallel_tool_calls": True})
    has_optional_thinking = False if _plain_request else apply_thinking_options(request_body, settings, disabled=_disable_thinking)
    payload = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    api_key = settings.get("ai_api_key", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        result = agent_http_post(agent_endpoint(base_url), payload, headers)
    except ValueError as exc:
        if getattr(exc, "status", None) == 400 and has_optional_thinking:
            return call_agent_chat(messages, max_tokens, tools, tool_choice, _plain_request=True, _disable_rich_media=_disable_rich_media)
        if not _disable_rich_media and has_rich_agent_media(messages) and rich_media_compatibility_error(exc):
            return call_agent_chat(messages, max_tokens, tools, tool_choice, _plain_request=_plain_request, _disable_rich_media=True)
        raise
    try:
        choice = result["choices"][0]
        message = choice["message"]
        finish_reason = str(choice.get("finish_reason", ""))
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("AI 服务返回了无法识别的数据") from exc
    content = message.get("content", "") if isinstance(message, dict) else ""
    if isinstance(content, list):
        content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    tool_calls = message.get("tool_calls", []) if isinstance(message, dict) else []
    reasoning = message.get("reasoning_content", "") if isinstance(message, dict) else ""
    if finish_reason == "length" and not tool_calls:
        if str(reasoning).strip() and not _disable_thinking:
            return call_agent_chat(messages, max_tokens, tools, tool_choice, _disable_thinking=True, _plain_request=_plain_request, _disable_rich_media=_disable_rich_media)
        raise ValueError("AI 输出达到长度上限，请提高输出上限或减少当前阶段加载的技能")
    if not str(content).strip() and not tool_calls:
        if str(reasoning).strip() and not _disable_thinking:
            return call_agent_chat(messages, max_tokens, tools, tool_choice, _disable_thinking=True, _plain_request=_plain_request, _disable_rich_media=_disable_rich_media)
        raise ValueError("AI 服务未返回最终内容；模型可能耗尽了输出长度或响应格式不兼容")
    return {
        "content": str(content).strip(),
        "tool_calls": tool_calls if isinstance(tool_calls, list) else [],
        "finish_reason": finish_reason,
    }


def call_agent_model(messages: list[dict[str, Any]], max_tokens: int = 2500) -> str:
    response = call_agent_chat(messages, max_tokens)
    if response["tool_calls"]:
        raise ValueError("AI 在非工具阶段返回了工具调用")
    return response["content"]


def repair_agent_result(messages: list[dict[str, Any]], result: dict[str, Any], model: str, mode: str, validator=None) -> dict[str, Any]:
    def prompt_issues(prompt):
        return validator(prompt, model, mode) if validator else (["empty optimized_prompt"] if not prompt.strip() else [])
    if result.get("status") == "needs_input" and result.get("questions"):
        return result
    issues = prompt_issues(result.get("optimized_prompt", ""))
    if not result.get("optimized_prompt_zh"):
        issues.append("missing optimized_prompt_zh")
    if result.get("status") == "needs_input":
        issues.append("needs_input requires at least one question with text and selectable options")
    if not issues:
        return result
    correction = {"role": "user", "content": "Your response failed this executable contract: " + "; ".join(issues) + ". Return the same JSON contract again. If clarification is needed, return needs_input with questions containing text and selectable options. Otherwise return ready with complete optimized_prompt and optimized_prompt_zh for the active mode. Keep the user's intent and reference mapping. Do not use ellipses, placeholders, or unfinished text. Return JSON only."}
    repaired = parse_agent_result(call_agent_model(messages + [correction], 7000))
    if repaired.get("status") == "needs_input" and repaired.get("questions"):
        return repaired
    repaired_issues = prompt_issues(repaired.get("optimized_prompt", ""))
    if not repaired.get("optimized_prompt_zh"):
        repaired_issues.append("missing optimized_prompt_zh")
    if repaired.get("status") != "ready" or repaired_issues:
        raise ValueError("智能协作生成的最终提示词未通过格式校验：" + "; ".join(repaired_issues or issues))
    return repaired


def initial_agent_message(request: AgentChatRequest) -> list[dict[str, Any]]:
    counts = {"image": 0, "video": 0, "audio": 0}
    inventory = []
    content: list[dict[str, Any]] = []
    multimodal = str(read_settings().get("ai_multimodal_video", "true")).lower() in {"1", "true", "yes", "on"}
    for reference in request.references:
        if reference.kind not in counts:
            continue
        counts[reference.kind] += 1
        label = {"image": "Picture", "video": "Video", "audio": "Audio"}[reference.kind]
        item_label = f"<{label} {counts[reference.kind]}>"
        inventory.append({"label": item_label, "name": reference.name, "media_type": reference.media_type})
        media_url = reference.data_url if multimodal and reference.data_url else None
        if media_url and reference.kind == "image":
            # H3 quick conversion must inspect reference ownership and visual
            # conflicts before rewriting the prompt; low-detail input makes
            # that preflight unreliable for faces, props, and environments.
            content.append({"type": "image_url", "image_url": {"url": media_url, "detail": "high"}})
        elif media_url and reference.kind == "video":
            content.append({"type": "video_url", "video_url": {"url": media_url}})
        # Quick conversion needs the stable <Audio N> identity and declared
        # role, not the binary waveform. Text-only local models often reject
        # OpenAI's input_audio message part before prompt conversion starts.
        elif media_url and reference.kind == "audio" and request.collaboration_mode != "quick":
            suffix = Path(reference.name).suffix.lower().lstrip(".") or "wav"
            content.append({"type": "input_audio", "input_audio": {"data": media_url, "format": suffix}})
    context = {
        "user_request": request.message,
        "generation": {
            "kind": request.kind,
            "model": request.model,
            "mode": request.mode,
            "duration_seconds": request.duration_seconds,
            "aspect_ratio": request.ratio,
            "resolution": request.resolution,
            "mode_parameters": {
                key: value for key, value in request.params.items() if not key.startswith("_")
            },
        },
        "ordered_references": inventory,
        "reference_vision": "enabled" if multimodal else "disabled; use filenames and user-provided descriptions only",
        "explicit_user_assertions": "Treat any reference-role statement in user_request (for example, 'Picture 1 and Picture 2 are characters, Picture 3 is the street') as confirmed intent. Do not ask the user to reconfirm an explicitly stated mapping; only ask about roles that remain unstated and materially ambiguous.",
    }
    content.insert(0, {"type": "text", "text": "Analyze this generation request and follow the required JSON response contract:\n" + json.dumps(context, ensure_ascii=False, indent=2)})
    return content


from .media import (
    collaboration_directory,
    has_rich_media as has_rich_agent_media,
    is_compatibility_error as rich_media_compatibility_error,
    materialize_messages as materialize_agent_messages,
    materialize_reference as materialize_agent_reference,
    strip_rich_media as strip_rich_agent_media,
)


def staged_generation_context(request: AgentChatRequest) -> dict[str, Any]:
    counts = {"image": 0, "video": 0, "audio": 0}
    references = []
    for reference in request.references:
        if reference.kind not in counts:
            continue
        counts[reference.kind] += 1
        label = {"image": "Picture", "video": "Video", "audio": "Audio"}[reference.kind]
        references.append({
            "label": f"<{label} {counts[reference.kind]}>",
            "name": reference.name,
            "media_type": reference.media_type,
        })
    return {
        "kind": request.kind,
        "model": agent_capability(request.model, request.mode, request.params.get("capability_id")).get("model_id", request.model),
        "mode": request.mode,
        "duration_seconds": request.duration_seconds,
        "aspect_ratio": request.ratio,
        "resolution": request.resolution,
        "mode_parameters": {
            key: value for key, value in request.params.items() if not key.startswith("_")
        },
        "review_mode": request.review_mode,
        "ordered_references": references,
    }
