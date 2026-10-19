import asyncio
import json
import time
import uuid
from backend.modules.shared.plugin_runtime import AgentChatRequest, PluginError
from backend.modules.shared.plugin_runtime import parse_agent_result
from backend.modules.shared.plugin_runtime import agent_skill_prompt
from .analysis import (
    parse_requirements_result, agent_prompt_issues, normalize_reference_mode_questions,
    selected_text_fallback,
)
from .prompts import AGENT_MODEL_ALIASES
from .prompts import h3_quick_prompt, requirements_stage_prompt
from .pipeline import run_h3_production_pipeline

STAGE_LABELS = {
    "requirements": "需求与素材策划",
    "skill_planning": "技能规划",
    "compiler": "MiniMax H3 导演成稿",
    "conformance": "英文契约检查",
    "translation": "中文确认稿翻译",
    "optimize": "模型提示词优化",
    "quick_convert": "MiniMax H3 提示词转换",
}

async def compile(request, runtime):
    return await handle(request.model_copy(update={"collaboration_mode": "quick"}), runtime)

async def director(request, runtime):
    return await handle(request.model_copy(update={"collaboration_mode": "director"}), runtime)

async def handle(request: AgentChatRequest, runtime):
    if request.duration_seconds > 15:
        raise PluginError(422, "MiniMax H3 视频时长不能超过 15 秒")
    progress_id = request.progress_id or f"progress-{uuid.uuid4().hex[:12]}"
    existing = runtime.session(request.session_id)
    normalized_model = AGENT_MODEL_ALIASES.get(request.model, request.model)
    pipeline = (
        str(existing.get("pipeline")) if existing
        else "h3-quick" if normalized_model == "minimax-h3" and request.collaboration_mode == "quick"
        else "h3-staged" if normalized_model == "minimax-h3"
        else "single"
    )
    stage_ids = (
        ["requirements", "skill_planning", "compiler", "conformance", "translation"]
        if pipeline == "h3-staged" else ["quick_convert"] if pipeline == "h3-quick" else ["optimize"]
    )
    runtime.start_progress(progress_id, [{"id": stage_id, "label": STAGE_LABELS[stage_id]} for stage_id in stage_ids])
    try:
        if request.session_id:
            session = runtime.session(request.session_id)
            if not session:
                raise ValueError("智能体会话已失效，请重新发送生成需求")
            if selected_text_fallback(request.message, session.get("generation", {})):
                session["generation"]["mode"] = "text_to_video"
                session["mode"] = "text_to_video"
                session["submission_capability_id"] = "video.text_to_video"
                if session.get("pipeline") == "h3-quick":
                    session["messages"][0]["content"] = h3_quick_prompt("text_to_video")
                session["requirements_messages" if session.get("pipeline") == "h3-staged" else "messages"].append({
                    "role": "user",
                    "content": "用户已明确选择切换到纯文字生成 T2VA。不要再询问参考素材或模式；按 T2VA 继续，并在确认后提交到 video.text_to_video。",
                })
            message_key = "requirements_messages" if session.get("pipeline") == "h3-staged" else "messages"
            session[message_key].append({"role": "user", "content": request.message})
            if session.get("pipeline") == "h3-staged" and session.get("last_final_result"):
                session[message_key].insert(-1, {
                    "role": "user",
                    "content": "当前已生成的中英文成稿如下。后续修改必须以它为基线，只修改用户明确提出的部分：\n"
                    + json.dumps(session["last_final_result"], ensure_ascii=False),
                })
            session.setdefault("user_requests", []).append(request.message)
        else:
            session_id = f"agent-{uuid.uuid4().hex[:12]}"
            session = {
                "id": session_id,
                "created_at": time.time(),
                "model": normalized_model,
                "mode": request.mode,
                "pipeline": pipeline,
                "generation": runtime.staged_context(request),
                "user_requests": [request.message],
            }
            if session["pipeline"] == "h3-staged":
                session["requirements_messages"] = [
                    {"role": "system", "content": requirements_stage_prompt()},
                    {"role": "user", "content": runtime.initial_message(request)},
                ]
            else:
                session["messages"] = [
                    {"role": "system", "content": (
                        h3_quick_prompt(request.mode)
                        if session["pipeline"] == "h3-quick"
                        else agent_skill_prompt(request.model, request.mode)
                    )},
                    {"role": "user", "content": runtime.initial_message(request)},
                ]
            runtime.save_session(session)

        if session.get("pipeline") == "h3-staged":
            messages = session["requirements_messages"]
            source_text = "\n".join(str(item) for item in session.get("user_requests", []))
            runtime.update_progress(progress_id, "requirements", "running", "正在策划需求、素材职责、声音与可行性")
            content = await asyncio.to_thread(runtime.call_model, messages, 6000)
            requirements = parse_requirements_result(content, session["generation"], source_text)
            requirements = normalize_reference_mode_questions(requirements, session.get("mode", request.mode), session.get("generation"))
            if requirements["status"] == "needs_input" and not requirements["questions"] and not requirements.get("_contract_issues"):
                correction = {"role": "user", "content": (
                    "You returned needs_input without any question. If all necessary choices are resolved, "
                    "return status=ready with every required field complete. Otherwise ask one necessary question "
                    "with at least two clickable options. Return the complete corrected JSON contract."
                )}
                content = await asyncio.to_thread(runtime.call_model, messages + [{"role": "assistant", "content": content}, correction], 6000)
                requirements = parse_requirements_result(content, session["generation"], source_text)
            requirements = normalize_reference_mode_questions(requirements, session.get("mode", request.mode), session.get("generation"))
            if requirements["status"] == "needs_input" and not requirements.get("_contract_issues"):
                allowed_questions = {"background_music_choice", "reference_role", "role_mapping", "dialogue", "ending", "central_action", "missing_reference_action"}
                allowed_questions.update(
                    item.get("id") for item in requirements.get("questions", [])
                    if str(item.get("id", "")).startswith("text_normalization_")
                )
                extraneous = [item for item in requirements["questions"] if item.get("id") not in allowed_questions]
                if extraneous:
                    correction = {"role": "user", "content": (
                        "Do not ask the user to choose editing strategy, shot count, choreography, pacing, or other creative decisions. "
                        "Decide these yourself while preserving the user's action and dialogue. Only ask about missing "
                        "reference ownership, mandatory dialogue, ending, central action, or the required music decision. "
                        "Return the complete corrected JSON contract."
                    )}
                    content = await asyncio.to_thread(runtime.call_model, messages + [{"role": "assistant", "content": content}, correction], 6000)
                    requirements = parse_requirements_result(content, session["generation"], source_text)
                    requirements = normalize_reference_mode_questions(requirements, session.get("mode", request.mode), session.get("generation"))
            if requirements.get("_contract_issues"):
                correction = {
                    "role": "user",
                    "content": "Your response claimed status=ready but violated the JSON contract: "
                    + "; ".join(requirements["_contract_issues"])
                    + ". Return one corrected, complete JSON object only. Do not ask the user to repair your formatting.",
                }
                corrected = await asyncio.to_thread(
                    runtime.call_model,
                    messages + [{"role": "assistant", "content": content}, correction],
                    6000,
                )
                messages.extend([{"role": "assistant", "content": content}, correction])
                content = corrected
                requirements = parse_requirements_result(content, session["generation"], source_text)
                if requirements.get("_contract_issues"):
                    raise ValueError("需求策划阶段连续两次未返回完整结构，请重试或更换 AI 模型")
            messages.append({"role": "assistant", "content": content})
            requirements.pop("_contract_issues", None)
            session["requirements"] = requirements
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
            result = await asyncio.to_thread(run_h3_production_pipeline, session, requirements, progress_callback, runtime.call_model)
            if session.get("submission_capability_id"):
                result["generation_payload"] = {**result.get("generation_payload", {}),
                                                 "capability_id": session["submission_capability_id"]}
            session["production_plan"] = result.get("production_plan")
            session["last_final_result"] = {
                "optimized_prompt_zh": result.get("optimized_prompt_zh", ""),
                "optimized_prompt": result.get("optimized_prompt", ""),
            }
            runtime.finish_progress(progress_id, "completed" if result.get("status") == "ready" else "awaiting_input")
            return {"session_id": session["id"], "progress_id": progress_id, "stage": "ready", **result}

        stage_id = "quick_convert" if session.get("pipeline") == "h3-quick" else "optimize"
        stage_message = "正在忠实转换为 MiniMax H3 中英文执行稿" if stage_id == "quick_convert" else "正在按当前模型与模式优化提示词"
        runtime.update_progress(progress_id, stage_id, "running", stage_message)
        max_tokens = 7000 if session.get("pipeline") == "h3-quick" else 2500
        content = await asyncio.to_thread(runtime.call_model, session["messages"], max_tokens)
        result = parse_agent_result(content)
        result = normalize_reference_mode_questions(result, session.get("mode", request.mode), session.get("generation"))
        result = await asyncio.to_thread(
            runtime.repair_result,
            session["messages"],
            result,
            session.get("model", request.model),
            session.get("mode", request.mode),
            agent_prompt_issues,
        )
        if session.get("submission_capability_id"):
            result["generation_payload"] = {**result.get("generation_payload", {}),
                                             "capability_id": session["submission_capability_id"]}
        session["messages"].append({"role": "assistant", "content": content})
        runtime.update_progress(progress_id, stage_id, "completed", "H3 提示词转换已完成" if stage_id == "quick_convert" else "提示词方案已完成")
        runtime.finish_progress(progress_id, "completed" if result.get("status") == "ready" else "awaiting_input")
        return {"session_id": session["id"], "progress_id": progress_id, **result}
    except ValueError as exc:
        runtime.fail_progress(progress_id, str(exc))
        raise PluginError(502, str(exc)) from exc


