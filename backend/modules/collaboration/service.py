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

from fastapi import HTTPException

from ...bootstrap import context, comfyui_client
from ...core.errors import AgentCollaborationCancelled
from ...modules.settings import SettingsService
from ...modules.shared.schemas import AgentChatRequest
from .analysis import (
    agent_prompt_issues, approved_dialogue_lines, director_capacity_issues,
    final_prompt_consistency_issues, missing_speed_numbers, parse_agent_json,
    parse_agent_result, parse_structured_stage, production_plan_digest,
    unapproved_action_durations,
)
from .prompts import (
    AGENT_MODEL_ALIASES, AGENT_SKILLS, DIRECTOR_CORE_SKILLS,
    director_skill_catalog, director_skill_planner_prompt, final_review_prompt,
    h3_compiler_prompt, h3_conformance_prompt, h3_conformance_review_prompt,
    h3_director_prompt, load_director_skill, read_agent_files,
    scene_design_stage_prompt, shot_direction_prompt,
)

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


def run_director_skill_planner(
    generation: dict[str, Any], requirements: dict[str, Any], user_requests: list[str],
) -> tuple[list[str], list[str]]:
    catalog = director_skill_catalog()
    allowed = {item["id"] for item in catalog}
    messages = [
        {"role": "system", "content": director_skill_planner_prompt()},
        {"role": "user", "content": json.dumps({
            "user_requests": user_requests,
            "generation": generation,
            "approved_requirements": requirements,
            "registered_skills": catalog,
        }, ensure_ascii=False)},
    ]
    try:
        result = parse_agent_json(call_agent_model(messages, 2500)) or {}
    except (ValueError, AgentCollaborationCancelled):
        result = {}
    selected: list[str] = []
    reasons: list[str] = []
    raw = result.get("selected_skills") if isinstance(result.get("selected_skills"), list) else []
    for item in raw:
        skill_id = str(item.get("id", "")).strip() if isinstance(item, dict) else str(item).strip()
        if skill_id in allowed and skill_id not in selected:
            selected.append(skill_id)
            if isinstance(item, dict) and str(item.get("reason", "")).strip():
                reasons.append(f"{skill_id}: {str(item['reason']).strip()}")
    # Core capabilities remain a deterministic fallback if the planner is unavailable.
    for capability in requirements.get("capabilities", []):
        core = DIRECTOR_CORE_SKILLS.get(str(capability))
        if core and core[0] not in selected:
            selected.append(core[0])
    if requirements.get("martial_arts_plan", {}).get("required") and "martial-arts-combat" not in selected:
        selected.append("martial-arts-combat")
    if requirements.get("shot_type") == "chase_motion" and "chase-motion" not in selected:
        selected.append("chase-motion")
    return selected[:8], reasons[:8]


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


def repair_agent_result(messages: list[dict[str, Any]], result: dict[str, Any], model: str, mode: str) -> dict[str, Any]:
    issues = agent_prompt_issues(result.get("optimized_prompt", ""), model, mode)
    if not result.get("optimized_prompt_zh"):
        issues.append("missing optimized_prompt_zh")
    if not issues:
        return result
    if result.get("status") == "needs_input" and not result.get("optimized_prompt"):
        return result
    correction = {"role": "user", "content": "Your ready prompt failed this executable contract: " + "; ".join(issues) + ". Return the same JSON contract again. Keep the user's intent and reference mapping, but rewrite optimized_prompt as a complete prompt for the active mode. Do not use ellipses, placeholders, or unfinished text. Return JSON only."}
    repaired = parse_agent_result(call_agent_model(messages + [correction], 7000))
    repaired_issues = agent_prompt_issues(repaired.get("optimized_prompt", ""), model, mode)
    if not repaired.get("optimized_prompt_zh"):
        repaired_issues.append("missing optimized_prompt_zh")
    if repaired.get("status") != "ready" or repaired_issues:
        raise ValueError("智能协作生成的最终提示词未通过格式校验：" + "; ".join(repaired_issues or issues))
    return repaired


