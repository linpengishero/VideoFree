# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Declarative forms shared by discovery, generation and post-processing."""

import math
import re
from typing import Any


COMPONENTS = {"textarea", "text", "number", "select", "checkbox", "style", "voice", "media", "dimensions"}
PATH = re.compile(r"^(prompt|lyrics|target_size|upscaler|settings\.[a-zA-Z_][a-zA-Z0-9_]*|parameters\.[a-zA-Z_][a-zA-Z0-9_]*)$")


def validate_form(ui: dict, config: dict, *, postprocess: bool = False) -> None:
    if not isinstance(ui, dict) or ui.get("version") != 1 or not isinstance(ui.get("fields"), list):
        raise ValueError("ui requires version=1 and fields")
    seen = set()
    for field in ui["fields"]:
        if not isinstance(field, dict) or field.get("component") not in COMPONENTS or not isinstance(field.get("label"), str):
            raise ValueError("Invalid declarative UI field")
        bind = field.get("bind", "")
        if not isinstance(bind, str) or not PATH.fullmatch(bind) or bind in seen:
            raise ValueError(f"Invalid or duplicate UI binding: {bind}")
        seen.add(bind)
        if postprocess and not (bind.startswith("parameters.") or bind in {"target_size", "upscaler"}):
            raise ValueError(f"Unsupported postprocess binding: {bind}")
        if bind in {"target_size", "upscaler"} and not postprocess:
            raise ValueError(f"Postprocess-only UI binding: {bind}")
        if field["component"] == "select" and not field.get("options"):
            raise ValueError(f"select requires options: {bind}")
        if field.get("section", "settings") not in {"body", "settings", "submit"}:
            raise ValueError(f"Invalid UI section: {bind}")
        if bind.startswith("parameters.") and bind.split(".")[1] not in config.get("parameters", {}):
            raise ValueError(f"UI parameter is not registered: {bind}")
        if field["component"] == "media":
            media = field.get("media")
            if media not in {"image", "video", "audio"} or not config.get("references", {}).get(media, {}).get("max", 0):
                raise ValueError(f"UI media has no registered input: {bind}")
            if bind != f"settings.reference_{media}":
                raise ValueError(f"Invalid media binding: {bind}")
        if field["component"] == "dimensions":
            if not postprocess or bind != "target_size" or not field.get("presets"):
                raise ValueError("dimensions requires postprocess target_size and presets")
            if type(field.get("alignment")) is not int or field["alignment"] <= 0:
                raise ValueError("Invalid dimensions alignment")
            for preset in field["presets"]:
                if not isinstance(preset, dict) or type(preset.get("edge")) not in {int, float} or not math.isfinite(preset["edge"]) or preset["edge"] <= 0 or not isinstance(preset.get("label"), str):
                    raise ValueError("Invalid dimensions preset")
        for bound in ("minimum", "maximum", "step", "normal_chars_per_second"):
            if bound in field and (type(field[bound]) not in {int, float} or not math.isfinite(field[bound])):
                raise ValueError(f"Invalid UI bound: {bind}.{bound}")
        if field.get("minimum", -math.inf) > field.get("maximum", math.inf) or field.get("step", 1) <= 0:
            raise ValueError(f"Invalid UI range: {bind}")
        if "options" in field:
            options = field["options"]
            if not isinstance(options, list) or not options or any(not isinstance(x, dict) or type(x.get("value")) not in {str, int, float, bool} or not isinstance(x.get("label"), str) for x in options):
                raise ValueError(f"Invalid UI options: {bind}")
            values = [x["value"] for x in options]
            if len(set(values)) != len(values):
                raise ValueError(f"Duplicate UI options: {bind}")
        if "default" in field:
            validate_value(field, field["default"])
    template = ui.get("prompt_template")
    if template is not None:
        if not isinstance(template, dict) or not isinstance(template.get("fields"), list) or not isinstance(template.get("suffix", ""), str):
            raise ValueError("Invalid UI prompt_template")
        declared = {item["bind"]: item for item in ui["fields"]}
        for bind in template["fields"]:
            if bind not in declared or not declared[bind].get("options") or any(not isinstance(item.get("prompt"), str) for item in declared[bind]["options"]):
                raise ValueError(f"prompt_template must reference options with prompt: {bind}")
    if not postprocess and config.get("operation", "generate") == "generate":
        for media, limits in config.get("references", {}).items():
            if limits.get("max", 0) and f"settings.reference_{media}" not in seen:
                raise ValueError(f"Missing media UI: {media}")


def validate_value(field: dict, value: Any) -> None:
    label = field["label"]
    if field.get("required") and (value is None or isinstance(value, str) and not value.strip()):
        raise ValueError(f"{label}不能为空")
    if value is None:
        return
    component = field["component"]
    if component == "number":
        if type(value) not in {int, float} or not math.isfinite(value):
            raise ValueError(f"{label}必须是数字")
        if not field.get("minimum", -math.inf) <= value <= field.get("maximum", math.inf):
            raise ValueError(f"{label}超出允许范围")
    elif component == "checkbox" and type(value) is not bool:
        raise ValueError(f"{label}必须是布尔值")
    elif component in {"textarea", "text", "voice", "style"}:
        if not isinstance(value, str) or len(value) > field.get("maxLength", 100_000):
            raise ValueError(f"{label}文本无效或过长")
    if field.get("options") and value not in [item["value"] for item in field["options"]]:
        raise ValueError(f"{label}选项无效")


def form_values(ui: dict, payload: dict) -> dict:
    """Apply plugin defaults only to absent fields, then validate supplied values."""
    result = {**payload, "settings": dict(payload.get("settings", {})), "parameters": dict(payload.get("parameters", {}))}
    for field in ui.get("fields", []):
        if field["component"] in {"media", "dimensions"}:
            continue
        parts = field["bind"].split(".")
        target = result[parts[0]] if len(parts) == 2 else result
        name = parts[-1]
        if name not in target and "default" in field:
            target[name] = field["default"]
        validate_value(field, target.get(name))
    template = ui.get("prompt_template")
    if template and not result.get("prompt", "").strip():
        prompts = []
        for bind in template["fields"]:
            field = next(item for item in ui["fields"] if item["bind"] == bind)
            parts = bind.split(".")
            value = result[parts[0]].get(parts[1]) if len(parts) == 2 else result.get(bind)
            option = next((item for item in field["options"] if item["value"] == value), None)
            if not option:
                raise ValueError(f"{field['label']}选项无效")
            prompts.append(option["prompt"])
        result["prompt"] = " ".join([*prompts, template.get("suffix", "")]).strip()
    return result
