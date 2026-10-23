"""Segmented MiniMax H3 production pipeline, owned by this plugin.

Architecture: the director first writes ONE complete six-section draft for the
whole video. A separate editor stage then cuts that finished draft into 2-5
generation segments at shot-level breathing points (cut craft from the model,
hard validation from code), and each cut is converted into a standalone ref2va
execution draft with coverage checks against the source text. The conformance
review and the Chinese translation close the chain.
"""

import json
import hashlib
import math
import re
from datetime import datetime, timezone
from typing import Any

from backend.modules.shared.plugin_runtime import AgentCollaborationCancelled, parse_agent_json
from .analysis import (
    agent_prompt_issues, approved_dialogue_lines, missing_speed_numbers,
    production_plan_digest, unapproved_action_durations,
)
from .prompts import (
    DIRECTOR_CORE_SKILLS, chinese_translation_prompt, director_skill_catalog,
    director_skill_planner_prompt, h3_conformance_review_prompt, h3_director_prompt,
    h3_full_draft_prompt, load_director_skill, segment_splitting_prompt,
)


def run_director_skill_planner(
    generation: dict[str, Any], requirements: dict[str, Any], user_requests: list[str], call_model,
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
        result = parse_agent_json(call_model(messages, 2500)) or {}
    except AgentCollaborationCancelled:
        raise
    except ValueError:
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


def explicit_segment_structure(user_requests: list[str]) -> dict[str, float]:
    """Deterministically extract a user-stated segment structure from the raw requests."""
    text = "\n".join(str(item) for item in user_requests)
    structure: dict[str, float] = {}
    match = (re.search(r"分成?\s*(\d{1,2})\s*段", text)
             or re.search(r"(\d{1,2})\s*段", text)
             or re.search(r"(\d{1,2})\s*segments?", text, re.I))
    if match:
        structure["segments"] = int(match.group(1))
    match = (re.search(r"每段\s*(\d{1,2}(?:\.\d{1,2})?)\s*秒", text)
             or re.search(r"(\d{1,2}(?:\.\d{1,2})?)\s*秒\s*(?:每段|一段)", text)
             or re.search(r"(\d{1,2}(?:\.\d{1,2})?)\s*seconds?\s+(?:each|per\s+segment|apiece)", text, re.I))
    if match:
        structure["per_segment_duration"] = float(match.group(1))
    match = (re.search(r"总时长[^0-9]{0,8}(\d{1,3}(?:\.\d{1,2})?)\s*秒", text)
             or re.search(r"total\s+duration[^.]{0,20}?(\d{1,3}(?:\.\d{1,2})?)\s*seconds?", text, re.I))
    if match:
        structure["total_duration"] = float(match.group(1))
    return structure


def resolve_production_structure(user_requests: list[str], generation: dict[str, Any]) -> dict[str, float]:
    """Arithmetic the model never gets to renegotiate: the UI duration field is the
    whole-video total (the single authority); the prompt may still refine the segment
    count or per-segment length. At most 15 seconds per clip: totals up to 15 seconds
    generate as one segment, longer totals chain 2-5 segments."""
    structure = explicit_segment_structure(user_requests)
    total = float(generation.get("duration_seconds") or 10)
    per = structure.get("per_segment_duration")
    floor = math.ceil(total / 15)  # every clip must stay within 15 seconds
    profile = comfyui_segment_profile(generation.get("hardware_snapshot"))
    target = profile.get("planning_segment_seconds", 15)
    hardware_floor = math.ceil(total / target)
    if total <= 15:
        segments = 1
    else:
        requested = (int(structure["segments"]) if structure.get("segments") else
                     math.ceil(total / per) if per else hardware_floor)
        segments = max(1 if total <= 15 else 2, floor, requested)
        segments = min(5, segments)
    per = round(total / segments, 1)
    return {
        "segments": int(segments), "total_duration": float(total),
        "per_segment_duration": float(per), "hardware_profile": profile,
    }


def comfyui_segment_profile(snapshot: Any) -> dict[str, Any]:
    """Prefer shorter planning chunks when the configured ComfyUI GPU has little free VRAM."""
    observed_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    devices = snapshot.get("devices", []) if isinstance(snapshot, dict) else []
    cuda = [item for item in devices if isinstance(item, dict) and item.get("type") == "cuda"]
    measured = [item for item in cuda if type(item.get("total_memory_bytes")) is int
                and item["total_memory_bytes"] > 0 and type(item.get("free_memory_bytes")) is int]
    if not measured:
        return {"status": "unavailable", "planning_segment_seconds": 15, "observed_at": observed_at,
                "warning": "ComfyUI GPU memory is unavailable; the standard 15-second segment limit is used."}
    device = min(measured, key=lambda item: item["free_memory_bytes"] / item["total_memory_bytes"])
    ratio = max(0.0, min(1.0, device["free_memory_bytes"] / device["total_memory_bytes"]))
    constrained = ratio < 0.25
    return {
        "status": "constrained" if constrained else "available",
        "device": device.get("name", "CUDA device"),
        "device_count": len(measured),
        "total_vram_bytes": device["total_memory_bytes"],
        "free_vram_bytes": max(0, device["free_memory_bytes"]),
        "free_vram_ratio": round(ratio, 3),
        "planning_segment_seconds": 10 if constrained else 15,
        "observed_at": observed_at,
        "warning": (
            "Low free VRAM: prefer segments around 10 seconds, within the five-segment cap. "
            "This is a planning heuristic, not a guarantee that generation will fit."
            if constrained else
            "VRAM snapshot is advisory only; it does not guarantee a segment will fit at execution time."
        ),
    }


NO_DUPLICATES_CLAUSE = "no duplicates, clones, reflections or extra figures of any subject appear at any point"

SECTION_LABELS = ("subject_definitions", "summary", "retention_analysis", "detailed_description",
                  "overall_soundscape", "non_diegetic_music")


def draft_sections(draft: str) -> dict[str, str]:
    """Split a six-section draft into {label: body}; first occurrence of each label wins."""
    pattern = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?(" + "|".join(SECTION_LABELS)
                         + r")\s*:(?:\*\*)?\s*", re.I | re.M)
    matches = list(pattern.finditer(draft))
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(draft)
        sections.setdefault(match.group(1).lower(), draft[match.end():end].strip())
    return sections


def _shot_timestamp(seconds: float) -> str:
    total_ms = max(0, round(seconds * 1000))
    whole, millis = divmod(total_ms, 1000)
    minutes, seconds = divmod(whole, 60)
    return f"{minutes:02d}:{seconds:02d}.{millis:03d}"


def _checkpoint_for(session: dict[str, Any], requirements: dict[str, Any], user_requests: list[str]):
    generation = dict(session.get("generation", {}))
    generation.pop("hardware_snapshot", None)
    source = json.dumps({"generation": generation, "requirements": requirements,
                         "user_requests": user_requests}, ensure_ascii=False,
                        sort_keys=True, separators=(",", ":"), default=str)
    key = hashlib.sha256(source.encode("utf-8")).hexdigest()
    checkpoint = session.get("_minimax_h3_action_checkpoint")
    if not isinstance(checkpoint, dict) or checkpoint.get("key") != key:
        checkpoint = {"key": key, "version": 1, "segment_drafts": {}, "translations": {}}
        session["_minimax_h3_action_checkpoint"] = checkpoint
    return checkpoint


def _relative_shots(shots: str) -> str:
    marker = re.compile(r"\[Shot\s+\d+\](?:\s+At\s+(\d{2}):(\d{2})\.(\d{3}),)?", re.I)
    matches = list(marker.finditer(shots))
    if not matches:
        raise ValueError("分段稿没有可编译的镜头标记")

    def absolute_time(match):
        return (int(match.group(1)) * 60 + int(match.group(2)) + int(match.group(3)) / 1000
                if match.group(1) is not None else 0.0)

    offset = absolute_time(matches[0])
    result = shots
    for index in range(len(matches) - 1, -1, -1):
        match = matches[index]
        if index == 0:
            replacement = "[Shot 1]"
        else:
            replacement = f"[Shot {index + 1}] At {_shot_timestamp(max(0.0, absolute_time(match) - offset))},"
        result = result[:match.start()] + replacement + result[match.end():]
    return result


def compile_segment_prompt(index: int, cut: dict[str, Any], full_draft: str) -> str:
    """Render a valid segment prompt from approved source text; headings are never model-authored."""
    sections = draft_sections(full_draft)
    source_shots = str(cut.get("shots", "")).strip()
    detailed = sections.get("detailed_description", "")
    first_marker = re.search(r"\[Shot\s+\d+\]", detailed, re.I)
    style = detailed[:first_marker.start()].strip() if first_marker else ""
    shot_text = _relative_shots(source_shots)
    detail_parts = [part for part in (style, shot_text) if part]
    if index > 1:
        detail_parts.insert(1 if style else 0,
                            "Continue directly from the preceding segment's final frame. "
                            "Do not replay completed action or reset the scene.")

    segment_summary = str(cut.get("summary", "")).strip()
    if not segment_summary:
        first_shot = re.sub(r"^\[Shot\s+\d+\](?:\s+At\s+\d{2}:\d{2}\.\d{3},)?\s*", "",
                            source_shots, count=1, flags=re.I)
        segment_summary = first_shot.splitlines()[0].strip() if first_shot else sections.get("summary", "")
    if not segment_summary:
        segment_summary = sections.get("summary", "")
    if NO_DUPLICATES_CLAUSE not in segment_summary.lower():
        segment_summary = f"{segment_summary.rstrip()} {NO_DUPLICATES_CLAUSE}".strip()

    bodies = {
        "subject_definitions": sections.get("subject_definitions", "").strip(),
        "summary": segment_summary,
        "retention_analysis": sections.get("retention_analysis", "").strip(),
        "detailed_description": "\n\n".join(detail_parts),
        "overall_soundscape": str(cut.get("sound", "")).strip() or sections.get("overall_soundscape", "").strip() or "N/A",
        "non_diegetic_music": str(cut.get("music", "")).strip() or sections.get("non_diegetic_music", "").strip() or "N/A",
    }
    missing = [name for name in SECTION_LABELS if not bodies[name]]
    if missing:
        raise ValueError("整篇导演稿缺少无法安全继承的分段内容：" + ", ".join(missing))
    return "\n\n".join(f"{name}:\n{bodies[name]}" for name in SECTION_LABELS)


def _compile_structured_draft(raw: dict[str, Any], total_duration: float) -> tuple[str, list[str]]:
    sections = raw.get("sections")
    if not isinstance(sections, dict):
        return "", ["response must contain a structured `sections` object"]
    issues = [f"missing or empty section `{name}`" for name in SECTION_LABELS
              if name != "detailed_description" and name != "non_diegetic_music"
              if not isinstance(sections.get(name), str) or not sections[name].strip()]
    music = sections.get("non_diegetic_music")
    if not isinstance(music, str) or not music.strip():
        issues.append("missing or empty section `non_diegetic_music`")
    detail = sections.get("detailed_description")
    if not isinstance(detail, dict):
        issues.append("`detailed_description` must contain `style` and `shots`")
        return "", issues
    shots = detail.get("shots")
    if not isinstance(shots, list) or not shots:
        issues.append("`detailed_description.shots` must contain shot objects")
        return "", issues
    normalized_shots = []
    previous = -1.0
    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            issues.append(f"shot {index} must be an object")
            continue
        start = shot.get("start_seconds")
        description = str(shot.get("description", "")).strip()
        if type(start) not in {int, float} or not math.isfinite(start) or not 0 <= start <= total_duration:
            issues.append(f"shot {index} start_seconds must be within the approved video duration")
            continue
        if start <= previous:
            issues.append(f"shot {index} start_seconds must increase strictly")
        if (index == 1 and not math.isclose(start, 0, abs_tol=0.01)):
            issues.append("the first shot must start at 0 seconds")
        if not description or re.search(r"\[Shot\s+\d+\]", description, re.I):
            issues.append(f"shot {index} must contain only its description, without a [Shot N] label")
        normalized_shots.append((float(start), description))
        previous = float(start)
    if issues:
        return "", issues
    detail_text = str(detail.get("style", "")).strip()
    if detail_text:
        detail_text += "\n"
    for index, (start, description) in enumerate(normalized_shots, start=1):
        marker = f"[Shot {index}]"
        if index > 1:
            marker += f" At {_shot_timestamp(start)},"
        detail_text += f"{marker} {description}\n"
    bodies = {name: detail_text if name == "detailed_description" else sections[name].strip()
              for name in SECTION_LABELS}
    summary = bodies["summary"].rstrip().lower()
    if not summary.endswith(NO_DUPLICATES_CLAUSE):
        issues.append("summary must end with the exact subject-count lock clause")
    output = "\n\n".join(f"{name}:\n{bodies[name]}" for name in SECTION_LABELS)
    return output, issues


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def _shot_markers(text: str) -> list[str]:
    return re.findall(r"\[Shot\s+(\d+)\]", text, re.I)


def _speed_numbers_in(requirements: dict[str, Any], text: str) -> list[str]:
    plan = requirements.get("kinetic_plan", {})
    numbers = list(dict.fromkeys(
        number for key in ("quantitative_anchors", "proposed_speed_anchors")
        for anchor in plan.get(key, [])
        for number in re.findall(r"\d+(?:\.\d+)?", str(anchor))))
    return [number for number in numbers
            if re.search(r"(?<![\d.])" + re.escape(number) + r"(?![\d.])", text)]


# ---------------------------------------------------------------------------
# Stage: full-length director draft
# ---------------------------------------------------------------------------

def production_structure_note(structure: dict[str, float]) -> str:
    """Binding structure brief for the requirements stage (single-clip scoping is the old bug)."""
    total = structure["total_duration"]
    profile = structure.get("hardware_profile", {})
    hardware_note = (" ComfyUI hardware snapshot: " + str(profile.get("warning"))
                     if isinstance(profile, dict) and profile.get("warning") else "")
    if structure["segments"] <= 1:
        return ("PRODUCTION STRUCTURE (binding, machine-extracted): this production is ONE continuous video "
                f"of {total:g} seconds, generated as a single clip. Plan the FULL story across the whole "
                f"{total:g} seconds: the brief, event_chain, script_zh, audio plan and required_ending must "
                "cover the user's complete story from opening to final ending, paced to fill the duration. "
                f"brief.duration_seconds must equal {total:g}." + hardware_note)
    return ("PRODUCTION STRUCTURE (binding, machine-extracted): this production is ONE continuous video of "
            f"{total:g} seconds, generated as {int(structure['segments'])} chained "
            "segments of 1-15 seconds each. Plan the FULL story across the whole duration: the brief, "
            "event_chain, script_zh, audio plan and required_ending must cover the user's complete story "
            "from opening to final ending. The per-clip generation limit applies to each segment, never to "
            "the story; do NOT scope the production down to one clip or one highlight moment. "
            f"brief.duration_seconds must equal {total:g}." + hardware_note)


def duration_coverage_issues(detailed: str, total_duration: float) -> list[str]:
    """The draft's shot timestamps must run to the approved total, not stop at one clip."""
    if len(_shot_markers(detailed)) == 1:
        return []
    seconds = [int(h) * 60 + int(m) + int(f or 0) / (10 ** len(f or "0"))
               for h, m, f in re.findall(r"(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?", detailed)]
    reached = max(seconds, default=0.0)
    if reached < 0.5 * total_duration:
        return [f"the last detailed_description shot begins at {reached:g}s, before the midpoint of the "
                f"approved {total_duration:g}s total; cover the complete story through its ending"]
    return []


def full_draft_contract_text(structure: dict[str, float]) -> str:
    if structure["segments"] <= 1:
        opening = [
            f"The whole video is one generation clip of {structure['total_duration']} seconds; there is no "
            "segmentation. Pace the story to fill exactly this duration.",
            "Cover the COMPLETE approved story (every event_chain event through the required ending) across "
            f"the full {structure['total_duration']} seconds.",
        ]
    else:
        opening = [
            f"The whole video is {structure['total_duration']} seconds. It will later be cut into exactly "
            f"{structure['segments']} generation segments of 1-15 seconds each at your [Shot N] boundaries, "
            "so pace the story to be cuttable that way.",
            "Cover the COMPLETE approved story (every event_chain event through the required ending) across the "
            f"full {structure['total_duration']} seconds. The per-clip generation limit applies to each segment, "
            "never to the story: never scope the draft down to one clip or one highlight moment.",
        ]
    rules = opening + [
        "Return the six sections as structured JSON fields under `sections`, not as a preformatted prompt. "
        "Use string values for subject_definitions, summary, retention_analysis, overall_soundscape, "
        "and non_diegetic_music. Use an object for detailed_description with `style` and `shots`.",
        "Each detailed_description.shots item must be {\"start_seconds\": number, \"description\": string}; "
        "the first shot starts at 0, later start_seconds values increase strictly, and descriptions contain "
        "no [Shot N] labels or timestamps. The application will format the H3 headings and shot markers.",
        "Shot 1 is the opening shot and has no timestamp, following the H3 ref2va format. Later shots use "
        "[Shot N] At MM:SS.mmm, to mark cut times.",
        "`<Picture 1>` stays the appearance authority.",
        "Every approved dialogue line appears verbatim in its original language inside a [Shot N] block; "
        "every approved speed anchor appears at the action it qualifies.",
        "Reference images may show the same character from several angles; that is a character sheet, not "
        "several characters. Declare the exact number of on-screen subjects and end the summary section "
        f"with this exact clause: \"{NO_DUPLICATES_CLAUSE}\".",
        "Never use ellipses, placeholders, or references to segments.",
    ]
    return "\n".join(f"- {rule}" for rule in rules) + "\n\n```json\n{\n" \
        "  \"status\": \"ready\",\n  \"message\": \"one short English sentence\",\n" \
        "  \"sections\": {\n" \
        "    \"subject_definitions\": \"...\",\n    \"summary\": \"... exact subject-count lock clause\",\n" \
        "    \"retention_analysis\": \"...\",\n    \"detailed_description\": {\"style\": \"...\", " \
        "\"shots\": [{\"start_seconds\": 0, \"description\": \"...\"}]},\n" \
        "    \"overall_soundscape\": \"...\",\n    \"non_diegetic_music\": \"...\"\n  }\n}\n```"


def compile_full_draft(generation: dict[str, Any], requirements: dict[str, Any],
                       structure: dict[str, float], approved_digest: str,
                       selected_skill_text: str, call_model) -> str:
    mode = generation["mode"]
    system = h3_full_draft_prompt(mode, requirements, selected_skill_text)
    system += "\n\n---\n\n# Full-Length Draft Contract\n\n" + full_draft_contract_text(structure)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({
            "generation": generation,
            "approved_requirements": requirements,
            "production_structure": structure,
            "director_contract": {
                "approved_plan_digest": approved_digest,
                "immutable_fields": [
                    "user intent", "character identities and roles", "exact dialogue", "reference ownership",
                    "total duration", "required ending", "music choice", "continuity locks",
                ],
                "director_owns": [
                    "continuous action and performance", "shot count and cut points", "blocking",
                    "camera placement and movement", "focus", "sound description",
                ],
            },
        }, ensure_ascii=False, indent=2)},
    ]
    issues: list[str] = []
    for attempt in range(3):
        raw = parse_agent_json(call_model(messages, 9000)) or {}
        prompt, issues = _compile_structured_draft(raw, structure["total_duration"])
        if prompt:
            issues.extend(agent_prompt_issues(prompt, "minimax-h3-action", mode))
        issues.extend(f"missing approved speed value {number}"
                      for number in missing_speed_numbers(prompt, requirements))
        issues.extend(f"missing approved dialogue line {line}"
                      for line in approved_dialogue_lines(requirements) if line not in prompt)
        if NO_DUPLICATES_CLAUSE not in prompt.lower():
            issues.append(f"missing subject-count lock: end the summary with \"{NO_DUPLICATES_CLAUSE}\"")
        if not _shot_markers(draft_sections(prompt).get("detailed_description", "")):
            issues.append("detailed_description must be split into [Shot N] blocks with timestamps")
        else:
            issues.extend(duration_coverage_issues(draft_sections(prompt)["detailed_description"],
                                                   structure["total_duration"]))
        if raw.get("status") == "ready" and prompt and not issues:
            return prompt
        if attempt < 2:
            messages = [*messages, {"role": "assistant", "content": json.dumps(raw, ensure_ascii=False)},
                {"role": "user", "content":
                "The full-length draft needs correction: "
                + "; ".join(issues or ["missing ready status or prompt"]) + ".\n"
                + "Return corrected structured JSON under sections, preserving the six required fields, "
                "the approved story, speed anchors and dialogue. The application renders all H3 heading and "
                "shot syntax. Do not rerun requirements or skills planning; do not use placeholders."}]
    raise ValueError("整篇导演成稿未编译出完整英文 H3 稿：" + "；".join(issues or ["缺少 ready 状态或成稿"]))


