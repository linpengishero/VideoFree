"""Qwen reference graph transformation owned by the plugin."""
from typing import Any
from backend.modules.shared.plugin_runtime import GenerateRequest


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
