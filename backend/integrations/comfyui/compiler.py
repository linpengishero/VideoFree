"""Pure ComfyUI workflow compilation and history helpers."""

import re
import secrets
from typing import Any, Callable
import urllib.error

from ...modules.shared.schemas import GenerateRequest


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

def history_media(outputs: dict[str, Any], preferred_nodes: list[str] | None = None):
    """Yield ComfyUI history media regardless of the output node's media key."""
    ordered = [outputs[node] for node in preferred_nodes or [] if node in outputs]
    for node in ordered or outputs.values():
        for media_key in ("images", "gifs", "audio", "videos"):
            for value in node.get(media_key, []):
                if value.get("filename"):
                    yield media_key, value


def history_is_complete(status: dict[str, Any], outputs: dict[str, Any]) -> bool:
    """Handle the completion shapes used by different ComfyUI releases.

    LTX workflows can expose an output entry before the final boolean is
    updated.  Conversely, some builds emit ``execution_success`` while the
    legacy ``completed`` field remains false.  Treat the explicit success
    message as authoritative, but never infer success from output files alone.
    """
    status_name = str(status.get("status_str", "")).lower()
    if status.get("completed") is True or status_name in {"success", "completed"}:
        return True
    messages = status.get("messages", [])
    for message in messages:
        if not isinstance(message, (list, tuple)) or not message:
            continue
        event = str(message[0]).lower()
        if event in {"execution_success", "execution_complete", "execution_completed"}:
            return True
    return False


def comfy_queue_contains(queue_state: dict[str, Any], prompt_id: str) -> bool:
    for key in ("queue_running", "queue_pending"):
        for item in queue_state.get(key, []):
            if isinstance(item, (list, tuple)) and len(item) > 1 and str(item[1]) == prompt_id:
                return True
            if isinstance(item, dict) and str(item.get("prompt_id", "")) == prompt_id:
                return True
    return False


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


def validate_reference_counts(config: dict[str, Any], images: int, videos: int, audios: int) -> None:
    supplied = {"image": images, "video": videos, "audio": audios}
    labels = {"image": "参考图", "video": "参考视频", "audio": "参考音频"}
    for media_type, count in supplied.items():
        limits = config.get("references", {}).get(media_type, {"min": 0, "max": 0})
        minimum, maximum = int(limits.get("min", 0)), int(limits.get("max", 0))
        if count < minimum or count > maximum:
            raise ValueError(f"{config['mode']} 需要 {minimum}-{maximum} 个{labels[media_type]}，当前为 {count}")


def replace_prompt(value: Any, prompt: str) -> Any:
    if isinstance(value, str):
        return value.replace("{{prompt}}", prompt)
    if isinstance(value, list):
        return [replace_prompt(v, prompt) for v in value]
    if isinstance(value, dict):
        return {k: replace_prompt(v, prompt) for k, v in value.items()}
    return value


def apply_media_bindings(workflow: dict[str, Any], config: dict[str, Any], media: dict[str, list[str]]) -> None:
    """Bind uploaded files using registry metadata, keeping node details out of request logic."""
    for media_type, bindings in config.get("media_bindings", {}).items():
        values = media.get(media_type, [])
        for binding_index, binding in enumerate(bindings):
            source_index = int(binding.get("source_index", binding_index))
            if source_index >= len(values):
                continue
            node_id, input_name = str(binding["node"]), binding["input"]
            if node_id not in workflow:
                raise ValueError(f"Media binding node {node_id} is missing from {config['file']}")
            if binding.get("connect"):
                loader_id = f"gateway_{media_type}_{source_index}"
                loader_type = {"image": "LoadImage", "video": "VHS_LoadVideo", "audio": "LoadAudio"}[media_type]
                loader_inputs = {"image": values[source_index]} if media_type == "image" else {"audio": values[source_index]} if media_type == "audio" else {
                    "video": values[source_index], "force_rate": 0, "custom_width": 0, "custom_height": 0,
                    "frame_load_cap": 0, "skip_first_frames": 0, "select_every_nth": 1,
                }
                workflow[loader_id] = {"class_type": loader_type, "inputs": loader_inputs}
                workflow[node_id].setdefault("inputs", {})[input_name] = [loader_id, int(binding.get("output", 0))]
            else:
                workflow[node_id].setdefault("inputs", {})[input_name] = values[source_index]


