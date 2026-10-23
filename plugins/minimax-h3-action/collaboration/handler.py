"""Staged director collaboration for multi-segment continuation.

Requirements planning (multi-turn Q&A) -> director skill planning -> one
full-length six-section director draft -> editor splitting at shot-level
breathing points -> per-segment ref2va conversion -> chain conformance ->
Chinese confirmation. The confirmed plan travels as plugin parameters and
the compiler materializes one ComfyUI job with per-segment durations.
"""

import asyncio
import json
import time
import uuid
from backend.modules.shared.plugin_runtime import PluginError
from .analysis import parse_requirements_result
from .pipeline import production_structure_note, resolve_production_structure, run_segmented_production
from .prompts import requirements_stage_prompt

STAGE_LABELS = {
    "requirements": "需求与素材策划",
    "skill_planning": "导演技能规划",
    "full_draft": "整篇导演成稿",
    "segmentation": "镜头呼吸点拆分",
    "compiler": "逐段格式转换",
    "conformance": "链式契约检查",
    "translation": "中文确认稿翻译",
}
STAGES = [{"id": key, "label": label} for key, label in STAGE_LABELS.items()]
RETRY_FAILED_STAGE_COMMAND = "__videofree_retry_failed_stage__"


def bounded_segments(value):
    try:
        return max(1, min(5, int(value)))
    except (TypeError, ValueError):
        return 1


def bounded_durations(value, segments):
    """Per-segment durations only survive when complete and in range.

    Accepts the comma-separated wire string (the framework parameter schema has
    no array type) as well as in-process lists.
    """
    if isinstance(value, str):
        value = value.replace("，", ",").split(",")
    if not isinstance(value, list) or len(value) != segments:
        return []
    durations = []
    for item in value:
        try:
            number = float(item)
        except (TypeError, ValueError):
            return []
        if not 1 <= number <= 15:
            return []
        durations.append(number)
    return durations


def validate_plan_durations(value, segments, total_duration):
    durations = bounded_durations(value, segments)
    if not durations:
        raise ValueError("分段计划缺少有效的各段时长，请重新生成导演方案")
    if abs(sum(durations) - float(total_duration)) > 0.05:
        raise ValueError("各段时长合计必须等于整片总时长，请重新生成导演方案")
    return durations


def finalize(result):
    """Clamp the director's plan into the compiler's parameter surface."""
    payload = result.setdefault("generation_payload", {})
    parameters = payload.setdefault("parameters", {})
    segments = bounded_segments(parameters.get("segments"))
    total_duration = (payload.get("settings", {}).get("duration")
                      if isinstance(payload.get("settings"), dict) else None)
    if total_duration is None:
        total_duration = (result.get("production_plan", {}).get("production_structure", {}).get("total_duration")
                          if isinstance(result.get("production_plan"), dict) else None)
    if segments > 1 and total_duration is None:
        raise ValueError("分段方案缺少整片总时长，请重新生成导演方案")
    durations = validate_plan_durations(parameters.get("durations"), segments, total_duration) if total_duration is not None else []
    parameters.pop("prompt_1", None)
    parameters["segments"] = segments
    main = str(result.get("optimized_prompt", "")).strip()
    for index in range(2, segments + 1):
        key = f"prompt_{index}"
        if not str(parameters.get(key, "")).strip():
            parameters[key] = main
    for index in range(segments + 1, 6):
        parameters.pop(f"prompt_{index}", None)
    if durations:
        parameters["durations"] = ",".join(f"{item:g}" for item in durations)
    settings = payload.get("settings")
    if isinstance(settings, dict):
        # The user owns ratio/resolution in the submit UI; the director may
        # allocate segment durations within the user's selected total.
        payload["settings"] = {key: settings[key] for key in ("duration",) if key in settings}
    else:
        payload["settings"] = {}
    return result


async def run_requirements_stage(session, request, runtime, progress_id, hardware_snapshot=None):
    """One requirements planning turn; returns the contract or a needs_input result."""
    messages = session["requirements_messages"]
    # The requirements skill is written for single clips; bind it to the multi-segment total.
    generation = {**session["generation"], "hardware_snapshot": hardware_snapshot}
    structure = resolve_production_structure(session.get("user_requests", []), generation)
    call_messages = messages + [{"role": "user", "content": production_structure_note(structure)}]
    source_text = "\n".join(str(item) for item in session.get("user_requests", []))
    runtime.update_progress(progress_id, "requirements", "running", "正在策划需求、素材职责、声音与可行性")
    content = await asyncio.to_thread(runtime.call_model, call_messages, 6000)
    requirements = parse_requirements_result(content, session["generation"], source_text)
    if requirements["status"] == "needs_input" and not requirements["questions"] and not requirements.get("_contract_issues"):
        correction = {"role": "user", "content": (
            "You returned needs_input without any question. If all necessary choices are resolved, "
            "return status=ready with every required field complete. Otherwise ask one necessary question "
            "with at least two clickable options. Return the complete corrected JSON contract."
        )}
        content = await asyncio.to_thread(runtime.call_model,
                                          call_messages + [{"role": "assistant", "content": content}, correction], 6000)
        requirements = parse_requirements_result(content, session["generation"], source_text)
    if requirements["status"] == "needs_input" and not requirements.get("_contract_issues"):
        allowed_questions = {"background_music_choice", "reference_role", "role_mapping", "dialogue",
                             "ending", "central_action"}
        allowed_questions.update(
            item.get("id") for item in requirements.get("questions", [])
            if str(item.get("id", "")).startswith("text_normalization_")
        )
        extraneous = [item for item in requirements["questions"] if item.get("id") not in allowed_questions]
        if extraneous:
            correction = {"role": "user", "content": (
                "Do not ask the user to choose editing strategy, segment count, choreography, pacing, or other "
                "creative decisions. Decide these yourself while preserving the user's action and dialogue. Only "
                "ask about missing reference ownership, mandatory dialogue, ending, central action, or the required "
                "music decision. Return the complete corrected JSON contract."
            )}
            content = await asyncio.to_thread(runtime.call_model,
                                              call_messages + [{"role": "assistant", "content": content}, correction], 6000)
            requirements = parse_requirements_result(content, session["generation"], source_text)
    if requirements.get("_contract_issues"):
        correction = {
            "role": "user",
            "content": "Your response claimed status=ready but violated the JSON contract: "
            + "; ".join(requirements["_contract_issues"])
            + ". Return one corrected, complete JSON object only. Do not ask the user to repair your formatting.",
        }
        corrected = await asyncio.to_thread(runtime.call_model,
                                            call_messages + [{"role": "assistant", "content": content}, correction], 6000)
        messages.extend([{"role": "assistant", "content": content}, correction])
        content = corrected
        requirements = parse_requirements_result(content, session["generation"], source_text)
        if requirements.get("_contract_issues"):
            raise ValueError("需求策划阶段连续两次未返回完整结构，请重试或更换 AI 模型")
    messages.append({"role": "assistant", "content": content})
    requirements.pop("_contract_issues", None)
    return requirements


