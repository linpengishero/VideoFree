# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Pure ComfyUI workflow compilation and history helpers."""

import re
import secrets
from typing import Any, Callable
import urllib.error

from ...core.schemas import GenerateRequest


def history_media(outputs: dict[str, Any], preferred_nodes: list[str] | None = None):
    """Yield ComfyUI history media regardless of the output node's media key."""
    ordered = [outputs[node] for node in preferred_nodes or [] if node in outputs]
    for node in ordered if preferred_nodes else outputs.values():
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
    }
    for source, bindings in config.get("parameter_bindings", {}).items():
        for binding in bindings:
            if source in values:
                value = values[source]
            elif source in request.params.get("plugin_parameters", {}):
                value = request.params["plugin_parameters"][source]
            elif source in request.params:
                value = request.params[source]
            elif "default" in binding:
                value = binding["default"]
            else:
                raise ValueError(f"Missing declared plugin parameter: {source}")
            node_id, input_name = str(binding["node"]), binding["input"]
            if node_id not in workflow:
                raise ValueError(f"Parameter binding node {node_id} is missing from {config['file']}")
            workflow[node_id].setdefault("inputs", {})[input_name] = value








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
    multiple = int(config.get("dimension_alignment", 8))
    width, height = fit_aligned_dimensions(requested_width, requested_height, multiple)
    for node in workflow.values():
        class_type = node.get("class_type")
        inputs = node.setdefault("inputs", {})
        if class_type in {"EmptyLatentImage", "EmptySD3LatentImage"}:
            if "width" in inputs:
                inputs["width"] = width
            if "height" in inputs:
                inputs["height"] = height
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