# ---------------------------------------------------------------------------
# Stage: editor splitting at breathing points
# ---------------------------------------------------------------------------

def split_plan_issues(plan: dict[str, Any], full_draft: str, structure: dict[str, float],
                      requirements: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if plan.get("status") != "ready":
        issues.append("status must be ready")
    segments = int(structure["segments"])
    if plan.get("segments") != segments:
        issues.append(f"segments must equal the required count {segments}")
    cuts = plan.get("segment_cuts") if isinstance(plan.get("segment_cuts"), list) else []
    if len(cuts) != segments:
        issues.append(f"segment_cuts must contain exactly {segments} entries")
        return issues
    detailed = _normalize(draft_sections(full_draft).get("detailed_description", ""))
    draft_shots = _shot_markers(detailed)
    seen_shots: list[str] = []
    durations: list[float] = []
    dialogue_lines = [line for line in approved_dialogue_lines(requirements) if line in full_draft]
    line_cuts = {line: 0 for line in dialogue_lines}
    for index, item in enumerate(cuts, start=1):
        if not isinstance(item, dict):
            issues.append(f"segment_cuts[{index}] must be an object")
            continue
        if int(item.get("index", 0) or 0) != index:
            issues.append(f"segment_cuts[{index}].index must equal {index}")
        duration = item.get("duration")
        if not (type(duration) in {int, float} and 1 <= duration <= 15):
            issues.append(f"segment_cuts[{index}].duration must be a number between 1 and 15")
        else:
            durations.append(float(duration))
        shots = _normalize(item.get("shots", ""))
        if not shots:
            issues.append(f"segment_cuts[{index}].shots must not be empty")
            continue
        if shots not in detailed:
            issues.append(f"segment_cuts[{index}].shots must be copied verbatim from the draft's "
                          "detailed_description, unchanged")
        seen_shots.extend(_shot_markers(shots))
        end_state = _normalize(item.get("end_state", ""))
        if not end_state:
            issues.append(f"segment_cuts[{index}].end_state must not be empty")
        elif end_state not in shots:
            issues.append(f"segment_cuts[{index}].end_state must be copied verbatim from the "
                          "segment's last shot")
        for line in dialogue_lines:
            if line in shots:
                line_cuts[line] += 1
    if len(durations) == segments and not math.isclose(
        sum(durations), structure["total_duration"], rel_tol=0, abs_tol=0.05
    ):
        issues.append(f"the segment durations must sum to {structure['total_duration']} seconds "
                      f"(received {sum(durations):g})")
    if seen_shots != draft_shots:
        issues.append("the shots must be partitioned in order: every [Shot N] of the draft belongs to "
                      "exactly one segment, none dropped or duplicated")
    for line, count in line_cuts.items():
        if count != 1:
            issues.append(f"approved dialogue line \"{line}\" must appear in exactly one segment "
                          f"(found in {count})")
    return issues


def run_segment_splitter(full_draft: str, structure: dict[str, float],
                         requirements: dict[str, Any], call_model) -> dict[str, Any]:
    messages = [
        {"role": "system", "content": segment_splitting_prompt()},
        {"role": "user", "content": json.dumps({
            "full_draft": full_draft,
            "required_segments": int(structure["segments"]),
            "total_duration": structure["total_duration"],
            "average_segment_duration": structure["per_segment_duration"],
        }, ensure_ascii=False, indent=2)},
    ]
    plan: dict[str, Any] = {}
    issues: list[str] = []
    for attempt in range(3):
        plan = parse_agent_json(call_model(messages, 9000)) or {}
        issues = split_plan_issues(plan, full_draft, structure, requirements)
        if not issues:
            break
        if attempt < 2:
            messages = [*messages, {"role": "user", "content":
                "The cut plan is not executable: " + "; ".join(issues) +
                ". The segment count is fixed, shot text must be copied verbatim, and every shot must "
                "belong to exactly one segment. Return the complete corrected JSON object."}]
    if issues:
        raise ValueError("分段拆分自动修正后仍不可执行：" + "；".join(issues))
    return plan


# ---------------------------------------------------------------------------
# Stage: per-segment conversion into standalone ref2va drafts
# ---------------------------------------------------------------------------

def conversion_contract_text(index: int, segments: int, duration: float, previous_end_state: str) -> str:
    rules = [
        f"You are converting cut {index} of {segments} of one continuation chain into a standalone "
        f"MiniMax H3 ref2va execution draft for one independent {duration}-second clip.",
        "Return exactly one complete six-section draft (subject_definitions / summary / retention_analysis / "
        "detailed_description / overall_soundscape / non_diegetic_music) inside the JSON contract field "
        "`optimized_prompt`.",
        "`subject_definitions` is copied from the full draft unchanged.",
        "`detailed_description` uses the provided shots verbatim; only renumber the shot timestamps so the "
        "clip starts at 00:00.000. Add no story beats and drop none.",
        "`summary` is scoped to this segment only and ends with this exact clause: "
        f"\"{NO_DUPLICATES_CLAUSE}\".",
        "`overall_soundscape` / `non_diegetic_music` use the provided sound / music slices; when a slice is "
        "empty, carry over the full draft's section as-is.",
        "`<Picture 1>` stays the appearance authority: the same reference images are supplied to every segment.",
        "Never use ellipses, placeholders, or references to another segment's text.",
    ]
    if index > 1:
        rules.append(
            "This segment continues the previous one. Before the first [Shot N] block, open with one "
            "sentence that resumes exactly from the previous segment's ending state given below: same "
            "pose, balance, occupied limbs, prop ownership, positions and screen direction. Do not replay "
            "the previous beat and do not reset to a neutral stance."
        )
    return "\n".join(f"- {rule}" for rule in rules) + "\n\n```json\n{\n" \
        "  \"status\": \"ready\",\n  \"message\": \"one short English sentence\",\n" \
        "  \"optimized_prompt\": \"complete ref2va six-section English draft for this segment only\"\n}\n```"


def convert_segment(index: int, segments: int, cut: dict[str, Any], full_draft: str,
                    previous_end_state: str, generation: dict[str, Any],
                    requirements: dict[str, Any], approved_digest: str,
                    selected_skill_text: str, call_model) -> str:
    mode = generation["mode"]
    duration = float(cut["duration"])
    system = h3_director_prompt(mode, requirements, selected_skill_text)
    system += "\n\n---\n\n# Segment Conversion Contract\n\n" + conversion_contract_text(
        index, segments, duration, previous_end_state)
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({
            "generation": generation,
            "approved_requirements": requirements,
            "segment_cut": cut,
            "full_draft": full_draft,
            "previous_segment_end_state": previous_end_state or None,
            "director_contract": {
                "approved_plan_digest": approved_digest,
                "immutable_fields": [
                    "user intent", "character identities and roles", "exact dialogue", "reference ownership",
                    "per-segment duration", "required ending", "music choice", "continuity locks",
                ],
                "director_owns": [
                    "shot opening continuation sentence", "retention analysis wording",
                    "summary scoping", "sound description",
                ],
            },
        }, ensure_ascii=False, indent=2)},
    ]
    shots = str(cut.get("shots", ""))
    issues: list[str] = []
    for attempt in range(3):
        raw = parse_agent_json(call_model(messages, 7000)) or {}
        prompt = str(raw.get("optimized_prompt", "")).strip()
        issues = agent_prompt_issues(prompt, "minimax-h3-action", mode)
        issues.extend(f"missing speed anchor {number} from this segment's shots"
                      for number in _speed_numbers_in(requirements, shots)
                      if not re.search(r"(?<![\d.])" + re.escape(number) + r"(?![\d.])", prompt))
        issues.extend(f"missing approved dialogue line {line}"
                      for line in approved_dialogue_lines(requirements)
                      if line in shots and line not in prompt)
        issues.extend(f"unapproved internal action duration {number} seconds"
                      for number in unapproved_action_durations(prompt, requirements))
        if NO_DUPLICATES_CLAUSE not in prompt.lower():
            issues.append(f"missing subject-count lock: end the summary with \"{NO_DUPLICATES_CLAUSE}\"")
        if raw.get("status") == "ready" and prompt and not issues:
            return prompt
        if attempt < 2:
            messages = [*messages, {"role": "assistant", "content": json.dumps(
                {"status": raw.get("status"), "optimized_prompt": prompt}, ensure_ascii=False)},
                {"role": "user", "content":
                f"The English H3 draft for segment {index} needs correction: "
                + "; ".join(issues or ["missing ready status or prompt"]) + ".\n"
                + "The six sections must appear exactly once each, in this exact order, each as its own "
                "top-level line label: subject_definitions: -> summary: -> retention_analysis: -> "
                "detailed_description: -> overall_soundscape: -> non_diegetic_music:. If the order is "
                "wrong, reorder the existing sections without rewriting their content. Preserve approved "
                "speed anchors and dialogue. Return the complete corrected draft in the same JSON "
                "contract, without placeholders."}]
    raise ValueError(f"第 {index} 段转换稿未编译出完整英文 H3 执行稿：" + "；".join(issues or ["缺少 ready 状态或成稿"]))


