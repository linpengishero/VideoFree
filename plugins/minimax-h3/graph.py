"""MiniMax H3 graph transformations owned by the plugin."""
import re
import secrets
from typing import Any
from backend.modules.shared.plugin_runtime import GenerateRequest
from backend.modules.shared.plugin_runtime import fit_aligned_dimensions


H3_LORA_CAPABILITIES = {
    "wushu": {
        "node_id": "gateway_h3_wushu_lora",
        "filename": "wushu_spatial_physics_v2_1000_pruned.safetensors",
        "strength": 0.5,
    },
    "cinemagrade": {
        "node_id": "gateway_h3_cinemagrade_lora",
        "filename": "cinemagrade_style_h3_ep50.safetensors",
        "strength": 0.5,
        "trigger": "cinemagradestyle",
    },
    "crash_zoom": {
        "node_id": "gateway_h3_crash_zoom_lora",
        "filename": "Crash_Zoom_MinimaxH3_v1.safetensors",
        "strength": 0.8,
        "trigger": "crash_zm",
    },
    "lms_sharpness": {
        "node_id": "gateway_h3_lms_lora",
        "filename": "minimax_h3_lms_v1.0_r64.safetensors",
        "strength": 0.75,
    },
}


def _prepend_h3_prompt_triggers(workflow: dict[str, Any], triggers: list[str]) -> None:
    triggers = list(dict.fromkeys(trigger for trigger in triggers if trigger))
    if not triggers:
        return
    for node in workflow.values():
        if not isinstance(node, dict) or node.get("class_type") != "PrimitiveStringMultiline":
            continue
        value = str(node.get("inputs", {}).get("value", ""))
        missing = [trigger for trigger in triggers if trigger.lower() not in value.lower()]
        if missing:
            node.setdefault("inputs", {})["value"] = f"{' '.join(missing)}. {value}".strip()


def configure_h3_lms_guide(workflow: dict[str, Any], request: GenerateRequest) -> None:
    """Anchor the source video when the Ref2VA LMS enhancement mode is selected."""
    if request.mode != "lms_enhance":
        return
    h3_id = next((node_id for node_id, node in workflow.items()
                  if isinstance(node, dict) and node.get("class_type") == "MiniMaxH3ReferenceToVideo"), None)
    video_id = next((node_id for node_id, node in workflow.items()
                     if isinstance(node, dict) and node.get("class_type") in {"VHS_LoadVideo", "VHS_LoadVideoPath"}
                     and str(node_id).startswith("gateway_video_")), None)
    guider = next((node for node in workflow.values()
                   if isinstance(node, dict) and node.get("class_type") == "BasicGuider"), None)
    video_vae_id = next((node_id for node_id, node in workflow.items()
                         if isinstance(node, dict) and node.get("class_type") == "VAELoader"
                         and "video_vae" in str(node.get("inputs", {}).get("vae_name", ""))), None)
    audio_vae_id = next((node_id for node_id, node in workflow.items()
                         if isinstance(node, dict) and node.get("class_type") == "VAELoader"
                         and "audio_vae" in str(node.get("inputs", {}).get("vae_name", ""))), None)
    if not all((h3_id, video_id, guider, video_vae_id, audio_vae_id)):
        raise ValueError("LMS 清晰度增强需要一个有效的 Ref2VA 视频输入")
    workflow["gateway_h3_lms_guide"] = {
        "class_type": "MiniMaxH3AddGuide",
        "inputs": {
            "positive": [h3_id, 0],
            "latent": [h3_id, 1],
            "frame_idx": 0,
            "vae": [video_vae_id, 0],
            "audio_vae": [audio_vae_id, 0],
            "image": [video_id, 0],
            "audio": [video_id, 2],
        },
    }
    guider.setdefault("inputs", {})["conditioning"] = ["gateway_h3_lms_guide", 0]


def drop_template_media_loaders(workflow: dict[str, Any]) -> None:
    """Remove example assets exported with a workflow before API injection.

    Canvas exports often include disconnected LoadImage/LoadAudio examples.
    ComfyUI validates those nodes too, even when the gateway has replaced all
    reference inputs with the request's own uploads.
    """
    template_ids = {
        node_id for node_id, node in workflow.items()
        if node.get("class_type") in {"LoadImage", "LoadAudio", "VHS_LoadVideo", "VHS_LoadVideoPath"}
        and not str(node_id).startswith("gateway_")
    }
    for node_id in template_ids:
        workflow.pop(node_id, None)
    for node in workflow.values():
        for key, value in list(node.get("inputs", {}).items()):
            if isinstance(value, list) and len(value) == 2 and str(value[0]) in template_ids:
                node["inputs"].pop(key)


