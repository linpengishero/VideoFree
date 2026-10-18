"""Plugin-owned workflow preparation; shared execution stays in the gateway."""

from backend.modules.shared.plugin_runtime import fit_aligned_dimensions



def bind_inputs(workflow, config, prompt, images):
    for node in workflow.values():
        inputs = node.setdefault("inputs", {})
        if not config.get("prompt", {}).get("preserve_all") and node.get("class_type") in {
            "CLIPTextEncode", "easy showAnything", "PrimitiveStringMultiline",
        }:
            for key in ("text", "string", "value"):
                if key in inputs:
                    inputs[key] = prompt
                    break
        if node.get("class_type") == "CreateVideo":
            inputs.update(fps=24, bit_depth=8)
        elif node.get("class_type") == "SaveVideo":
            inputs.setdefault("codec", "auto")
    if images and not config.get("media_bindings", {}).get("image"):
        loaders = [node for node in workflow.values() if node.get("class_type") == "LoadImage"]
        for node, filename in zip(loaders, images):
            node["inputs"]["image"] = filename

def prepare(workflow, config, request, media, job_id, prompt):
    bind_inputs(workflow, config, prompt, media["image"])
    output_prefix = request.params["_output_prefix"]
    ltx_nodes = [node for node in workflow.values() if node.get("class_type") == "EmptyLTXVLatentVideo"]
    if ltx_nodes and config.get("dynamic_ltx_dimensions", True):
        # LTX canvas examples wire dimensions through helper nodes.  API input
        # values may safely replace those links, giving the gateway one stable
        # width/height/duration contract regardless of the canvas layout.
        width, height = fit_aligned_dimensions(
            request.params.get("width", 768), request.params.get("height", 432), 64,
        )
        frames = max(9, 1 + (round(request.duration_seconds * 24) // 8) * 8)
        for node in ltx_nodes:
            # These values are often linked to canvas helper nodes.  A linked
            # socket ignores a replacement widget value in API prompts.
            for key in ("width", "height", "length"):
                node["inputs"].pop(key, None)
            node["inputs"].update(width=width, height=height, length=frames)
        for node in workflow.values():
            if node.get("class_type") == "LTXVEmptyLatentAudio":
                node["inputs"].pop("frames_number", None)
                node["inputs"].pop("frame_rate", None)
                node["inputs"].update(frames_number=frames, frame_rate=24)
            if node.get("class_type") == "VHS_VideoCombine":
                node["inputs"].update(filename_prefix=output_prefix, save_output=True)

