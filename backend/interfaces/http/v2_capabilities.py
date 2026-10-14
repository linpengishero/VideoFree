from typing import Any

from fastapi import HTTPException

from .v2_schemas import AssetInput


CAPABILITY_LABELS = {
    "image.text_to_image": "Krea2 文生图", "image.image_to_image": "Krea2 图生图",
    "image.character": "Krea2 角色多视图", "image.krea2.text_to_image": "Krea2 文生图",
    "image.krea2.image_to_image": "Krea2 图生图", "image.krea2.character": "Krea2 角色多视图",
    "image.krea2.storyboard_4": "Krea2 四宫格分镜", "image.qwen.text_to_image": "Qwen 文生图",
    "image.qwen.image_to_image": "Qwen 图生图", "image.qwen.character": "Qwen 角色多视图",
    "image.qwen.storyboard_4": "Qwen 四宫格分镜", "image.qwen.storyboard_6": "Qwen 六宫格分镜",
    "image.qwen.scene": "Qwen 场景图", "image.gpt_image.text_to_image": "GPT-Image 文生图",
    "image.gpt_image.image_to_image": "GPT-Image 图生图", "image.gpt_image.character": "GPT-Image 角色版",
    "image.gpt_image.scene": "GPT-Image 场景图", "image.gpt_image.storyboard_4": "GPT-Image 四宫格分镜",
    "image.gpt_image.storyboard_6": "GPT-Image 六宫格分镜", "video.text_to_video": "MiniMax H3 文生视频",
    "video.image_to_video": "MiniMax H3 图生视频", "video.first_last_frame": "MiniMax H3 首尾帧",
    "video.reference": "MiniMax H3 全能参考", "video.ltx2_5.text_to_video": "LTX 2.5 文生视频",
    "video.ltx2_5.image_to_video": "LTX 2.5 图生视频", "video.ltx2_5.first_last_frame": "LTX 2.5 首尾帧",
    "video.ltx2_5.multi_reference": "LTX 2.5 多主体参考", "tts.preset": "预设声音",
    "tts.describe": "声音设计", "music.create": "MiniMax Music 歌曲创作",
    "music.ace_step.background": "ACE-Step 背景配乐",
    "tts.cosyvoice3.preset": "CosyVoice3 预设音色", "tts.cosyvoice3.clone": "CosyVoice3 音色克隆",
    "image.split": "四宫格分割", "image.split_6": "六宫格分割",
}
POST_ACTIONS = {
    "image": {"split": ("四宫格分割", "image.split"), "split_6": ("六宫格分割", "image.split_6"), "krea2_upscale": ("Krea2 高清增强", "image.krea2_upscale")},
    "video": {
        "interpolate": ("视频补帧", "video.interpolate"),
        "upscale": ("LTX 2.5 视频放大", "video.upscale"),
        "lms_enhance": ("LMS 清晰度增强", "video.lms_enhance"),
    },
}
RESOLUTIONS = {"480P": 480, "576P": 576, "720P": 720, "1K": 1024, "1080P": 1080, "1440P": 1440, "2K": 2048}
RATIOS = {"16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "2:3", "3:2"}


def model_and_mode(capability_id: str, config: dict[str, Any]) -> tuple[str, str, str]:
    parts, kind, mode = capability_id.split("."), config["kind"], config["mode"]
    if kind == "image":
        model = parts[1] if len(parts) > 2 and parts[1] in {"krea2", "qwen", "gpt_image"} else "krea2"
    elif kind == "video":
        model = "ltx2_5" if len(parts) > 2 and parts[1] == "ltx2_5" else "minimax"
    elif kind == "tts":
        model = parts[1] if len(parts) > 2 and parts[1] in {"qwen3_tts", "cosyvoice3"} else "qwen3_tts"
    elif kind == "music":
        model = "ace_step" if len(parts) > 2 and parts[1] == "ace_step" else "minimax_music3"
    else:
        model = ""
    return kind, model, mode


def public_model_id(kind: str, model: str) -> str:
    return {("video", "minimax"): "minimax-h3", ("video", "ltx2_5"): "ltx-2.5", ("tts", "qwen3_tts"): "qwen3-tts", ("tts", "cosyvoice3"): "cosyvoice3", ("music", "minimax_music3"): "minimax-music3", ("music", "ace_step"): "ace-step-1.5", ("image", "gpt_image"): "gpt-image"}.get((kind, model), model)


def agent_model_and_mode(kind: str, model_id: str, mode_id: str) -> tuple[str, str] | None:
    model = {"minimax-h3": "minimax-h3", "ltx-2.5": "ltx2_5", "krea2": "krea2", "qwen": "qwen", "minimax-music3": "minimax_music3", "ace-step-1.5": "ace_step"}.get(model_id)
    if not model:
        return None
    mode = "creative" if kind == "music" and mode_id == "create" else mode_id
    supported = {
        "minimax-h3": {"text_to_video", "image_to_video", "first_last_frame", "reference"},
        "ltx2_5": {"text_to_video", "image_to_video", "first_last_frame", "multi_reference"},
        "krea2": {"text_to_image", "image_to_image", "character"},
        "qwen": {"text_to_image", "image_to_image", "character", "scene", "storyboard_4", "storyboard_6"},
        "minimax_music3": {"preset", "creative"},
        "ace_step": {"background"},
    }
    return (model, mode) if mode in supported[model] else None


def capability(capability_id: str, config: dict[str, Any]) -> dict[str, Any]:
    kind, model, mode = model_and_mode(capability_id, config)
    variants = config.get("variants", {})
    public_variant_ids = config.get("public_variants")
    if isinstance(public_variant_ids, list):
        variants = {key: variants[key] for key in public_variant_ids if key in variants}
    roles = {media: [] for media in ("image", "video", "audio")}
    if mode == "first_last_frame": roles["image"] = ["first_frame", "last_frame"]
    elif mode == "image_to_video": roles["image"] = ["first_frame"]
    elif mode == "storyboard_4" and model == "krea2": roles["image"] = ["scene", "character_a", "character_b"]
    elif mode == "multi_reference": roles["image"] = ["subject_1", "subject_2", "subject_3"]
    for media in roles:
        if isinstance(config.get("input_roles", {}).get(media), list): roles[media] = config["input_roles"][media]
    public_model = public_model_id(kind, model)
    collaboration_supported = agent_model_and_mode(kind, public_model, mode) is not None
    references = config.get("references", {})
    limits = {media: {"min": int(references.get(media, {}).get("min", 0)), "max": int(references.get(media, {}).get("max", 0))} for media in roles}
    postprocess_ids = {value[1] for actions in POST_ACTIONS.values() for value in actions.values()}
    return {
        "id": capability_id, "name": CAPABILITY_LABELS.get(capability_id, capability_id), "type": kind,
        "model": public_model, "mode": mode,
        "generation_modes": ["direct", "collaborative"] if collaboration_supported else ["direct"],
        "collaboration_supported": collaboration_supported,
        "collaboration_modes": (["quick", "director"] if public_model == "minimax-h3" else ["director"]) if collaboration_supported else [],
        "operation": "postprocess" if capability_id in postprocess_ids else "generate", "inputs": limits,
        "input_roles": roles, "variants": [{"id": key, "name": value.get("label", key)} for key, value in variants.items()],
        "models": list(config.get("models", [])), "ratios": sorted(RATIOS), "resolutions": list(RESOLUTIONS),
        "duration": ({"min": 1, "max": 15, "default": 5} if kind == "video" and public_model == "minimax-h3" else {"min": 1, "max": 30, "default": 5} if kind == "video" else {"min": 1, "max": 360, "default": 5} if kind == "music" else None),
        "supports_style": kind == "image" and capability_id not in postprocess_ids, "requirements": config.get("requirements", {}),
    }


def validate_duration(value: dict[str, Any], duration: float) -> None:
    limits = value.get("duration")
    if limits and not limits["min"] <= duration <= limits["max"]:
        raise HTTPException(422, f"{value['model'] or value['type']} 时长必须在 {limits['min']}-{limits['max']} 秒之间")


def dimensions(resolution: str, ratio: str, kind: str) -> tuple[int, int]:
    if resolution not in RESOLUTIONS: raise HTTPException(422, f"不支持的分辨率: {resolution}")
    if ratio not in RATIOS: raise HTTPException(422, f"不支持的比例: {ratio}")
    value, (rw, rh) = RESOLUTIONS[resolution], map(int, ratio.split(":"))
    if kind == "image": return value, round(value * rh / rw)
    if value in {1024, 2048}: return (value, round(value * rh / rw)) if rw >= rh else (round(value * rw / rh), value)
    return (round(value * rw / rh), value) if rw >= rh else (value, round(value * rh / rw))


def named_dimensions(width: int | None, height: int | None, kind: str) -> tuple[str, str]:
    if not width or not height: return "16:9", "720P"
    candidates = ((abs(w - width) / width + abs(h - height) / height, ratio, resolution) for ratio in RATIOS for resolution in RESOLUTIONS for w, h in [dimensions(resolution, ratio, kind)])
    _, ratio, resolution = min(candidates)
    return ratio, resolution


def validate_input_roles(value: dict[str, Any], inputs: list[AssetInput]) -> None:
    for media, allowed in value["input_roles"].items():
        if not allowed: continue
        roles = [item.role for item in inputs if item.type == media]
        unknown = [role for role in roles if role not in allowed]
        if unknown: raise HTTPException(422, f"{media} 素材角色无效: {unknown[0]}，可选: {', '.join(allowed)}")
        if len(roles) != len(set(roles)): raise HTTPException(422, f"{media} 素材角色不能重复")


def voice(item: dict[str, Any]) -> dict[str, Any]:
    return {"id": item["preset_key"], "name": item["display_name"], "instruction": item.get("instruction", ""), "speaker": item.get("speaker", ""), "language": item.get("language", "Chinese"), "model": item.get("model", ""), "sample_url": item.get("sample_audio_url")}