def apply_h3_reference_bindings(
    workflow: dict[str, Any],
    config: dict[str, Any],
    request: GenerateRequest,
    images: list[str],
    videos: list[str],
    audios: list[str],
) -> int:
    """Replace canvas examples with request media on every H3 reference node."""
    h3_nodes = [node for node in workflow.values() if node.get("class_type") == "MiniMaxH3ReferenceToVideo"]
    if not h3_nodes:
        return 0
    drop_template_media_loaders(workflow)
    for h3_index, h3 in enumerate(h3_nodes):
        width, height = fit_aligned_dimensions(
            request.params.get("width", 768), request.params.get("height", 432), 32,
        )
        dimensions = {"width": width, "height": height}
        for key, value in dimensions.items():
            if not config.get("preserve_h3_dimension_links") or not isinstance(h3["inputs"].get(key), list):
                h3["inputs"][key] = value
        frames = max(5, round(request.duration_seconds * 24))
        h3["inputs"].update(
            length=frames + (5 - frames % 17) % 17,
            ref_image_size=request.params.get("ref_image_size", "match"),
        )
        for key in list(h3["inputs"]):
            if key.startswith(("ref_images.", "ref_videos.", "ref_video_audios.", "ref_audios.")):
                h3["inputs"].pop(key, None)
        media_groups = (
            ("image", images[:9], "LoadImage", "ref_images.ref_image_", lambda value: {"image": value}),
            (
                "video", videos[:3], "VHS_LoadVideo", "ref_videos.ref_video_",
                lambda value: {
                    "video": value, "force_rate": 0, "custom_width": 0, "custom_height": 0,
                    "frame_load_cap": 0, "skip_first_frames": 0, "select_every_nth": 1,
                },
            ),
            ("audio", audios[:3], "LoadAudio", "ref_audios.ref_audio_", lambda value: {"audio": value}),
        )
        for media_type, values, loader_type, input_prefix, loader_inputs in media_groups:
            for index, value in enumerate(values):
                node_id = f"gateway_{media_type}_{h3_index}_{index}"
                workflow[node_id] = {"class_type": loader_type, "inputs": loader_inputs(value)}
                h3["inputs"][f"{input_prefix}{index}"] = [node_id, 0]
    return len(h3_nodes)


def replace_h3_video_savers(workflow: dict[str, Any]) -> int:
    """Use VHS/FFmpeg for H3 video encoding instead of PyAV/libx264."""
    if not any(
        isinstance(node, dict)
        and str(node.get("class_type", "")).startswith("MiniMaxH3")
        for node in workflow.values()
    ):
        return 0

    replaced = 0
    removable: set[str] = set()
    for node_id, saver in list(workflow.items()):
        if not isinstance(saver, dict) or saver.get("class_type") != "SaveVideo":
            continue
        video_ref = saver.get("inputs", {}).get("video")
        if not isinstance(video_ref, list) or len(video_ref) != 2:
            continue
        create_id = str(video_ref[0])
        create = workflow.get(create_id)
        if not isinstance(create, dict) or create.get("class_type") != "CreateVideo":
            continue
        create_inputs = create.get("inputs", {})
        images = create_inputs.get("images")
        if not isinstance(images, list) or len(images) != 2:
            continue
        frame_rate = create_inputs.get("fps", 24)
        if isinstance(frame_rate, bool) or not isinstance(frame_rate, (int, float)):
            frame_rate = 24
        inputs: dict[str, Any] = {
            "images": images,
            "frame_rate": max(1, int(frame_rate)),
            "loop_count": 0,
            "filename_prefix": saver.get("inputs", {}).get("filename_prefix", "MediaGateway/video"),
            "format": "video/nvenc_h264-mp4",
            "pingpong": False,
            "save_output": True,
            "pix_fmt": "yuv420p",
            "bitrate": 15,
            "megabit": True,
            "save_metadata": True,
        }
        audio = create_inputs.get("audio")
        if isinstance(audio, list) and len(audio) == 2:
            inputs["audio"] = audio
        workflow[node_id] = {"class_type": "VHS_VideoCombine", "inputs": inputs}
        replaced += 1
        still_referenced = any(
            isinstance(other, dict)
            and any(
                isinstance(value, list) and len(value) == 2 and str(value[0]) == create_id
                for value in other.get("inputs", {}).values()
            )
            for other_id, other in workflow.items()
            if str(other_id) != str(node_id)
        )
        if not still_referenced:
            removable.add(create_id)

    for node_id in removable:
        workflow.pop(node_id, None)
    return replaced