def compile_h3_english(messages: list[dict[str, Any]], mode: str,
                       requirements: dict[str, Any] | None = None) -> dict[str, Any]:
    for attempt in range(2):
        raw = parse_agent_json(call_agent_model(messages, 7000)) or {}
        prompt = str(raw.get("optimized_prompt", "")).strip()
        issues = agent_prompt_issues(prompt, "minimax-h3", mode)
        issues.extend(f"missing approved speed value {number}" for number in missing_speed_numbers(prompt, requirements or {}))
        issues.extend(f"unapproved internal action duration {number} seconds" for number in unapproved_action_durations(prompt, requirements or {}))
        issues.extend(f"missing approved dialogue line {line}" for line in approved_dialogue_lines(requirements or {}) if line not in prompt)
        if raw.get("status") == "ready" and prompt and not issues:
            return {"status": "ready", "message": str(raw.get("message", "")).strip(),
                    "questions": [], "optimized_prompt": prompt}
        if attempt == 0:
            messages = [*messages, {"role": "user", "content":
                "The English H3 execution draft needs correction: " + "; ".join(issues or ["missing ready status or prompt"]) +
                ". Preserve approved speed anchors and only user-approved or necessary shot-cut timestamps. Remove invented internal action durations; "
                "link actions through physical momentum instead. Return the complete English draft in the same JSON contract, without placeholders."}]
    raise ValueError("导演成稿未能编译出完整英文 H3 执行稿：" + "; ".join(issues or ["missing ready status or prompt"]))


def conform_h3_draft(
    result: dict[str, Any], generation: dict[str, Any], requirements: dict[str, Any],
    user_requests: list[str] | None = None,
) -> dict[str, Any]:
    review_payload = {
        "original_user_requests": user_requests or [],
        "approved_requirements": requirements,
        "english_draft": result["optimized_prompt"],
    }
    try:
        review = parse_agent_json(call_agent_model([
            {"role": "system", "content": h3_conformance_review_prompt()},
            {"role": "user", "content": json.dumps(review_payload, ensure_ascii=False)},
        ], 2500)) or {}
    except ValueError as exc:
        result["revision_warning"] = f"通用契约检查未完成，保留导演初稿供人工确认：{exc}"
        return result
    issues = review.get("issues") if isinstance(review.get("issues"), list) else []
    issues = [item for item in issues if isinstance(item, dict) and str(item.get("problem", "")).strip()][:5]
    if review.get("conforms") is True and not issues:
        return result
    if not issues:
        result["revision_warning"] = "通用契约检查未返回可执行结论，保留导演初稿供人工确认。"
        return result
    messages = [
        {"role": "system", "content": h3_conformance_prompt()},
        {"role": "user", "content": json.dumps({
            **review_payload,
            "verified_contract_issues": issues,
        }, ensure_ascii=False)},
    ]
    try:
        return compile_h3_english(messages, generation["mode"], requirements)
    except ValueError as exc:
        result["revision_warning"] = f"通用契约一致性修订未完成，保留导演初稿供人工确认：{exc}"
        return result


def translate_h3_draft(english: str, generation: dict[str, Any], requirements: dict[str, Any]) -> str:
    raw = parse_agent_json(call_agent_model([
        {"role": "system", "content": read_agent_files([AGENT_SKILLS / "pipeline" / "h3-chinese-translation.md"])},
        {"role": "user", "content": json.dumps({"mode": generation["mode"], "english_execution_draft": english,
                                               "approved_dialogue_lines_zh": approved_dialogue_lines(requirements)}, ensure_ascii=False)},
    ], 7000)) or {}
    return str(raw.get("optimized_prompt_zh", "")).strip()


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
        "model": AGENT_MODEL_ALIASES.get(request.model, request.model),
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


def run_structured_stage(
    system_prompt: str,
    payload: dict[str, Any],
    required: tuple[str, ...],
    max_tokens: int,
    *,
    stage_label: str = "结构化阶段",
    baseline: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
    ]
    content = call_agent_model(messages, max_tokens)
    result = parse_structured_stage(content, baseline)
    missing = [key for key in required if not result or not result.get(key)]
    if missing:
        correction = {
            "role": "user",
            "content": "The previous response was not executable. Return one JSON object only and include complete values for: " + ", ".join(missing),
        }
        content = call_agent_model(messages + [{"role": "assistant", "content": content}, correction], max_tokens)
        result = parse_structured_stage(content, baseline)
    if not result or any(not result.get(key) for key in required):
        missing = [key for key in required if not result or not result.get(key)]
        raise ValueError(f"智能协作的{stage_label}没有返回完整结构（缺少 {', '.join(missing)}），请重试")
    return result, messages