def conform_segments(drafts: list[str], cuts: list[dict[str, Any]], full_draft: str,
                     generation: dict[str, Any], requirements: dict[str, Any],
                     user_requests: list[str], call_model,
                     selected_skill_text: str, approved_digest: str) -> tuple[list[str], str]:
    """One review pass over the whole chain; repair only flagged segments."""
    review_payload = {
        "original_user_requests": user_requests,
        "approved_requirements": requirements,
        "full_draft": full_draft,
        "segment_cuts": [{"index": index, "duration": cut.get("duration"),
                          "end_state": cut.get("end_state")} for index, cut in enumerate(cuts, start=1)],
        "english_drafts": [{"segment_index": index, "draft": draft}
                           for index, draft in enumerate(drafts, start=1)],
        "review_note": "issues must carry segment_index (1-based). HARD ERRORS that must be flagged: "
                       "(1) a segment that does not open by continuing the previous segment's end_state "
                       "(replay, reset, or a neutral stance instead of the inherited pose, props, "
                       "positions and screen direction); (2) a draft missing the subject-count lock "
                       "(\"no duplicates, clones, reflections or extra figures\") or describing any "
                       "duplicate or extra figure of a subject; (3) a broken six-section order; "
                       "(4) a segment that dropped or invented story beats against its cut shots. "
                       "Reference images may show one character from several angles: that is a character "
                       "sheet and never licenses extra characters on screen.",
    }
    try:
        review = parse_agent_json(call_model([
            {"role": "system", "content": h3_conformance_review_prompt()},
            {"role": "user", "content": json.dumps(review_payload, ensure_ascii=False)},
        ], 3000)) or {}
    except ValueError as exc:
        return drafts, f"链式契约检查未完成，保留导演初稿供人工确认：{exc}"
    issues = review.get("issues") if isinstance(review.get("issues"), list) else []
    issues = [item for item in issues if isinstance(item, dict) and str(item.get("problem", "")).strip()][:8]
    if review.get("conforms") is True and not issues:
        return drafts, ""
    if not issues:
        return drafts, "链式契约检查未返回可执行结论，保留导演初稿供人工确认。"
    repaired = list(drafts)
    warnings = []
    for item in issues:
        try:
            index = int(item.get("segment_index", 0))
        except (TypeError, ValueError):
            index = 0
        if not 1 <= index <= len(drafts):
            warnings.append(f"契约审查返回了无效的 segment_index：{item.get('segment_index')!r}；未能自动修订")
            continue
        try:
            repaired[index - 1] = convert_segment(
                index, len(drafts), cuts[index - 1], full_draft,
                str(cuts[index - 2].get("end_state", "")) if index > 1 else "",
                generation, requirements, approved_digest, selected_skill_text, call_model)
        except ValueError as exc:
            warnings.append(f"第 {index} 段契约修订未完成：{exc}")
    if not warnings and issues:
        warnings.append("契约审查发现问题，但没有可执行的修订结果；请人工核对")
    return repaired, "；".join(warnings)


