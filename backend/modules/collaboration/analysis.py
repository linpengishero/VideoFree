# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Pure parsing and deterministic review rules for director collaboration."""

import json
from typing import Any


def parse_agent_json(content: str) -> dict[str, Any] | None:
    value = content.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        try:
            result = json.loads(value[start:end + 1]) if start >= 0 and end > start else None
        except json.JSONDecodeError:
            result = None
    return result if isinstance(result, dict) else None


def normalized_agent_questions(result: dict[str, Any]) -> list[dict[str, Any]]:
    questions = []
    if not isinstance(result.get("questions"), list):
        return questions
    for index, question in enumerate(result["questions"]):
        if not isinstance(question, dict):
            continue
        text = str(question.get("text", "")).strip()
        raw_options = question.get("options", [])
        if not text or not isinstance(raw_options, list):
            continue
        options = list(dict.fromkeys(str(option).strip() for option in raw_options if str(option).strip()))
        if options:
            questions.append({
                "id": str(question.get("id", "")).strip() or f"question_{index + 1}",
                "text": text,
                "options": options,
            })
    return questions




def parse_agent_result(content: str) -> dict[str, Any]:
    result = parse_agent_json(content)
    if not result:
        return {"status": "needs_input", "message": content, "questions": [], "reference_map": [], "decisions": [], "optimized_prompt_zh": "", "optimized_prompt": ""}
    nested = parse_agent_json(str(result.get("message", "")))
    if nested and nested.get("status") in {"ready", "needs_input"}:
        result = {**result, **nested}
    normalized = {
        "status": "ready" if result.get("status") == "ready" and str(result.get("optimized_prompt", "")).strip() and str(result.get("optimized_prompt_zh", "")).strip() else "needs_input",
        "message": str(result.get("message", "")).strip() or "我还需要一点信息才能继续。",
        "questions": normalized_agent_questions(result),
        "reference_map": result.get("reference_map") if isinstance(result.get("reference_map"), list) else [],
        "decisions": result.get("decisions") if isinstance(result.get("decisions"), list) else [],
        "optimized_prompt_zh": str(result.get("optimized_prompt_zh", "")).strip(),
        "optimized_prompt": str(result.get("optimized_prompt", "")).strip(),
        "optimized_shots": [str(item).strip() for item in result.get("optimized_shots", []) if str(item).strip()][:4]
        if isinstance(result.get("optimized_shots"), list) else [],
        "generation_payload": result.get("generation_payload") if isinstance(result.get("generation_payload"), dict) else {},
    }
    return normalized
