"""Faithful draft translation without H3 prompt rewriting."""
import json

from backend.modules.shared.plugin_runtime import PluginError, parse_agent_json


def translate(request, runtime):
    inputs = request["inputs"]
    prompt = (
        "Translate the complete Chinese MiniMax H3 draft faithfully into English. "
        "Preserve every section name and its order, <Subject N>, <Picture N>, [Shot N], and all XML-like tags. "
        "Keep Chinese dialogue inside <d>[Chinese]...</d> unchanged. Do not optimize, add, omit, summarize, "
        "or comment. Return one JSON object only: {\"english_prompt\": \"...\"}."
    )
    raw = runtime.call_model([
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps({"mode": inputs.get("mode", "reference"),
                                               "chinese_draft": inputs["text"]}, ensure_ascii=False)},
    ], 7000)
    result = parse_agent_json(raw) or {}
    english = str(result.get("english_prompt", "")).strip()
    if not english:
        raise PluginError(502, "AI 未返回完整英文译稿，请重试")
    return {"english_prompt": english}