def configure_qwen_image21_references(
    workflow: dict[str, Any],
    config: dict[str, Any],
    request: GenerateRequest,
    images: list[str],
) -> None:
    """Bind up to eight optional references to the shared Qwen-Image 2.1 graph."""
    if not config.get("qwen_image21_multi_reference"):
        return
    encoder = next((
        node for node in workflow.values()
        if isinstance(node, dict) and node.get("class_type") == "TextEncodeQwenImage21"
    ), None)
    sampler = next((
        node for node in workflow.values()
        if isinstance(node, dict) and node.get("class_type") == "KSampler"
    ), None)
    if encoder is None or sampler is None:
        raise ValueError("Qwen-Image 2.1 工作流缺少编码或采样节点")
    inputs = encoder.setdefault("inputs", {})
    for key in list(inputs):
        if key.startswith("images.image_"):
            inputs.pop(key)
    for index, filename in enumerate(images[:8], 1):
        node_id = f"gateway_qwen21_image_{index}"
        workflow[node_id] = {"class_type": "LoadImage", "inputs": {"image": filename}}
        inputs[f"images.image_{index}"] = [node_id, 0]
    empty_latent = next((
        node_id for node_id, node in workflow.items()
        if isinstance(node, dict) and node.get("class_type") == "EmptyLatentImage"
    ), None)
    if not empty_latent:
        raise ValueError("Qwen-Image 2.1 工作流缺少空 latent 节点")
    sampler.setdefault("inputs", {})["latent_image"] = (
        [next(node_id for node_id, node in workflow.items() if node is encoder), 2]
        if request.mode == "image_to_image" and images
        else [empty_latent, 0]
    )


def prune_workflow(workflow: dict[str, Any], output_nodes: list[str]) -> None:
    """Keep only nodes needed by the registered final outputs."""
    needed = set(map(str, output_nodes))
    pending = list(needed)
    while pending:
        node = workflow.get(pending.pop())
        if not node:
            continue
        for value in node.get("inputs", {}).values():
            if isinstance(value, list) and len(value) == 2:
                dependency = str(value[0])
                if dependency not in needed:
                    needed.add(dependency)
                    pending.append(dependency)
    for node_id in list(workflow):
        if node_id not in needed:
            workflow.pop(node_id)


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


def apply_parameter_bindings(workflow: dict[str, Any], config: dict[str, Any], request: GenerateRequest) -> None:
    requested_seed = request.params.get("seed")
    seed = int(requested_seed) if requested_seed is not None else secrets.randbelow(2**48)
    request.params["seed"] = seed
    values = {
        "width": int(request.params.get("width", 768)),
        "height": int(request.params.get("height", 432)),
        "duration": float(request.duration_seconds),
        "fps": int(request.params.get("fps", 24)),
        "seed": seed,
        "latent_checkpoint": str(request.params.get("latent_checkpoint", "")),
        "latent_sha256": str(request.params.get("latent_sha256", "")),
        "music_bpm": int(request.params.get("music_bpm", 120)),
        "music_key": str(request.params.get("music_key", "C minor")),
        "music_timesignature": str(request.params.get("music_timesignature", "4")),
    }
    for source, bindings in config.get("parameter_bindings", {}).items():
        for binding in bindings:
            node_id, input_name = str(binding["node"]), binding["input"]
            if node_id not in workflow:
                raise ValueError(f"Parameter binding node {node_id} is missing from {config['file']}")
            workflow[node_id].setdefault("inputs", {})[input_name] = values[source]


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


def configure_h3_latent_upscaler(workflow: dict[str, Any], request: GenerateRequest, comfy_request: Callable[..., Any]) -> None:
    """Switch the refinement graph to the installed learned upscaler when available."""
    if request.params.get("speed") not in {
        "latent_refine", "staged_refine", "preview_refine_fast", "preview_refine_stable", "latent_ultra_refine"
    }:
        return
    node = next((item for item in workflow.values()
                 if item.get("class_type") == "MiniMaxH3LearnedLatentUpscaleT8Advanced"), None)
    if not node:
        return
    backend = str(request.params.get("latent_upscaler", "3d")).lower()
    class_name = "MinimaxH3LatentUpscalerNode2D" if backend == "2d" else "MinimaxH3LatentUpscaler3D"
    try:
        available = comfy_request("/object_info/" + urllib.parse.quote(class_name, safe=""))
    except Exception:
        available = {}
    if not available:
        return
    source = node["inputs"].get("av_latent") or node["inputs"].get("latent")
    if not source:
        return
    source_width = max(1, int(request.params.get("latent_width") or request.params.get("width") or 768))
    source_height = max(1, int(request.params.get("latent_height") or request.params.get("height") or 432))
    target_width = max(source_width, int(request.params.get("width") or source_width))
    target_height = max(source_height, int(request.params.get("height") or source_height))
    scale = max(target_width / source_width, target_height / source_height)
    separate_id = "gateway_h3_separate_av"
    concat_id = "gateway_h3_concat_av"
    workflow[separate_id] = {
        "class_type": "LTXVSeparateAVLatent",
        "inputs": {"av_latent": source},
    }
    video_source = [separate_id, 0]
    node["class_type"] = class_name
    if backend == "2d":
        node["inputs"] = {
            "latent": video_source,
            "model_name": "minimax_h3_latent_upscaler_3d_fp16.safetensors",
            "scale": round(max(1.0, min(4.0, scale)), 3),
            "device": "cuda",
            "precision": "fp16",
        }
    else:
        node["inputs"] = {
            "latent": video_source,
            "model_name": "minimax_h3_latent_upscaler_3d_fp16.safetensors",
            "mode": "target dimensions",
            "mode.width": target_width,
            "mode.height": target_height,
            "align": 32,
            "enable_temporal_chunking": True,
            "force_unload": True,
            "device": "cuda",
            "precision": "fp16",
        }
    workflow[concat_id] = {
        "class_type": "LTXVConcatAVLatent",
        "inputs": {"video_latent": [next(key for key, value in workflow.items() if value is node), 0],
                   "audio_latent": [separate_id, 1]},
    }
    reconcile = next((item for item in workflow.values()
                      if item.get("class_type") == "MiniMaxH3TwoPassLatentReconcileT8Advanced"), None)
    if reconcile:
        reconcile["inputs"]["learned_latent"] = [concat_id, 0]
    conditioning = next((item for item in workflow.values()
                         if item.get("class_type") in {"MiniMaxH3ReferenceToVideo", "MiniMaxH3ImageToVideo"}), None)
    if conditioning:
        conditioning["inputs"]["width"] = target_width
        conditioning["inputs"]["height"] = target_height