async def director(request, runtime):
    if request.duration_seconds > 75:
        raise PluginError(422, "总时长不能超过 75 秒（最多 5 段 × 15 秒）")
    progress_id = request.progress_id or f"progress-{uuid.uuid4().hex[:12]}"
    runtime.start_progress(progress_id, STAGES)
    retry_failed_stage = str(request.message or "").strip() == RETRY_FAILED_STAGE_COMMAND
    try:
        if request.session_id:
            session = runtime.session(request.session_id)
            if not session:
                raise ValueError("智能体会话已失效，请重新发送生成需求")
            if retry_failed_stage and not session.get("last_failure"):
                raise ValueError("当前会话没有失败阶段可重试，请正常发送新的需求")
            if not retry_failed_stage:
                if session.get("last_final_result"):
                    session["requirements_messages"].insert(-1, {"role": "user", "content":
                        "当前已生成的分段中英文成稿如下。后续修改必须以它为基线，只修改用户明确提出的部分：\n"
                        + json.dumps(session["last_final_result"], ensure_ascii=False)})
                session["requirements_messages"].append({"role": "user", "content": request.message})
                session.setdefault("user_requests", []).append(request.message)
                session.pop("_minimax_h3_action_checkpoint", None)
                session.pop("requirements", None)
        else:
            session = {"id": f"agent-{uuid.uuid4().hex[:12]}", "created_at": time.time(),
                       "model": request.model, "mode": request.mode,
                       "generation": runtime.staged_context(request),
                       "user_requests": [request.message]}
            session["requirements_messages"] = [
                {"role": "system", "content": requirements_stage_prompt()},
                {"role": "user", "content": runtime.initial_message(request)},
            ]
            runtime.save_session(session)

        requirements = session.get("requirements") if retry_failed_stage else None
        if isinstance(requirements, dict):
            runtime.update_progress(progress_id, "requirements", "completed", "沿用已完成的需求与素材策划")
            hardware_snapshot = None
        else:
            try:
                hardware_snapshot = await asyncio.to_thread(
                    runtime.call_system_service, "comfyui", "system_stats", {})
            except Exception:
                # Hardware information is advisory; ComfyUI/provider outages must not block collaboration.
                hardware_snapshot = None
            requirements = await run_requirements_stage(session, request, runtime, progress_id, hardware_snapshot)
        session["requirements"] = requirements
        runtime.save_session(session)
        runtime.update_progress(progress_id, "requirements", "completed", "需求、素材、声音与制作约束已整理")
        if requirements["status"] != "ready":
            runtime.finish_progress(progress_id, "awaiting_input")
            return {
                "session_id": session["id"],
                "progress_id": progress_id,
                "status": "needs_input",
                "message": requirements["message"],
                "questions": requirements["questions"],
                "reference_map": requirements["reference_map"],
                "decisions": requirements["decisions"],
                "optimized_prompt_zh": "",
                "optimized_prompt": "",
                "optimized_shots": [],
                "generation_payload": {},
                "stage": "requirements",
            }

        progress_callback = lambda stage_id, status, message="": runtime.update_progress(progress_id, stage_id, status, message)
        result = await asyncio.to_thread(run_segmented_production, session, requirements,
                                         progress_callback, runtime.call_model, hardware_snapshot)
        finalize(result)
        session["production_plan"] = result.get("production_plan")
        session["last_final_result"] = {
            "optimized_prompt_zh": result.get("optimized_prompt_zh", ""),
            "optimized_prompt": result.get("optimized_prompt", ""),
        }
        session.pop("last_failure", None)
        runtime.save_session(session)
    except ValueError as exc:
        if "session" in locals() and isinstance(session, dict):
            session["last_failure"] = str(exc)
            runtime.save_session(session)
        runtime.fail_progress(progress_id, str(exc))
        raise PluginError(502, str(exc)) from exc
    except Exception:
        if "session" in locals() and isinstance(session, dict):
            session["last_failure"] = "导演流程遇到暂时性错误，可重试失败阶段"
            runtime.save_session(session)
        runtime.fail_progress(progress_id, "导演流程遇到暂时性错误，可重试失败阶段")
        raise
    runtime.finish_progress(progress_id, "completed" if result.get("status") == "ready" else "awaiting_input")
    return {"session_id": session["id"], "progress_id": progress_id, "stage": "ready", **result}
