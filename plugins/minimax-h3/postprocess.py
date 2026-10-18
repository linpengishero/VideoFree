"""MiniMax latent postprocessing plugin actions."""

from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from backend.modules.shared.plugin_runtime import GenerateRequest, PluginError
from .checkpoints import checkpoint_path, owns


class RefineRequest(BaseModel):
    mode: str = Field(pattern="^(h3_refine|preview_refine_fast|preview_refine_stable|ltx_ultra)$")
    width: int = Field(ge=64, le=4096)
    height: int = Field(ge=64, le=4096)


def availability(action_request, runtime):
    source = action_request["source"]
    if source.get("external") or not owns(source):
        return {"available": False, "reason": "此二采仅支持 MiniMax H3 原生初稿，不支持其他模型视频"}
    params = (source.get("request") or {}).get("params", {})
    if not params.get("latent_checkpoint_ready"):
        return {"available": False, "reason": "该初稿没有可用的 H3 原生检查点"}
    if not params.get("latent_checkpoint"):
        return {"available": False, "reason": "该初稿缺少 H3 原生检查点记录"}
    return {"available": True}


def validate_refine_dimensions(params: dict[str, Any], request: RefineRequest) -> None:
    source_width = int(params.get("latent_width") or params.get("width") or 0)
    source_height = int(params.get("latent_height") or params.get("height") or 0)
    if not source_width or not source_height:
        raise PluginError(409, "初稿缺少 latent 尺寸信息，无法二采")
    source_ratio = source_width / source_height
    if abs(request.width / request.height - source_ratio) / source_ratio > 0.03:
        raise PluginError(422, "二采分辨率必须保持初稿画幅比例")
    if request.width < source_width or request.height < source_height:
        raise PluginError(422, "二采分辨率不能低于初稿")
    if request.mode in {"h3_refine", "preview_refine_fast", "preview_refine_stable"} and min(request.width, request.height) > 768:
        raise PluginError(422, "H3 高清二采短边最高支持 768；更高分辨率请使用 LTX 2.5 超清二采")


def prepare(action_request, runtime):
    source = action_request["source"]
    eligibility = availability(action_request, runtime)
    if not eligibility["available"]:
        raise PluginError(409, eligibility["reason"])
    options = {**action_request["inputs"], "mode": action_request["action"]["id"]}
    refine = RefineRequest(**options)
    job_id = source["id"]
    request = runtime.job_request(source)
    # Refinement always executes the H3 reference workflow, regardless of the
    # source draft's original generation mode (text-to-video, image-to-video,
    # or reference).
    request["mode"] = "reference"
    params = dict(request.get("params") or {})
    if source.get("kind") != "video" or source.get("status") != "completed":
        raise PluginError(409, "只有已完成的视频初稿可以二采")
    if not params.get("latent_checkpoint_ready"):
        raise PluginError(409, "该任务没有可用的 H3 原生 latent")
    checkpoint_name = str(params.get("latent_checkpoint", ""))
    checkpoint = checkpoint_path(runtime, checkpoint_name)
    if not checkpoint:
        raise PluginError(409, "H3 原生 latent 已不存在，请重新生成初稿")
    validate_refine_dimensions(params, refine)
    checkpoint_kind = str(params.get("h3_checkpoint_kind") or "completed_draft_latent")
    # The public H3 action selects the workflow from the native checkpoint format.
    if (refine.mode == "h3_refine" and params.get("speed") == "preview"
            and checkpoint_kind not in {"sigma_intermediate", "denoised_preview_latent"}):
        refine = refine.model_copy(update={"mode": "preview_refine_stable"})
    if refine.mode in {"preview_refine_fast", "preview_refine_stable"} and params.get("speed") != "preview":
        raise PluginError(409, "极速预览专用二采只能用于4步极速预览初稿")
    variant = (
        "staged_refine" if refine.mode == "h3_refine" and checkpoint_kind in {"sigma_intermediate", "denoised_preview_latent"}
        else refine.mode if refine.mode in {"preview_refine_fast", "preview_refine_stable"}
        else "latent_refine" if refine.mode == "h3_refine"
        else "latent_ultra_refine"
    )
    for child in runtime.jobs():
        child_params = (child.get("request") or {}).get("params", {})
        if (
            child.get("parent_job_id") == job_id
            and child_params.get("speed") == variant
            and int(child_params.get("width", 0)) == refine.width
            and int(child_params.get("height", 0)) == refine.height
            and child.get("status") in {"queued", "running"}
        ):
            raise PluginError(409, "相同规格的二采任务正在运行")

    params.update(
        speed=variant,
        refine_mode=refine.mode,
        width=refine.width,
        height=refine.height,
        parent_job_id=job_id,
        latent_checkpoint_owner=str(params.get("latent_checkpoint_owner") or job_id),
        latent_checkpoint_ready=False,
        h3_checkpoint_kind="completed_draft_latent",
        h3_resume_stage="post_sampling",
        h3_resume_step=0,
        h3_total_steps=0,
        h3_sigma_schedule_persisted=False,
    )
    artifacts = source.get("artifacts") or []
    artifact_name = next((item.get("name") for item in artifacts if item.get("name")), "")
    if not artifact_name:
        raise PluginError(409, "初稿缺少可用视频产物，无法二采")
    # The parent task package resolves this reference without exposing storage paths.
    params["videos"] = [f"task:output/{Path(str(artifact_name)).name}"]
    if refine.mode == "ltx_ultra":
        request["references"] = []
        params["videos"] = []
        params["audios"] = []
    request["params"] = params
    return "video", GenerateRequest(**request)