def fit_aligned_dimensions(width: Any, height: Any, multiple: int) -> tuple[int, int]:
    """Find nearby legal dimensions while minimizing aspect and size drift together."""
    target_width, target_height = max(multiple, int(width)), max(multiple, int(height))
    ratio = target_width / target_height
    center_width = max(1, round(target_width / multiple))
    center_height = max(1, round(target_height / multiple))
    candidates = (
        (w * multiple, h * multiple)
        for w in range(max(1, center_width - 4), center_width + 5)
        for h in range(max(1, center_height - 4), center_height + 5)
    )
    return min(candidates, key=lambda size: (
        abs(size[0] / size[1] - ratio) / ratio
        + 0.25 * ((abs(size[0] - target_width) / target_width + abs(size[1] - target_height) / target_height) / 2)
    ))


def apply_image_dimensions(workflow: dict[str, Any], config: dict[str, Any], request: GenerateRequest) -> None:
    """Apply the UI canvas to common image-generation nodes by node contract."""
    if config.get("prune_to_outputs"):
        return
    requested_width = max(64, int(request.params.get("width", 1024)))
    requested_height = max(64, int(request.params.get("height", 1024)))
    is_qwen_image21 = any(
        isinstance(node, dict) and node.get("class_type") == "TextEncodeQwenImage21"
        for node in workflow.values()
    )
    multiple = 32 if is_qwen_image21 else 8
    width, height = fit_aligned_dimensions(requested_width, requested_height, multiple)
    for node in workflow.values():
        class_type = node.get("class_type")
        inputs = node.setdefault("inputs", {})
        if class_type in {"EmptyLatentImage", "EmptySD3LatentImage"}:
            if "width" in inputs:
                inputs["width"] = width
            if "height" in inputs:
                inputs["height"] = height
        elif class_type == "TextEncodeQwenImage21":
            # Let the encoder derive its target from the actual latent canvas.
            # A hard-coded 1024 here degrades non-square and higher-resolution jobs.
            if "resolution" in inputs:
                inputs["resolution"] = 0
        elif class_type == "LayerUtility: ImageScaleByAspectRatio V2":
            # This node can produce an exact canvas without relying on the
            # source image's original aspect ratio.
            inputs.update(
                aspect_ratio="custom",
                proportional_width=width,
                proportional_height=height,
                scale_to_side="width",
                scale_to_length=width,
                round_to_multiple="None",
            )
        elif class_type == "Grsai_GPTImage":
            ratios = {
                "1:1": "1024x1024 (1:1)", "16:9": "1672x941 (16:9)",
                "9:16": "941x1672 (9:16)", "4:3": "1443x1090 (4:3)",
                "3:4": "1090x1443 (3:4)", "3:2": "1536x1024 (3:2)",
                "2:3": "1024x1536 (2:3)", "21:9": "1920x832 (21:9)",
            }
            ratio = min(ratios, key=lambda value: abs(width / height - int(value.split(":")[0]) / int(value.split(":")[1])))
            inputs["aspect_ratio"] = ratios[ratio]


def apply_input_overrides(workflow: dict[str, Any], config: dict[str, Any]) -> None:
    """Apply environment-specific values declared alongside one workflow."""
    for override in config.get("input_overrides", []):
        node_id = str(override["node"])
        if node_id not in workflow:
            raise ValueError(f"Override node {node_id} is missing from {config['file']}")
        workflow[node_id].setdefault("inputs", {})[override["input"]] = override["value"]


def apply_storyboard_grid(workflow: dict[str, Any], config: dict[str, Any], width: int, height: int) -> None:
    grid = config.get("storyboard_grid")
    if not grid:
        return
    width = max(64, round(int(width) / 8) * 8)
    height = max(64, round(int(height) / 8) * 8)
    gap = max(0, int(grid.get("gap", 0)))
    canvas = workflow.get(str(grid.get("canvas_node")))
    if not canvas:
        raise ValueError(f"Storyboard canvas node is missing from {config['file']}")
    canvas["inputs"].update(width=width * 2 + gap, height=height * 2 + gap)
    for placement in grid.get("placements", []):
        node = workflow.get(str(placement.get("node")))
        if not node:
            raise ValueError(f"Storyboard placement node is missing from {config['file']}")
        node["inputs"].update(
            x=int(placement.get("column", 0)) * (width + gap),
            y=int(placement.get("row", 0)) * (height + gap),
        )