def run_scene_designer(generation: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    result, _ = run_structured_stage(
        scene_design_stage_prompt(
            str(requirements.get("content_type", "general")),
            str(requirements.get("shot_type", "general")),
            action_level=str(requirements.get("action_level", "simple")),
            action_domain=str(requirements.get("action_domain", "none")),
            dialogue_required=bool(requirements.get("dialogue_required")),
            closeup_emotion_required=bool(requirements.get("closeup_emotion_required")),
        ),
        {"generation": generation, "approved_requirements": requirements},
        ("scene_intent", "duration_plan", "spatial_state", "beats"),
        6000,
        stage_label="场面与表演设计阶段",
    )
    result.setdefault("continuity_locks", [])
    result.setdefault("density_decisions", [])
    result.setdefault("generation_risks", [])
    return result


def run_shot_director(
    generation: dict[str, Any],
    requirements: dict[str, Any],
    scene_design: dict[str, Any],
) -> dict[str, Any]:
    result, messages = run_structured_stage(
        shot_direction_prompt(),
        {
            "generation": generation,
            "approved_requirements": requirements,
            "appearance_authority": requirements.get("appearance_authority", "text_only"),
            "approved_scene_design": scene_design,
        },
        ("camera_intent", "axis_strategy", "shot_count_decision", "shots", "global_locks"),
        6000,
        stage_label="镜头导演阶段",
    )
    structure = str(requirements.get("camera_structure", "continuous"))
    required_fields = {"id", "time_range", "dramatic_purpose", "framing", "camera", "focus", "depth_layers", "continuity", "cut_to_next"}
    def plan_issues(plan: dict[str, Any]) -> list[str]:
        shots = plan.get("shots") if isinstance(plan.get("shots"), list) else []
        decision = plan.get("shot_count_decision") if isinstance(plan.get("shot_count_decision"), dict) else {}
        issues = []
        valid_count = len(shots) == 1 if structure == "continuous" else len(shots) >= 2
        if not valid_count:
            issues.append(f"{structure} 结构需要{'恰好 1 个' if structure == 'continuous' else '至少 2 个'}镜头，当前只有 {len(shots)} 个")
        if str(decision.get("selected_count", "")) != str(len(shots)):
            issues.append("shot_count_decision.selected_count 必须等于 shots 数量")
        if not str(decision.get("rationale", "")).strip() or not str(decision.get("readability_check", "")).strip():
            issues.append("shot_count_decision 需要非空的 rationale 和 readability_check")
        if any(not isinstance(shot, dict) or not required_fields.issubset(shot) for shot in shots):
            issues.append("每个镜头必须包含 id、time_range、dramatic_purpose 及完整摄影和连续性字段")
        return issues

    issues = plan_issues(result)
    if issues:
        correction = {"role": "user", "content": (
            "Correct ONLY the shot plan. The approved camera_structure is " + structure + ". Problems: " +
            "; ".join(issues) + ". Keep the approved script, duration, dialogue, references, and ending. "
            "Return a complete JSON shot plan with the required shot count and matching shot_count_decision."
        )}
        repaired = parse_structured_stage(call_agent_model(
            [*messages, {"role": "assistant", "content": json.dumps(result, ensure_ascii=False)}, correction], 6000,
        ))
        if repaired:
            result = repaired
        issues = plan_issues(result)
    if issues:
        raise ValueError("镜头导演自动修正后仍未形成可执行方案：" + "；".join(issues))
    result.setdefault("simplifications", [])
    return result


def run_final_reviewer(
    generation: dict[str, Any],
    requirements: dict[str, Any],
    scene_design: dict[str, Any] | None,
    final_result: dict[str, Any],
    user_requests: list[str] | None = None,
    shot_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    review_context = {
        **requirements,
        "mode": generation.get("mode", ""),
        "duration_seconds": generation.get("duration_seconds"),
        "ordered_references": generation.get("ordered_references", []),
        "shot_plan": shot_plan,
    }
    deterministic_issues = final_prompt_consistency_issues(final_result, review_context)
    capacity_issues = director_capacity_issues(requirements, scene_design, shot_plan)
    deterministic_issues = list(dict.fromkeys([*deterministic_issues, *capacity_issues]))
    messages = [
        {"role": "system", "content": final_review_prompt()},
        {"role": "user", "content": json.dumps({
            "generation": generation,
            "original_user_requests": user_requests or [],
            "approved_requirements": requirements,
            "approved_scene_design": scene_design,
            "approved_shot_plan": shot_plan,
            "final_prompt_zh": final_result.get("optimized_prompt_zh", ""),
            "final_prompt_en": final_result.get("optimized_prompt", ""),
            "deterministic_issues": deterministic_issues,
        }, ensure_ascii=False, indent=2)},
    ]
    try:
        content = call_agent_model(messages, 3000)
    except ValueError:
        return {
            "mode": "internal",
            "summary": "自动总检查未完成，请人工确认成稿。",
            "hard_errors": deterministic_issues,
            "warnings": list(dict.fromkeys([*deterministic_issues, "自动总检查服务未完成，请重点核对最终成稿。"]))[:5],
            "compiler_corrections": [],
            "confirmed_strengths": [],
        }
    parsed = parse_agent_json(content) or {}
    summary = str(parsed.get("summary", "")).strip()
    if not summary:
        return {
            "mode": "internal",
            "summary": "自动总检查未返回可解析结果，请人工确认成稿。",
            "hard_errors": deterministic_issues,
            "warnings": list(dict.fromkeys([*deterministic_issues, "自动总检查未完成，请重点核对最终成稿。"]))[:5],
            "compiler_corrections": [],
            "confirmed_strengths": [],
        }
    warnings = parsed.get("warnings", []) if isinstance(parsed.get("warnings"), list) else []
    strengths = parsed.get("confirmed_strengths", []) if isinstance(parsed.get("confirmed_strengths"), list) else []
    return {
        "mode": "internal",
        "summary": summary,
        "hard_errors": deterministic_issues,
        "warnings": list(dict.fromkeys([*deterministic_issues, *(str(item).strip() for item in warnings if str(item).strip())]))[:5],
        "compiler_corrections": [],
        "confirmed_strengths": list(dict.fromkeys(str(item).strip() for item in strengths if str(item).strip()))[:3],
    }


def run_h3_production_pipeline(session: dict[str, Any], requirements: dict[str, Any], progress: Any = None) -> dict[str, Any]:
    generation = session["generation"]
    if progress: progress("skill_planning", "running", "正在根据镜头需求选择适用技能")
    selected_skill_ids, skill_reasons = run_director_skill_planner(
        generation, requirements, session.get("user_requests", []),
    )
    selected_skill_text = "\n\n".join(load_director_skill(skill_id) for skill_id in selected_skill_ids)
    if progress: progress("skill_planning", "completed", f"已加载 {len(selected_skill_ids)} 项适用技能")
    if progress: progress("compiler", "running", "正在按已加载技能生成 H3 英文执行稿")
    approved_digest = production_plan_digest(requirements, None, None)
    final_messages = [
        {"role": "system", "content": h3_director_prompt(generation["mode"], requirements, selected_skill_text)},
        {"role": "user", "content": json.dumps({
            "generation": generation,
            "approved_requirements": requirements,
            "director_contract": {
                "approved_plan_digest": approved_digest,
                "immutable_fields": [
                    "user intent", "character identities and roles", "exact dialogue", "reference ownership",
                    "duration", "required ending", "music choice", "continuity locks",
                ],
                "director_owns": [
                    "continuous action and performance", "necessary shot count and cut points",
                    "blocking", "camera placement and movement", "focus", "sound description",
                ],
            },
        }, ensure_ascii=False, indent=2)},
    ]
    result = compile_h3_english(final_messages, generation["mode"], requirements)
    if progress: progress("compiler", "completed", "H3 导演成稿已完成")
    if generation.get("mode") == "reference":
        if progress: progress("conformance", "running", "正在检查参考图、动作连续性与用户约束")
        result = conform_h3_draft(result, generation, requirements, session.get("user_requests", []))
        if progress: progress("conformance", "completed", "英文执行稿已通过契约检查")
    elif progress:
        progress("conformance", "skipped", "当前模式无需参考图契约检查")

    if progress: progress("translation", "running", "正在将英文执行稿翻译为中文确认稿")
    try:
        result["optimized_prompt_zh"] = translate_h3_draft(result["optimized_prompt"], generation, requirements)
    except ValueError as exc:
        result["optimized_prompt_zh"] = ""
        result["translation_warning"] = f"中文翻译服务未完成：{exc}"
    if progress: progress("translation", "completed", "中文确认稿已返回，导演管线完成")

    warnings = []
    if result.get("revision_warning"):
        warnings.append(result["revision_warning"])
    if result.get("translation_warning"):
        warnings.append(result["translation_warning"])
    final_review = {
        "mode": "external" if generation.get("review_mode") == "external" else "human",
        "summary": "导演管线已完成，请确认中英文成稿。",
        "hard_errors": [],
        "warnings": warnings,
        "compiler_corrections": [],
        "confirmed_strengths": [],
    }
    result["production_plan"] = {
        "requirements": requirements,
        "scene_design": None,
        "shot_plan": None,
        "selected_skills": selected_skill_ids,
        "skill_reasons": skill_reasons,
        "final_review": final_review,
        "approved_plan_digest": approved_digest,
        "capacity_issues": [],
    }
    result["review"] = final_review
    return result
