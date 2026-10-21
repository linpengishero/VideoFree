"""MiniMax-native checkpoint ownership, persistence and recovery."""

import hashlib
import json
import os
from pathlib import Path
import stat

from backend.modules.shared.plugin_runtime import GenerateRequest

DIRECTORY = "MiniMaxH3/latent_checkpoints"


def owns(job):
    request = job.get("request") or {}
    generation = job.get("generation") or request.get("generation") or {}
    identity = generation.get("plugin_id")
    if identity:
        return identity == "minimax-h3"
    # Pre-plugin jobs have only the original model-family identity.
    return job.get("kind") == "video" and request.get("params", {}).get("video_model") == "minimax"


def checkpoint_path(runtime, name):
    if not name or Path(name).name != name or not name.endswith(".h3latent.safetensors"):
        return None
    return runtime.comfyui_output_file(f"{DIRECTORY}/{name}")


def persist(job, request, runtime, *, detect=True):
    matches = runtime.comfyui_output_files(DIRECTORY, f"{job['id']}_*.h3latent.safetensors", detect=detect)
    if not matches:
        raise RuntimeError("H3 初稿完成，但未找到原生 latent 检查点")
    checkpoint = matches[0]
    archived = runtime.save_job_file(job, "native-latent", source=checkpoint,
                                    metadata={"format": "h3latent.safetensors", "version": 1,
                                              "filename": checkpoint.name})
    frames = max(5, round(request.duration_seconds * 24))
    request.params.update(
        latent_checkpoint=checkpoint.name, latent_checkpoint_owner=job["id"],
        latent_archive_job=job["id"],
        latent_sha256=archived["sha256"].upper(), latent_checkpoint_ready=True,
        latent_width=int(request.params.get("width", 768)),
        latent_height=int(request.params.get("height", 432)),
        latent_frames=frames + (5 - frames % 17) % 17, latent_fps=24,
        latent_size=archived["size"],
        h3_checkpoint_kind=str(request.params.get("h3_checkpoint_kind") or "completed_draft_latent"),
        h3_resume_stage=str(request.params.get("h3_resume_stage") or "post_sampling"),
        h3_resume_step=int(request.params.get("h3_resume_step") or 0),
        h3_total_steps=int(request.params.get("h3_total_steps") or 0),
        h3_sigma_schedule_persisted=bool(request.params.get("h3_sigma_schedule_persisted", False)),
        h3_conditioning_cache_key=hashlib.sha256(json.dumps({
            "mode": request.mode, "speed": request.params.get("speed", "normal"),
            "prompt": request.prompt, "width": request.params.get("width"),
            "height": request.params.get("height"), "duration": request.duration_seconds,
        }, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
    )
    runtime.update_job_parameters(job, request.params, latent_checkpoint_ready=True, latent_checkpoint_warning=None)


def completed(event, runtime):
    if not event["config"].get("save_h3_latent"):
        return
    request = event["request"]
    try:
        persist(event["job"], request, runtime)
    except Exception as exc:
        request.params["latent_checkpoint_ready"] = False
        runtime.update_job_parameters(event["job"], request.params,
                                      latent_checkpoint_ready=False, latent_checkpoint_warning=str(exc))
    finally:
        runtime.free_comfyui_memory()


def recover(event, runtime):
    for job in runtime.jobs():
        params = (job.get("request") or {}).get("params", {})
        if not owns(job) or job.get("status") != "completed" or params.get("latent_archive_job"):
            continue
        if params.get("parent_job_id") or job.get("parent_job_id") or params.get("refine_mode"):
            continue
        try:
            persist(job, GenerateRequest(**runtime.job_request(job)), runtime, detect=False)
        except (OSError, RuntimeError, ValueError, TypeError, KeyError):
            continue


def delete(event, runtime):
    job = event["job"]
    if not owns(job):
        return
    params = (job.get("request") or {}).get("params", {})
    name = str(params.get("latent_checkpoint", ""))
    owner = params.get("latent_checkpoint_owner")
    if owner and owner != job["id"]:
        return
    if not owner and (job.get("parent_job_id") or params.get("refine_mode")):
        return
    # Protect queued children even if ComfyUI's cache was already removed.
    for other in runtime.jobs():
        other_params = (other.get("request") or {}).get("params", {})
        if (other["id"] != job["id"] and other.get("status") in {"queued", "running"}
                and name and other_params.get("latent_checkpoint") == name):
            raise RuntimeError("H3 检查点仍被运行中的二采任务引用")
    path = checkpoint_path(runtime, name)
    if path:
        try:
            path.unlink()
        except PermissionError:
            # Windows may preserve a read-only bit on files copied from ComfyUI.
            # Clear it once before handing the failure to the framework's
            # recoverable cleanup path.
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            path.unlink()