def translate_segment(draft: str, requirements: dict[str, Any], call_model) -> str:
    messages = [
        {"role": "system", "content": chinese_translation_prompt()},
        {"role": "user", "content": json.dumps({
            "mode": "reference", "english_execution_draft": draft,
            "approved_dialogue_lines_zh": approved_dialogue_lines(requirements),
        }, ensure_ascii=False)},
    ]
    for attempt in range(2):
        raw = parse_agent_json(call_model(messages, 7000)) or {}
        translated = str(raw.get("optimized_prompt_zh", "")).strip()
        if translated:
            return translated
        if attempt == 0:
            messages.extend([
                {"role": "assistant", "content": json.dumps(raw, ensure_ascii=False)},
                {"role": "user", "content":
                 "The Chinese translation is missing or empty. Return the complete Chinese translation "
                 "in optimized_prompt_zh and preserve all approved dialogue verbatim."},
            ])
    raise ValueError("中文翻译连续两次未返回有效确认稿")


def run_segmented_production(session: dict[str, Any], requirements: dict[str, Any], progress, call_model,
                             hardware_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    generation = dict(session["generation"])
    if hardware_snapshot is not None:
        generation["hardware_snapshot"] = hardware_snapshot
    user_requests = session.get("user_requests", [])
    checkpoint = _checkpoint_for(session, requirements, user_requests)
    structure = checkpoint.get("structure")
    if not isinstance(structure, dict):
        structure = resolve_production_structure(user_requests, generation)
        checkpoint["structure"] = structure
    segments = int(structure["segments"])
    total = structure["total_duration"]

    def report(stage_id, status, message):
        if progress:
            progress(stage_id, status, message)

    skill_plan = checkpoint.get("skill_planning")
    if isinstance(skill_plan, dict):
        selected_skill_ids = skill_plan.get("ids", [])
        skill_reasons = skill_plan.get("reasons", [])
        report("skill_planning", "completed", "沿用已完成的导演技能规划")
    else:
        report("skill_planning", "running", "正在根据剧情需求选择适用导演技能")
        try:
            selected_skill_ids, skill_reasons = run_director_skill_planner(
                generation, requirements, user_requests, call_model)
        except Exception:
            checkpoint["failed_stage"] = "skill_planning"
            raise
        checkpoint["skill_planning"] = {"ids": selected_skill_ids, "reasons": skill_reasons}
        report("skill_planning", "completed", f"已加载 {len(selected_skill_ids)} 项适用技能")
    selected_skill_text = "\n\n".join(load_director_skill(skill_id) for skill_id in selected_skill_ids)
    approved_digest = production_plan_digest(requirements, None, None)

    full_draft = checkpoint.get("full_draft")
    if full_draft:
        report("full_draft", "completed", "沿用已通过校验的整篇导演稿")
    else:
        report("full_draft", "running", f"正在撰写 {total:g} 秒整篇导演成稿")
        try:
            full_draft = compile_full_draft(generation, requirements, structure, approved_digest,
                                            selected_skill_text, call_model)
        except ValueError as first_error:
            report("full_draft", "running", "整篇稿格式校验未通过，正在仅重做整篇导演成稿阶段")
            try:
                full_draft = compile_full_draft(generation, requirements, structure, approved_digest,
                                                selected_skill_text, call_model)
            except ValueError as retry_error:
                checkpoint["failed_stage"] = "full_draft"
                raise ValueError(f"整篇导演成稿阶段重试仍失败：{retry_error}") from first_error
        except Exception:
            checkpoint["failed_stage"] = "full_draft"
            raise
        checkpoint["full_draft"] = full_draft
        report("full_draft", "completed", "整篇导演成稿完成")

    if segments <= 1:
        # Single clip: the full draft is the execution draft; no splitting, chaining or merging.
        drafts = [full_draft]
        cuts = [{"index": 1, "duration": total, "end_state": "", "cut_reason": "single clip"}]
        durations = [total]
        for stage_id, message in (("segmentation", "总时长不超过 15 秒，单段生成无需拆分"),
                                  ("compiler", "单段执行稿即整篇成稿"),
                                  ("conformance", "单段无需链式契约检查")):
            report(stage_id, "running", message)
            report(stage_id, "completed", message)
        revision_warning = ""
    else:
        plan = checkpoint.get("segmentation")
        if isinstance(plan, dict):
            report("segmentation", "completed", "沿用已通过校验的分段计划")
        else:
            report("segmentation", "running", f"正在沿镜头呼吸点拆分为 {segments} 段")
            try:
                plan = run_segment_splitter(full_draft, structure, requirements, call_model)
            except Exception:
                checkpoint["failed_stage"] = "segmentation"
                raise
            checkpoint["segmentation"] = plan
        cuts = plan["segment_cuts"]
        durations = [float(cut["duration"]) for cut in cuts]
        report("segmentation", "completed", "拆分完成：" + " / ".join(f"{d:g}秒" for d in durations))

        report("compiler", "running", f"正在编译第 1/{segments} 段 H3 英文执行稿")
        compiled = checkpoint.setdefault("segment_drafts", {})
        drafts = []
        for index in range(1, segments + 1):
            key = str(index)
            if key in compiled:
                drafts.append(compiled[key])
                continue
            report("compiler", "running", f"正在编译第 {index}/{segments} 段 H3 英文执行稿")
            try:
                draft = compile_segment_prompt(index, cuts[index - 1], full_draft)
                issues = agent_prompt_issues(draft, "minimax-h3-action", "reference")
                issues.extend(f"missing approved speed value {number}"
                              for number in missing_speed_numbers(draft, requirements))
                issues.extend(f"missing approved dialogue line {line}"
                              for line in approved_dialogue_lines(requirements)
                              if line in cuts[index - 1].get("shots", "") and line not in draft)
                issues.extend(f"unapproved internal action duration {number} seconds"
                              for number in unapproved_action_durations(draft, requirements))
                if issues:
                    raise ValueError("；".join(issues))
            except Exception:
                checkpoint["failed_stage"] = "compiler"
                checkpoint["failed_segment"] = index
                # A different cut plan may resolve a deterministic mapping issue;
                # keep the expensive full draft but invalidate dependent artifacts.
                checkpoint.pop("segmentation", None)
                checkpoint["segment_drafts"] = {}
                checkpoint.pop("conformance", None)
                checkpoint["translations"] = {}
                raise
            compiled[key] = draft
            drafts.append(draft)
        report("compiler", "completed", f"{segments} 段 H3 执行稿已由代码编译完成")

        conformance = checkpoint.get("conformance")
        if isinstance(conformance, dict):
            drafts = conformance.get("drafts", drafts)
            revision_warning = conformance.get("warning", "")
            report("conformance", "completed", "沿用已完成的连戏与约束检查")
        else:
            report("conformance", "running", "正在检查参考锚定、段间连续性与用户约束")
            drafts, revision_warning = conform_segments(
                drafts, cuts, full_draft, generation, requirements, user_requests,
                call_model, selected_skill_text, approved_digest)
            checkpoint["conformance"] = {"drafts": drafts, "warning": revision_warning}
            report("conformance", "completed", "链式契约检查完成")

    report("translation", "running", "正在翻译中文确认稿")
    translated_segments = checkpoint.setdefault("translations", {})
    zh_parts = []
    for index, draft in enumerate(drafts, start=1):
        key = str(index)
        if key in translated_segments:
            zh = translated_segments[key]
        else:
            try:
                zh = translate_segment(draft, requirements, call_model)
            except Exception:
                checkpoint["failed_stage"] = "translation"
                checkpoint["failed_segment"] = index
                raise
            translated_segments[key] = zh
        zh_parts.append(zh if segments <= 1
                        else f"【第{_cn_number(index)}段·{durations[index - 1]:g}秒】{zh}")
    zh_text = "\n".join(zh_parts) if segments <= 1 else "\n".join(zh_parts) + "\n共 {} 段，逐段时长 {} 秒，总计约 {:g} 秒。".format(
        segments, " / ".join(f"{d:g}" for d in durations), sum(durations))
    if progress: progress("translation", "completed", "中文确认稿已返回，分段导演管线完成")

    warnings = [item for item in (revision_warning,) if item]
    message = (f"单段 {total:g} 秒执行稿已完成，确认后一次生成。" if segments <= 1 else
               f"{segments} 段连续执行稿已完成（{' / '.join(f'{d:g}秒' for d in durations)}），确认后一次生成合并视频。")
    result = {
        "status": "ready",
        "message": message,
        "questions": [],
        "optimized_prompt": drafts[0],
        "optimized_prompt_zh": zh_text,
        "generation_payload": {
            "parameters": {"segments": segments, "durations": ",".join(f"{d:g}" for d in durations),
                           **{f"prompt_{index}": drafts[index - 1] for index in range(2, segments + 1)}},
            "settings": {"duration": total},
        },
        "review": {
            "mode": "internal",
            "summary": "分段导演管线已完成，请确认中英文成稿。",
            "hard_errors": [],
            "warnings": warnings,
            "compiler_corrections": [],
            "confirmed_strengths": [],
        },
        "production_plan": {
            "requirements": requirements,
            "production_structure": structure,
            "full_draft": full_draft,
            "segment_cuts": [{"index": index, "duration": cut.get("duration"),
                              "end_state": cut.get("end_state"), "cut_reason": cut.get("cut_reason")}
                             for index, cut in enumerate(cuts, start=1)],
            "selected_skills": selected_skill_ids,
            "skill_reasons": skill_reasons,
            "approved_plan_digest": approved_digest,
        },
    }
    checkpoint.pop("failed_stage", None)
    checkpoint.pop("failed_segment", None)
    return result


CN_NUMBERS = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五"}


def _cn_number(index: int) -> str:
    return CN_NUMBERS.get(index, str(index))
