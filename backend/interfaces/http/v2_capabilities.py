# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

from typing import Any
import math
import re

from fastapi import HTTPException

from .v2_schemas import AssetInput


RESOLUTIONS = {"480P": 480, "576P": 576, "720P": 720, "768P": 768, "1K": 1024, "1080P": 1080, "1440P": 1440, "2K": 2048}


def model_and_mode(capability_id: str, config: dict[str, Any]) -> tuple[str, str, str]:
    return config["kind"], str(config.get("model_family", config.get("model_id", ""))), config["mode"]


def declared_options(config, bind):
    field = next((field for field in config.get("ui", {}).get("fields", []) if field.get("bind") == bind), {})
    return [item["value"] for item in field.get("options", [])]


def declared_duration(config):
    if "duration" in config:
        return config["duration"]
    field = next((field for field in config.get("ui", {}).get("fields", [])
                  if field.get("bind") == "settings.duration"), None)
    if field and "minimum" in field and "maximum" in field:
        return {"min": field["minimum"], "max": field["maximum"], "default": field.get("default", field["minimum"])}
    return None



def capability(capability_id: str, config: dict[str, Any]) -> dict[str, Any]:
    kind, model, mode = model_and_mode(capability_id, config)
    variants = config.get("variants", {})
    public_variant_ids = config.get("public_variants")
    if isinstance(public_variant_ids, list):
        variants = {key: variants[key] for key in public_variant_ids if key in variants}
    roles = {media: [] for media in ("image", "video", "audio")}
    for media in roles:
        if isinstance(config.get("input_roles", {}).get(media), list): roles[media] = config["input_roles"][media]
    public_model = config.get("model_id", model)
    processing_modes = config.get("processing_modes", [{"id": "direct", "name": "直接生成"}])
    collaboration_supported = any(item["id"] != "direct" for item in processing_modes)
    references = config.get("references", {})
    limits = {media: {"min": int(references.get(media, {}).get("min", 0)), "max": int(references.get(media, {}).get("max", 0))} for media in roles}
    return {
        "id": capability_id, "name": config.get("name", config.get("mode_name", capability_id)), "type": kind,
        **{key: config[key] for key in ("name_key", "mode_name_key", "model_name_key", "provider_name_key", "description_key") if key in config},
        "category": config.get("category", kind),
        "plugin_id": config.get("plugin_id"), "plugin_version": config.get("plugin_version"),
        "plugin_folder": config.get("plugin_folder"), "collaboration_ui": config.get("collaboration_ui"),
        "parameters": config.get("parameters", {}),
        "prompt_translation_action": config.get("prompt_translation_action"),
        "ui": config.get("ui"),
        "selector_model": config.get("selector_model"), "mode_name": config.get("mode_name"),
        "selector_order": config.get("selector_order", 0),
        "shot_count": len(config.get("shot_nodes", [])),
        "processing_modes": [{key: value for key, value in item.items() if key != "handler"} for item in processing_modes],
        "compiler": config.get("compiler", "builtin"),
        "model": public_model,
        "model_name": config.get("model_name") or config.get("selector_model", {}).get("name") or model,
        "mode": mode,
        "generation_modes": ["direct", "collaborative"] if collaboration_supported else ["direct"],
        "collaboration_supported": collaboration_supported,
        "collaboration_modes": ["quick" if item["id"] == "compile" else item["id"] for item in processing_modes if item["id"] != "direct"],
        "operation": config.get("operation", "generate"), "inputs": limits,
        "input_roles": roles, "variants": [{"id": key, "name": value.get("label", key), "name_key": value.get("label_key", "")} for key, value in variants.items()],
        "models": list(config.get("models", [])), "ratios": declared_options(config, "settings.ratio"), "resolutions": declared_options(config, "settings.resolution"),
        "duration": declared_duration(config),
        "supports_style": kind == "image" and config.get("operation") != "postprocess", "requirements": config.get("requirements", {}),
    }


def validate_duration(value: dict[str, Any], duration: float) -> None:
    limits = value.get("duration")
    if limits and not limits["min"] <= duration <= limits["max"]:
        raise HTTPException(422, f"{value['model'] or value['type']} 时长必须在 {limits['min']}-{limits['max']} 秒之间")


def resolution_pixels(resolution: str) -> int:
    if resolution in RESOLUTIONS:
        return RESOLUTIONS[resolution]
    match = re.fullmatch(r"([0-9]{1,5}(?:\.[0-9]{1,3})?)([PK])", resolution, re.IGNORECASE)
    if match:
        pixels = float(match[1]) * (1024 if match[2].upper() == "K" else 1)
        if 64 <= pixels <= 16384 and pixels.is_integer():
            return int(pixels)
    raise HTTPException(422, f"无效分辨率: {resolution}，请使用 1080P、4K 等格式")


def dimensions(resolution: str, ratio: str, kind: str) -> tuple[int, int]:
    if not re.fullmatch(r"[0-9]{1,5}:[0-9]{1,5}", ratio):
        raise HTTPException(422, f"无效比例: {ratio}，请使用 16:9 等格式")
    value, (rw, rh) = resolution_pixels(resolution), map(int, ratio.split(":"))
    if not rw or not rh:
        raise HTTPException(422, "比例的宽和高必须大于零")
    if kind == "image": return value, round(value * rh / rw)
    if resolution.upper().endswith("K"): return (value, round(value * rh / rw)) if rw >= rh else (round(value * rw / rh), value)
    return (round(value * rw / rh), value) if rw >= rh else (value, round(value * rh / rw))


def named_dimensions(width: int | None, height: int | None, kind: str) -> tuple[str, str]:
    if not width or not height: return "16:9", "720P"
    divisor = math.gcd(width, height)
    ratio = f"{width // divisor}:{height // divisor}"
    for resolution in RESOLUTIONS:
        if dimensions(resolution, ratio, kind) == (width, height):
            return ratio, resolution
    resolution = width if kind == "image" else min(width, height)
    return ratio, f"{resolution}P"


def validate_input_roles(value: dict[str, Any], inputs: list[AssetInput]) -> None:
    for media, allowed in value["input_roles"].items():
        if not allowed: continue
        roles = [item.role for item in inputs if item.type == media]
        unknown = [role for role in roles if role not in allowed]
        if unknown: raise HTTPException(422, f"{media} 素材角色无效: {unknown[0]}，可选: {', '.join(allowed)}")
        if len(roles) != len(set(roles)): raise HTTPException(422, f"{media} 素材角色不能重复")


def voice(item: dict[str, Any]) -> dict[str, Any]:
    return {"id": item["preset_key"], "name": item["display_name"], "plugin_id": item.get("plugin_id"), "instruction": item.get("instruction", ""), "speaker": item.get("speaker", ""), "language": item.get("language", "Chinese"), "model": item.get("model", ""), "sample_url": item.get("sample_audio_url")}
