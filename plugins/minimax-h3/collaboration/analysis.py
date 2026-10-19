"""H3-specific deterministic planning and prompt validation."""
import hashlib
import json
import re
from typing import Any
from backend.modules.shared.plugin_runtime import parse_agent_json, normalized_agent_questions
from .prompts import AGENT_MODEL_ALIASES


def normalize_reference_mode_questions(result: dict[str, Any], mode: str, generation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Keep clarification actions executable within the selected H3 mode.

    A text-only fallback is an explicit mode choice, not a submission in Ref2VA.
    """
    if str(mode).strip().lower() != "reference":
        return result
    references = (generation or {}).get("ordered_references", [])
    if references:
        return result
    questions = [item for item in result.get("questions", []) if isinstance(item, dict)]
    if not any(item.get("id") == "missing_reference_action" for item in questions):
        result["questions"] = [{
            "id": "missing_reference_action",
            "text": "当前选择的是参考生成，但没有附带参考素材。请选择一次后继续：",
            "options": ["切换为纯文字生成（T2VA）", "补充参考素材后继续"],
        }, *questions]
    else:
        result["questions"] = questions
    result["status"] = "needs_input"
    return result


def selected_text_fallback(message: str, generation: dict[str, Any]) -> bool:
    """Recognize the explicit T2VA choice for an empty Ref2VA session."""
    if generation.get("mode") != "reference" or generation.get("ordered_references"):
        return False
    text = str(message).strip().lower()
    return any(term in text for term in ("t2va", "纯文字生成", "纯文字模式", "纯文本生成", "切换到纯文字"))


def parse_requirements_result(
    content: str, generation: dict[str, Any] | None = None, source_text: str = "",
) -> dict[str, Any]:
    result = parse_agent_json(content)
    if not result:
        return {
            "status": "needs_input", "message": content, "questions": [],
            "brief": {}, "script_zh": "", "event_chain": [], "scoped_constraints": [], "action_level": "simple",
            "content_type": "general", "shot_type": "general", "camera_structure": "adaptive", "capabilities": [],
            "action_domain": "none",
            "performance_level": "none", "dialogue_required": False,
            "closeup_emotion_required": False,
            "kinetic_plan": {"speed_priority": "normal", "playback_style": "natural", "allow_slow_motion": False,
                             "quantitative_anchors": [], "proposed_speed_anchors": [], "camera_separation": "normal"},
            "audio_plan": {}, "motion_contract": {
                "action_continuity": "adaptive", "tempo": "normal", "impact": "medium",
                "pause_policy": "user_defined", "timing_policy": "natural_transition",
                "basis": "未返回结构化需求，等待补充",
            }, "text_normalizations": [], "continuity_locks": [], "visual_facts": [], "feasibility": {},
            "reference_map": [], "reference_facts": [], "decisions": [], "_contract_issues": [],
        }
    contract_issues: list[str] = []
    claimed_ready = result.get("status") == "ready"
    content_type = str(result.get("content_type", "")).strip().lower()
    allowed_content_types = {"narrative_drama", "dialogue_performance", "action", "explainer", "commerce", "product_showcase", "general"}
    if content_type not in allowed_content_types:
        if claimed_ready: contract_issues.append("content_type must be explicit and valid")
        content_type = "general"
    shot_type = str(result.get("shot_type", "")).strip().lower()
    allowed_shot_types = {
        "dialogue_performance", "emotional_closeup", "combat_exchange", "ultimate_move",
        "chase_motion", "product_action", "explainer_action", "establishing", "transition", "general",
    }
    if shot_type not in allowed_shot_types:
        if claimed_ready: contract_issues.append("shot_type must be explicit and valid")
        shot_type = "general"
    camera_structure = str(result.get("camera_structure", "")).strip().lower()
    if camera_structure not in {"adaptive", "continuous", "shot_reverse_shot", "limited_sequence"}:
        if claimed_ready: contract_issues.append("camera_structure must be explicit and valid")
        camera_structure = "adaptive"
    brief = result.get("brief") if isinstance(result.get("brief"), dict) else {}
    script = str(result.get("script_zh", "")).strip()
    if claimed_ready and not script:
        contract_issues.append("script_zh is required")
    event_chain = result.get("event_chain") if isinstance(result.get("event_chain"), list) else []
    event_chain = [
        {
            "id": str(item.get("id", "")).strip(),
            "event": str(item.get("event", "")).strip(),
            "result": str(item.get("result", "")).strip(),
        }
        for item in event_chain if isinstance(item, dict)
    ]
    if claimed_ready and (
        not event_chain or any(not item["id"] or not item["event"] or not item["result"] for item in event_chain)
        or len({item["id"] for item in event_chain}) != len(event_chain)
    ):
        contract_issues.append("event_chain must contain ordered unique events with id, event and result")
    scoped_constraints = result.get("scoped_constraints") if isinstance(result.get("scoped_constraints"), list) else []
    scoped_constraints = [
        {
            "rule": str(item.get("rule", "")).strip(),
            "scope": str(item.get("scope", "")).strip(),
            "source": str(item.get("source", "")).strip().lower(),
            "evidence": str(item.get("evidence", "")).strip() or str(item.get("rule", "")).strip(),
        }
        for item in scoped_constraints if isinstance(item, dict)
    ]
    event_ids = {item["id"] for item in event_chain if item["id"]}
    expected_reference_labels = {
        str(item.get("label", "")).strip()
        for item in (generation or {}).get("ordered_references", []) if isinstance(item, dict)
    }
    if claimed_ready and any(
        not item["rule"]
        or item["source"] not in {"user", "reference", "inferred"}
        or (item["scope"] != "whole_clip" and item["scope"] not in event_ids
            and not re.fullmatch(r"dialogue:\d+", item["scope"]))
        for item in scoped_constraints
    ):
        contract_issues.append("scoped_constraints must include valid rule, scope and source")
    action_level = str(result.get("action_level", "")).strip().lower()
    if action_level not in {"simple", "coordinated", "combat"}:
        if claimed_ready: contract_issues.append("action_level must be explicit and valid")
        action_level = "simple"
    action_domain = str(result.get("action_domain", "")).strip()
    if claimed_ready and not action_domain:
        contract_issues.append("action_domain is required")
    performance_level = str(result.get("performance_level", "")).strip().lower()
    if performance_level not in {"none", "simple", "dramatic"}:
        if claimed_ready: contract_issues.append("performance_level must be explicit and valid")
        performance_level = "none"
    allowed_capabilities = {
        "combat_continuity", "ultimate_action", "dialogue_performance", "facial_performance",
        "chase_motion", "explainer", "commerce", "product_showcase",
    }
    supplied_capabilities = result.get("capabilities", [])
    capabilities = [str(item).strip().lower() for item in supplied_capabilities
                    if str(item).strip().lower() in allowed_capabilities] if isinstance(supplied_capabilities, list) else []
    inferred_capabilities = []
    if action_level == "combat" or action_domain == "combat" or shot_type == "combat_exchange":
        inferred_capabilities.append("combat_continuity")
    if shot_type == "ultimate_move": inferred_capabilities.append("ultimate_action")
    if bool(result.get("dialogue_required")) or content_type == "dialogue_performance": inferred_capabilities.append("dialogue_performance")
    if bool(result.get("closeup_emotion_required")) or shot_type == "emotional_closeup": inferred_capabilities.append("facial_performance")
    if shot_type == "chase_motion": inferred_capabilities.append("chase_motion")
    if content_type in {"explainer", "commerce", "product_showcase"}: inferred_capabilities.append(content_type)
    capabilities = list(dict.fromkeys([*capabilities, *inferred_capabilities]))
    for key in ("dialogue_required", "closeup_emotion_required", "explicit_cut_requested"):
        if claimed_ready and not isinstance(result.get(key), bool):
            contract_issues.append(f"{key} must be a boolean")
    kinetic_plan = dict(result.get("kinetic_plan")) if isinstance(result.get("kinetic_plan"), dict) else {}
    speed_priority = str(kinetic_plan.get("speed_priority", "")).strip().lower()
    if speed_priority not in {"normal", "high", "extreme"}:
        if claimed_ready: contract_issues.append("kinetic_plan.speed_priority must be explicit and valid")
        speed_priority = "normal"
    playback_style = str(kinetic_plan.get("playback_style", "natural")).strip().lower()
    if playback_style not in {"natural", "real_time", "slow_motion", "speed_ramp"}:
        playback_style = "natural"
    allow_slow_motion = kinetic_plan.get("allow_slow_motion") is True
    if playback_style in {"slow_motion", "speed_ramp"} and not allow_slow_motion:
        playback_style = "natural"
    if claimed_ready and not isinstance(kinetic_plan.get("quantitative_anchors"), list):
        contract_issues.append("kinetic_plan.quantitative_anchors must be a list")
    if claimed_ready and not str(kinetic_plan.get("camera_separation", "")).strip():
        contract_issues.append("kinetic_plan.camera_separation is required")
    kinetic_plan["speed_priority"] = speed_priority
    kinetic_plan["playback_style"] = playback_style
    kinetic_plan["allow_slow_motion"] = allow_slow_motion
    kinetic_plan["quantitative_anchors"] = [
        str(item).strip() for item in kinetic_plan.get("quantitative_anchors", []) if str(item).strip()
    ] if isinstance(kinetic_plan.get("quantitative_anchors"), list) else []
    proposed = kinetic_plan.get("proposed_speed_anchors", [])
    kinetic_plan["proposed_speed_anchors"] = list(dict.fromkeys(
        str(item).strip() for item in proposed if isinstance(item, str) and item.strip()
    ))[:2] if isinstance(proposed, list) and speed_priority in {"high", "extreme"} else []
    motion_contract = dict(result.get("motion_contract")) if isinstance(result.get("motion_contract"), dict) else {}
    motion_text = " ".join((source_text, str(result.get("script_zh", "")), str(result.get("message", "")))).lower()
    explicit_slow = bool(re.search(r"慢动作|慢慢|缓慢|放慢|slow[- ]motion|slowly|slow pace|deliberate", motion_text))
    explicit_pause = bool(re.search(r"停顿|暂停|僵持|对峙|停下来|pause|standoff|hold position", motion_text))
    physical_exchange = action_level == "combat" or action_domain == "combat" or shot_type in {"combat_exchange", "chase_motion", "product_action"}
    continuity = str(motion_contract.get("action_continuity", "")).strip().lower()
    if continuity not in {"continuous", "segmented", "adaptive"}:
        continuity = "continuous" if physical_exchange and not explicit_pause else "adaptive"
    if physical_exchange and not explicit_pause and continuity == "segmented":
        continuity = "adaptive"
    tempo = str(motion_contract.get("tempo", "")).strip().lower()
    if tempo not in {"slow", "normal", "fast", "extreme"}:
        tempo = "slow" if explicit_slow else "fast" if physical_exchange and speed_priority in {"high", "extreme"} else "normal"
    if explicit_slow:
        tempo = "slow"
    impact = str(motion_contract.get("impact", "")).strip().lower()
    if impact not in {"low", "medium", "high"}:
        impact = "high" if action_level == "combat" else "medium"
    pause_policy = str(motion_contract.get("pause_policy", "")).strip().lower()
    if pause_policy not in {"forbidden", "allowed", "user_defined"}:
        pause_policy = "allowed" if explicit_pause else "forbidden" if physical_exchange else "user_defined"
    if explicit_pause:
        pause_policy = "allowed"
    timing_policy = str(motion_contract.get("timing_policy", "")).strip().lower()
    if timing_policy not in {"natural_transition", "explicit_cut_only"}:
        timing_policy = "natural_transition"
    motion_contract = {
        "action_continuity": continuity,
        "tempo": tempo,
        "impact": impact,
        "pause_policy": pause_policy,
        "timing_policy": timing_policy,
        "basis": str(motion_contract.get("basis", "")).strip() or (
            "根据连续身体动作与战斗类型推断；用户明确的慢动作或停顿要求优先"
            if physical_exchange else "根据用户动作与叙事意图保留自适应节奏"
        ),
    }
    martial_text = " ".join((source_text, str(result.get("script_zh", "")), str(result.get("message", "")))).lower()
    martial_requested = bool(re.search(r"中国武术|中国功夫|功夫|武术|武侠|散打|咏春|太极|八极|wushu|kung.?fu|martial arts", martial_text))
    weapon_matches = re.findall(r"刀|剑|枪|棍|鞭|匕首|暗器|长矛|sword|saber|staff|spear|whip|dagger", martial_text)
    weapon_type = next(iter(dict.fromkeys(weapon_matches)), "none")
    weapon_mode = "single_weapon" if weapon_type != "none" else "unarmed"
    if re.search(r"双刀|双剑|双棍|两把|双持|dual", martial_text):
        weapon_mode = "dual_weapon"
    if martial_requested and re.search(r"追逐|追赶|逃跑|屋顶|踏墙|轻功|chase|pursuit", martial_text) and weapon_type == "none":
        weapon_mode = "lightness_chase"
    martial_arts_plan = dict(result.get("martial_arts_plan")) if isinstance(result.get("martial_arts_plan"), dict) else {}
    if martial_requested or martial_arts_plan.get("required") is True:
        martial_context = str(martial_arts_plan.get("context") or ("chase" if re.search(r"追逐|追赶|逃跑|chase|pursuit", martial_text) else "duel")).strip()
        chase_weapon = martial_context == "chase" and weapon_mode in {"single_weapon", "dual_weapon", "mixed"}
        martial_arts_plan = {
            "required": True,
            "style": str(martial_arts_plan.get("style") or "general_chinese").strip(),
            "weapon_mode": str(martial_arts_plan.get("weapon_mode") or weapon_mode).strip(),
            "weapon_type": str(martial_arts_plan.get("weapon_type") or weapon_type).strip(),
            "context": martial_context,
            "weapon_contact_policy": "transient" if chase_weapon else str(martial_arts_plan.get("weapon_contact_policy") or ("bind_allowed" if weapon_mode != "unarmed" else "none")).strip(),
            "post_contact_motion": "resume_pursuit" if chase_weapon else str(martial_arts_plan.get("post_contact_motion") or ("continue_exchange" if weapon_mode != "unarmed" else "user_defined")).strip(),
            "allow_weapon_bind": False if chase_weapon else bool(martial_arts_plan.get("allow_weapon_bind", False)),
            "movement_priorities": martial_arts_plan.get("movement_priorities") if isinstance(martial_arts_plan.get("movement_priorities"), list) else ["footwork", "whole_body_power", "redirection", "contact_points"],
        }
    else:
        martial_arts_plan = {"required": False, "style": "none", "weapon_mode": "unarmed", "weapon_type": "none", "context": "none", "weapon_contact_policy": "none", "post_contact_motion": "user_defined", "allow_weapon_bind": False, "movement_priorities": []}
    text_normalizations = result.get("text_normalizations") if isinstance(result.get("text_normalizations"), list) else []
    text_normalizations = [
        {
            "original": str(item.get("original", "")).strip(),
            "corrected": str(item.get("corrected", "")).strip(),
            "scope": str(item.get("scope", "script")).strip() or "script",
            "confidence": str(item.get("confidence", "high")).strip().lower(),
            "action": str(item.get("action", "auto_fix")).strip().lower(),
            "reason": str(item.get("reason", "")).strip(),
        }
        for item in text_normalizations
        if isinstance(item, dict) and str(item.get("original", "")).strip()
    ]
    text_normalizations = [item for item in text_normalizations if item["action"] in {"auto_fix", "ask"}]
    normalization_questions = []
    for item in text_normalizations:
        if item["action"] == "ask":
            normalization_questions.append({
                "id": f"text_normalization_{len(normalization_questions) + 1}",
                "text": f"输入中的“{item['original']}”是否应改为“{item['corrected']}”？",
                "options": [f"采用“{item['corrected']}”", f"保留“{item['original']}”"],
            })
    audio_plan = dict(result.get("audio_plan")) if isinstance(result.get("audio_plan"), dict) else {}
    dialogue_plan = dict(audio_plan.get("dialogue")) if isinstance(audio_plan.get("dialogue"), dict) else {}
    lines = dialogue_plan.get("lines")
    if isinstance(lines, list):
        dialogue_plan["lines"] = [
            {"speaker": str(item.get("speaker", "")).strip(), "text": str(item.get("text", "")).strip()}
            for item in lines if isinstance(item, dict) and str(item.get("text", "")).strip()
        ]
    if dialogue_plan:
        audio_plan["dialogue"] = dialogue_plan
    audio_contract = {
        "dialogue": {"required", "content", "speaker_strategy"},
        "ambience": {"required", "description"},
        "sound_effects": {"required", "description"},
        "background_music": {"choice", "decision", "dramatic_function", "mood", "instrumentation", "tempo_rhythm", "intensity_curve", "timing", "source", "non_diegetic"},
    }
    for key, required_keys in audio_contract.items():
        value = audio_plan.get(key)
        if claimed_ready and (not isinstance(value, dict) or not required_keys.issubset(value)):
            contract_issues.append(f"audio_plan.{key} must be an object")
    background_music = dict(audio_plan.get("background_music")) if isinstance(audio_plan.get("background_music"), dict) else {}
    music_choice = str(background_music.get("choice", "")).strip().lower()
    if music_choice not in {"none", "ai_match_script", "user_specified"}:
        music_choice = "none"
        background_music["choice"] = music_choice
        background_music.setdefault("source", "default")
    music_resolved = music_choice in {"none", "ai_match_script", "user_specified"}
    if claimed_ready and not music_resolved:
        contract_issues.append("audio_plan.background_music.choice must be explicit and valid")
    if music_choice == "none":
        background_music.update({"decision": "none", "source": "none"})
    elif music_choice in {"ai_match_script", "user_specified"}:
        background_music["decision"] = "required"
    if background_music:
        audio_plan["background_music"] = background_music
    feasibility = result.get("feasibility") if isinstance(result.get("feasibility"), dict) else {}
    if claimed_ready and (
        feasibility.get("level") not in {"straightforward", "challenging"}
        or not isinstance(feasibility.get("simplifications"), list)
        or not isinstance(feasibility.get("risks"), list)
    ):
        contract_issues.append("feasibility must include level, simplifications and risks")
    required_brief = {"intent", "attention_priority", "emotional_arc", "duration_seconds", "style", "required_ending", "must_preserve"}
    if claimed_ready and (not required_brief.issubset(brief) or not isinstance(brief.get("must_preserve"), list)):
        contract_issues.append("brief is incomplete")
    if claimed_ready and not isinstance(result.get("continuity_locks"), list):
        contract_issues.append("continuity_locks must be a list")
    continuity_locks = [str(item).strip() for item in result.get("continuity_locks", []) if str(item).strip()] if isinstance(result.get("continuity_locks"), list) else []
    visual_facts = [str(item).strip() for item in result.get("visual_facts", []) if str(item).strip()] if isinstance(result.get("visual_facts"), list) else []
    reference_map = result.get("reference_map") if isinstance(result.get("reference_map"), list) else []
    if claimed_ready and not isinstance(result.get("reference_map"), list):
        contract_issues.append("reference_map must be a list")
    expected_labels = [str(item.get("label", "")).strip() for item in (generation or {}).get("ordered_references", []) if isinstance(item, dict)]
    mapped_labels = [str(item.get("label", "")).strip() for item in reference_map if isinstance(item, dict)]
    if claimed_ready and any(
        not isinstance(item, dict)
        or not str(item.get("label", "")).strip()
        or not str(item.get("role", "")).strip()
        or item.get("confidence") not in {"high", "medium", "low"}
        for item in reference_map
    ):
        contract_issues.append("reference_map entries must include label, role and confidence")
    for label in expected_labels:
        if mapped_labels.count(label) != 1:
            contract_issues.append(f"reference_map must contain {label} exactly once")
    reference_facts = result.get("reference_facts") if isinstance(result.get("reference_facts"), list) else []
    reference_facts = [
        {
            "label": str(item.get("label", "")).strip(),
            "preserve": [str(fact).strip() for fact in item.get("preserve", []) if str(fact).strip()]
            if isinstance(item.get("preserve"), list) else [],
            "unknown": [str(fact).strip() for fact in item.get("unknown", []) if str(fact).strip()]
            if isinstance(item.get("unknown"), list) else [],
        }
        for item in reference_facts if isinstance(item, dict)
    ]
    fact_labels = [item["label"] for item in reference_facts]
    if claimed_ready and any(fact_labels.count(label) != 1 for label in expected_labels):
        contract_issues.append("reference_facts must contain every supplied reference exactly once")
    ready = claimed_ready and bool(brief) and bool(script) and music_resolved and not contract_issues and not normalization_questions
    questions = [] if ready else normalized_agent_questions(result)
    questions.extend(normalization_questions)
    return {
        "status": "ready" if ready else "needs_input",
        "message": str(result.get("message", "")).strip() or ("方案已整理完成。" if ready else "我还需要一点信息才能继续。"),
        "questions": questions,
        "brief": brief,
        "script_zh": script,
        "event_chain": event_chain,
        "scoped_constraints": scoped_constraints,
        "content_type": content_type,
        "shot_type": shot_type,
        "camera_structure": camera_structure,
        "capabilities": capabilities,
        "action_level": action_level,
        "action_domain": action_domain or "none",
        "performance_level": performance_level,
        "dialogue_required": bool(result.get("dialogue_required")),
        "closeup_emotion_required": bool(result.get("closeup_emotion_required")),
        "explicit_cut_requested": bool(result.get("explicit_cut_requested")),
        "kinetic_plan": kinetic_plan,
        "motion_contract": motion_contract,
        "martial_arts_plan": martial_arts_plan,
        "text_normalizations": text_normalizations,
        "audio_plan": audio_plan,
        "continuity_locks": continuity_locks,
        "visual_facts": visual_facts,
        "feasibility": feasibility,
        "reference_map": reference_map,
        "reference_facts": reference_facts,
        "appearance_authority": "reference_only" if (generation or {}).get("ordered_references") else "text_only",
        "decisions": result.get("decisions") if isinstance(result.get("decisions"), list) else [],
        "_contract_issues": contract_issues,
    }

def agent_prompt_issues(prompt: str, model: str, mode: str) -> list[str]:
    model = AGENT_MODEL_ALIASES.get(model, model)
    if model != "minimax-h3":
        return ["empty optimized_prompt"] if not prompt.strip() else []
    required = {
        "text_to_video": ["integrated_multimodal_description:", "overall_soundscape:", "non_diegetic_music:"],
        "image_to_video": ["at 0.00 seconds", "integrated_multimodal_description:", "overall_soundscape:", "non_diegetic_music:"],
        "first_last_frame": ["at 0.00 seconds", "at the final frame", "integrated_multimodal_description:", "overall_soundscape:", "non_diegetic_music:"],
        "last_frame": ["at the final frame", "integrated_multimodal_description:", "overall_soundscape:", "non_diegetic_music:"],
        "reference": ["subject_definitions:", "summary:", "retention_analysis:", "detailed_description:", "overall_soundscape:", "non_diegetic_music:"],
    }.get(mode, [])
    issues = [f"missing `{item}`" for item in required if item not in prompt]
    if "..." in prompt or "…" in prompt: issues.append("contains an unfinished ellipsis")
    if "placeholder" in prompt.lower(): issues.append("contains a placeholder")
    if mode == "reference":
        positions = [prompt.find(item) for item in required]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            issues.append("sections are out of order")
    return issues

def missing_speed_numbers(prompt: str, requirements: dict[str, Any]) -> list[str]:
    plan = requirements.get("kinetic_plan", {})
    return list(dict.fromkeys(
        number for key in ("quantitative_anchors", "proposed_speed_anchors")
        for anchor in plan.get(key, [])
        for number in re.findall(r"\d+(?:\.\d+)?", str(anchor))
        if not re.search(r"(?<![\d.])" + re.escape(number) + r"(?![\d.])", prompt)
    ))

def unapproved_action_durations(prompt: str, requirements: dict[str, Any]) -> list[str]:
    body = prompt.split("detailed_description:", 1)[-1] if "detailed_description:" in prompt else prompt.split("integrated_multimodal_description:", 1)[-1]
    body = body.split("overall_soundscape:", 1)[0]
    body = re.sub(r"\[Shot\s+\d+\]\s*At\s+\d{2}:\d{2}(?:\.\d{1,3})?", "", body, flags=re.IGNORECASE)
    approved = requirements.get("kinetic_plan", {})
    approved_text = " ".join(str(anchor) for key in ("quantitative_anchors", "proposed_speed_anchors")
                             for anchor in approved.get(key, [])) + " " + str(requirements.get("script_zh", ""))
    matches = re.findall(r"\b(?:within|in|over|for)\s+(?:(?:about|roughly|approximately|around|under|nearly)\s+)?"
                         r"(\d+(?:\.\d+)?)\s*(?:seconds?|secs?)\b", body, flags=re.IGNORECASE)
    return list(dict.fromkeys(number for number in matches
                              if not re.search(r"(?<![\d.])" + re.escape(number) + r"\s*(?:秒|seconds?|secs?)", approved_text, flags=re.IGNORECASE)))

def approved_dialogue_lines(requirements: dict[str, Any]) -> list[str]:
    dialogue = requirements.get("audio_plan", {}).get("dialogue", {})
    if not isinstance(dialogue, dict) or dialogue.get("required") is False:
        return []
    lines = dialogue.get("lines")
    if isinstance(lines, list) and lines:
        return list(dict.fromkeys(str(item.get("text", "")).strip() for item in lines
                                  if isinstance(item, dict) and str(item.get("text", "")).strip()))
    content = str(dialogue.get("content", "")).strip()
    quoted = re.findall(r"[“‘\"]([^”’\"]+)[”’\"]", content)
    if quoted:
        return list(dict.fromkeys(quoted))
    attributed = re.findall(r"(?:^|[；;\n])\s*[^：:\n；;]{1,24}[：:]\s*([^；;\n]+)", content)
    return list(dict.fromkeys(item.strip() for item in attributed)) if attributed else [content] if content else []

def parse_structured_stage(content: str, baseline: dict[str, Any] | None = None) -> dict[str, Any] | None:
    result = parse_agent_json(content)
    if not result:
        return None
    for key in ("revised_plan", "director_plan", "plan"):
        if isinstance(result.get(key), dict):
            result = result[key]
            break
    return {**(baseline or {}), **result}

def needs_shot_direction(requirements: dict[str, Any], scene_design: dict[str, Any] | None) -> bool:
    if not scene_design:
        return False
    return (
        str(requirements.get("camera_structure", "continuous")) != "continuous"
        or str(requirements.get("action_level", "simple")) in {"coordinated", "combat"}
        or str(requirements.get("shot_type", "general")) in {
            "combat_exchange", "ultimate_move", "chase_motion", "product_action",
        }
        or str(requirements.get("content_type", "general")) == "product_showcase"
        or bool(requirements.get("explicit_cut_requested"))
    )

def final_prompt_consistency_issues(result: dict[str, Any], requirements: dict[str, Any]) -> list[str]:
    english = str(result.get("optimized_prompt", ""))
    chinese = str(result.get("optimized_prompt_zh", ""))
    mode = str(requirements.get("mode", ""))
    issues = agent_prompt_issues(english, "minimax-h3", mode)
    duration = float(requirements.get("duration_seconds") or requirements.get("brief", {}).get("duration_seconds") or 0)
    description = english.split("integrated_multimodal_description:", 1)[-1]
    shot_count = len(set(re.findall(r"\[Shot\s+(\d+)\]", description, flags=re.IGNORECASE)))
    approved_shots = requirements.get("shot_plan", {}).get("shots", []) if isinstance(requirements.get("shot_plan"), dict) else []
    if approved_shots and shot_count != len(approved_shots):
        issues.append(f"镜头导演批准了 {len(approved_shots)} 个镜头，英文成稿实际包含 {shot_count} 个")
    camera_structure = str(requirements.get("camera_structure", "continuous"))
    if camera_structure == "continuous" and shot_count > 1:
        issues.append(f"continuous 结构必须保持单镜头，成稿包含 {shot_count} 个")
    elif camera_structure in {"shot_reverse_shot", "limited_sequence"} and 0 < shot_count < 2:
        issues.append(f"{camera_structure} 结构至少需要 2 个镜头，成稿只包含 {shot_count} 个")
    timestamps = [
        int(minutes) * 60 + float(seconds)
        for minutes, seconds in re.findall(r"At\s+(\d{2}):(\d{2}(?:\.\d{1,3})?)", english, flags=re.IGNORECASE)
    ]
    if timestamps != sorted(set(timestamps)):
        issues.append("镜头时间戳没有严格递增")
    if duration and any(value <= 0 or value >= duration for value in timestamps):
        issues.append("镜头时间戳超出视频时长")
    martial_plan = requirements.get("martial_arts_plan", {})
    if isinstance(martial_plan, dict) and martial_plan.get("context") == "chase" and martial_plan.get("weapon_contact_policy") == "transient":
        if re.search(r"\b(?:held|holds|braced|brace|locked|lock|bind|binding)\b|持续架|僵持|长时间接触|停在接触点", english, flags=re.IGNORECASE):
            issues.append("追逐中的兵器接触被写成持续架住或僵持，应改为瞬时碰撞后立即分离并继续追逐")
        if not re.search(r"resume|continue|pursu|run|turn|pivot|separat|deflect|redirect|立即|继续", english, flags=re.IGNORECASE):
            issues.append("追逐中的兵器接触后缺少立即恢复运动的动作")
    music = requirements.get("audio_plan", {}).get("background_music", {})
    if music.get("choice") == "none" and not re.search(r"non_diegetic_music\s*:\s*N/A\b", english, flags=re.IGNORECASE):
        issues.append("用户选择不配背景音乐，但英文成稿没有明确写 non_diegetic_music: N/A")
    for line in approved_dialogue_lines(requirements):
        if line not in chinese:
            issues.append(f"用户确认的对白 {line} 未保留在中文成稿中")
        if line not in english:
            issues.append(f"用户确认的对白 {line} 未保留在英文 H3 成稿中")
    for item in requirements.get("ordered_references", []):
        label = str(item.get("label", "")).strip() if isinstance(item, dict) else ""
        if label and label not in english:
            issues.append(f"参考标签 {label} 未出现在英文 H3 成稿中")
    issues.extend(f"量化速度锚点中的数值 {number} 未保留在英文成稿中"
                  for number in missing_speed_numbers(english, requirements))
    issues.extend(f"英文成稿擅自添加动作内部时长 {number} 秒"
                  for number in unapproved_action_durations(english, requirements))
    audiovisual_text = "\n".join((str(requirements.get("script_zh", "")), chinese, english))
    sound_trigger = re.search(
        r"听到|闻声|循声|马蹄声|脚步声|hears?\b|hearing\b|hoofbeats?\b|footsteps?\b",
        audiovisual_text,
        flags=re.IGNORECASE,
    )
    if sound_trigger and re.search(r"overall_soundscape:\s*N/A|fully muted|hard-muted", english, flags=re.IGNORECASE):
        issues.append("动作依赖听觉提示，但成稿同时要求完全静音")
    if re.search(r"dissolv(?:e[sd]?|ing) into ash|no intact (?:body|corpse) remains?|化作飞灰|不再出现完整", audiovisual_text, flags=re.IGNORECASE) and re.search(
        r"(?:body|corpse) (?:lies|lying|remains)|倒地亡灵|亡灵(?:尸体|残躯)|身旁地上躺着",
        audiovisual_text,
        flags=re.IGNORECASE,
    ):
        issues.append("成稿存在不可逆状态冲突：目标化灰后又以完整尸体或残躯出现")
    return list(dict.fromkeys(issues))[:5]

def production_plan_digest(requirements: dict[str, Any], scene_design: dict[str, Any] | None,
                           shot_plan: dict[str, Any] | None) -> str:
    """Stable fingerprint for the approved director decisions.

    The digest is metadata, not a prompt instruction: it lets a later review or
    resume operation prove which approved plan a take was compiled from.
    """
    payload = {"requirements": requirements, "scene_design": scene_design, "shot_plan": shot_plan}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def director_capacity_issues(requirements: dict[str, Any], scene_design: dict[str, Any] | None,
                             shot_plan: dict[str, Any] | None) -> list[str]:
    """Flag only dialogue that plainly cannot fit; shot and action pacing is creative."""
    duration = float(requirements.get("duration_seconds") or requirements.get("brief", {}).get("duration_seconds") or 0)
    issues: list[str] = []
    dialogue = requirements.get("audio_plan", {}).get("dialogue", {})
    text = str(dialogue.get("content", "")) if isinstance(dialogue, dict) and dialogue.get("required") else ""
    if duration and text and len(re.sub(r"\s+", "", text)) > max(12, int(duration * 4.5)):
        issues.append("对白容量超过当前时长的自然说话预算，应拆分或延长片段")
    return issues
