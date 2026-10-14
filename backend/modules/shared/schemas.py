from typing import Any

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    workflow: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    references: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(default=5, ge=1, le=360)
    mode: str = ""
    generation: dict[str, str] = Field(default_factory=dict)


class RefineRequest(BaseModel):
    mode: str = Field(pattern="^(h3_refine|preview_refine_fast|preview_refine_stable|ltx_ultra)$")
    width: int = Field(ge=64, le=4096)
    height: int = Field(ge=64, le=4096)
    upscaler: str = Field(default="3d", pattern="^(2d|3d)$")


class H3TranslationRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    mode: str = "reference"


class TTSRequest(BaseModel):
    text: str = Field(min_length=1)
    voice: str = "default"
    format: str = "wav"
    character: str = "orion_7"
    mode: str = "preset"
    voice_model: str = Field(default="qwen3_tts", pattern="^(qwen3_tts|cosyvoice3)$")
    instruction: str = ""
    speaker_preset: str = ""
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    reference_audio: str | None = None
    parent_job_id: str | None = None
    generation: dict[str, str] = Field(default_factory=dict)
    internal_project_id: str | None = Field(default=None, exclude=True)


class SettingsRequest(BaseModel):
    comfyui_url: str | None = None
    comfyui_output_dir: str | None = None
    ai_provider: str | None = None
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model: str | None = None
    ai_multimodal_video: bool | None = None
    ai_thinking_mode: str | None = None
    grsai_api_key: str | None = None


class AIModelsRequest(BaseModel):
    ai_base_url: str = Field(min_length=1)
    ai_api_key: str = ""


class AgentReference(BaseModel):
    kind: str
    name: str = ""
    media_type: str = ""
    data_url: str | None = None


class AgentChatRequest(BaseModel):
    session_id: str | None = None
    progress_id: str | None = None
    message: str = Field(min_length=1, max_length=20000)
    kind: str = "video"
    model: str = "minimax-h3"
    mode: str = "reference"
    duration_seconds: float = Field(default=5, ge=1, le=360)
    ratio: str = "16:9"
    resolution: int = 720
    references: list[AgentReference] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    review_mode: str = Field(default="human", pattern="^(human|external)$")
    collaboration_mode: str = Field(default="director", pattern="^(quick|director)$")
    client_request_id: str | None = Field(default=None, max_length=120)
    project_id: str | None = Field(default=None, min_length=1, max_length=120)


class AgentSubmittedRequest(BaseModel):
    job_id: str = Field(min_length=1, max_length=120)


class AgentGenerateRequest(BaseModel):
    kind: str = Field(pattern="^(image|video|tts|music)$")
    payload: dict[str, Any]
    revision: int = Field(ge=0)
