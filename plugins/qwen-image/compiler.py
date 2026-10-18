"""Plugin-owned workflow preparation; shared execution stays in the gateway."""

from backend.modules.shared.plugin_runtime import apply_image_dimensions, apply_storyboard_grid
from .graph import configure_qwen_image21_references


def prepare(workflow, config, request, media, job_id, prompt):
    apply_image_dimensions(workflow, {**config, "dimension_alignment": 32}, request)
    for node in workflow.values():
        if node.get("class_type") == "TextEncodeQwenImage21" and "resolution" in node.get("inputs", {}):
            # Derive the encoder target from the actual latent canvas.
            node["inputs"]["resolution"] = 0
    configure_qwen_image21_references(workflow, config, request, media["image"])
    apply_storyboard_grid(workflow, config, request.params.get("width", 1024), request.params.get("height", 1024))

