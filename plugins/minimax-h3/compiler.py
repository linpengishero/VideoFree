"""Plugin-owned workflow preparation; shared execution stays in the gateway."""

from backend.modules.shared.plugin_runtime import fit_aligned_dimensions
import hashlib

from .checkpoints import checkpoint_path
from .graph import (
    apply_h3_reference_bindings, configure_h3_lms_guide,
    configure_h3_generation_loras, inject_h3_checkpoint_save, replace_h3_video_savers,
)


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

def prepare(workflow, config, request, media, job_id, prompt, runtime=None):
    archive_job = request.params.get("latent_archive_job")
    if runtime and request.params.get("refine_mode") and archive_job:
        # Each child owns a reference, so deleting its draft cannot lose the latent.
        archived = runtime.link_job_file(archive_job, "native-latent", job_id)
        cached = checkpoint_path(runtime, request.params['latent_checkpoint'])
        matches = False
        if cached:
            try:
                if cached.stat().st_size == archived['size']:
                    digest = hashlib.sha256()
                    with cached.open('rb') as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                            digest.update(chunk)
                    matches = digest.hexdigest() == archived['sha256']
            except OSError:
                pass  # A missing or unreadable worker cache can be restored from the archive.
        if not matches:
            runtime.restore_job_file(job_id, "native-latent",
                                     f"MiniMaxH3/latent_checkpoints/{request.params['latent_checkpoint']}")
        request.params["latent_archive_job"] = job_id
        runtime.update_job_parameters({"id": job_id, "request": request.model_dump()}, request.params)
    uploaded, videos, audios = media["image"], media["video"], media["audio"]
    bind_inputs(workflow, config, prompt, uploaded)
    if config.get("h3_checkpoint_kind"):
        request.params.update(
            h3_checkpoint_kind=config["h3_checkpoint_kind"],
            h3_resume_stage=config.get("h3_resume_stage", config["h3_checkpoint_kind"]),
            h3_resume_step=int(config.get("h3_resume_step", 0)),
            h3_total_steps=int(config.get("h3_total_steps", 0)),
            h3_sigma_schedule_persisted=True,
        )
    frame_nodes = [n for n in workflow.values() if n.get('class_type') == 'MiniMaxH3ImageToVideo']
    for frame_index, frame_node in enumerate(frame_nodes):
        frames = max(5, round(request.duration_seconds * 24))
        width, height = fit_aligned_dimensions(
            request.params.get('width', 768), request.params.get('height', 432), 32,
        )
        dimensions = {'width': width, 'height': height}
        for key, value in dimensions.items():
            frame_node['inputs'][key] = value
        frame_node['inputs']['length'] = frames + (5 - frames % 17) % 17
        for key in ('first_frame', 'last_frame'):
            frame_node['inputs'].pop(key, None)
        for i, filename in enumerate(uploaded):
            node_id = f'gateway_frame_{frame_index}_{i}'
            workflow[node_id] = {'class_type':'LoadImage', 'inputs':{'image':filename}}
            frame_node['inputs'][('first_frame','last_frame')[i]] = [node_id,0]
    apply_h3_reference_bindings(workflow, config, request, uploaded, videos, audios)
    configure_h3_lms_guide(workflow, request)
    configure_h3_generation_loras(workflow, request)
    inject_h3_checkpoint_save(workflow, config, job_id)
    replace_h3_video_savers(workflow)
    for node in workflow.values():
        if node.get("class_type") == "MiniMaxH3NativeLatentCheckpointSaveT8Advanced":
            node["inputs"].update(filename_prefix=job_id, checkpoint_id=job_id)