def inject_h3_checkpoint_save(workflow: dict[str, Any], config: dict[str, Any], job_id: str) -> None:
    source = config.get("save_h3_latent")
    if not isinstance(source, dict):
        return
    node_id = str(source.get("node", ""))
    if node_id not in workflow:
        raise ValueError(f"H3 latent source node {node_id} is missing from {config['file']}")
    output = int(source.get("output", 0))
    workflow["gateway_h3_latent_clean"] = {
        "class_type": "RemoveNoiseMask",
        "inputs": {"samples": [node_id, output]},
    }
    workflow["gateway_h3_latent_save"] = {
        "class_type": "MiniMaxH3NativeLatentCheckpointSaveT8Advanced",
        "inputs": {
            "confirm_save": True,
            "filename_prefix": job_id,
            "checkpoint_id": job_id,
            "verify_after_write": True,
            "av_latent": ["gateway_h3_latent_clean", 0],
            "hash_chunk_megabytes": 8,
        },
    }


def configure_h3_generation_loras(workflow: dict[str, Any], request: GenerateRequest) -> None:
    """Apply registered H3 LoRAs selected by recipe, director capability, or user override."""
    if request.params.get("video_model", "minimax") not in {"", "minimax", "minimax-h3"}:
        return
    nodes = [node for node in workflow.values() if isinstance(node, dict)]
    guiders = [node for node in nodes if node.get("class_type") == "BasicGuider"]
    if not guiders or not isinstance(guiders[0].get("inputs", {}).get("model"), list):
        return

    speed = str(request.params.get("speed", ""))
    skills = request.params.get("director_skills", [])
    prompt = request.prompt.lower()
    martial = bool(request.params.get("martial_arts_required")) or (
        isinstance(skills, list) and "martial-arts-combat" in skills
    ) or bool(re.search(r"中国武术|中国功夫|武侠|功夫|武术|咏春|太极|八极|wushu|kung.?fu|chinese martial", prompt))
    camera_lora = str(request.params.get("h3_camera_lora", "auto")).lower()
    crash_zoom = camera_lora == "crash_zoom" or (
        camera_lora == "auto" and bool(re.search(
            r"crash[_ -]?zoom|撞击式变焦|急速变焦|猛烈变焦|瞬间(?:推近|拉近|冲向)|"
            r"(?:abrupt|aggressive|rapid|sudden)\w*(?:\s+\w+){0,3}\s+zoom",
            prompt,
        ))
    )
    cinemagrade = str(request.params.get("h3_style_lora", "")).lower() == "cinemagrade"
    lms_sharpness = request.mode == "lms_enhance" or bool(request.params.get("h3_lms_enhance"))
    recipes: list[tuple[str, str, float]] = []
    triggers: list[str] = []
    if speed in {"quick_preview", "staged_refine"}:
        recipes.append(("gateway_h3_turbo_lora", "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors", 1.0))
        recipes.append(("gateway_h3_mystic_lora", "MysticXXX_MMH3-V1.safetensors", 0.5))
    for enabled, capability in (
        (martial, "wushu"),
        (cinemagrade, "cinemagrade"),
        (crash_zoom, "crash_zoom"),
        (lms_sharpness, "lms_sharpness"),
    ):
        if not enabled:
            continue
        spec = H3_LORA_CAPABILITIES[capability]
        recipes.append((spec["node_id"], spec["filename"], float(spec["strength"])))
        if spec.get("trigger"):
            triggers.append(str(spec["trigger"]))
    if not recipes:
        return

    model = guiders[0]["inputs"]["model"]
    for node_id, filename, strength in recipes:
        workflow[node_id] = {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"model": model, "lora_name": filename, "strength_model": strength},
        }
        model = [node_id, 0]
    for node in nodes:
        if node.get("class_type") in {"BasicGuider", "BasicScheduler"}:
            node.setdefault("inputs", {})["model"] = model
    _prepend_h3_prompt_triggers(workflow, triggers)


