# Copyright (c) 2026 VideoFree individual project author and contributors.
# Part of VideoFree: https://github.com/linpengishero/VideoFree
# Licensed under the GNU Affero General Public License v3.0; see LICENSE and NOTICE.
# Separate commercial licensing may be available; see COMMERCIAL_LICENSE.md.

"""Runtime request contracts shared by interfaces, domains, and integrations."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    category_id: str | None = Field(default=None, max_length=120)
    prompt: str = Field(min_length=1)
    workflow: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    references: list[str] = Field(default_factory=list)
    duration_seconds: float = Field(default=5, ge=1, le=360)
    mode: str = ""
    generation: dict[str, str] = Field(default_factory=dict)
    internal_project_id: str | None = Field(default=None, exclude=True)


class TTSRequest(BaseModel):
    category_id: str | None = Field(default=None, max_length=120)
    text: str = Field(min_length=1)
    voice: str = "default"
    format: str = "wav"
    character: str = ""
    mode: str = "preset"
    voice_model: str = Field(default="", max_length=120)
    instruction: str = ""
    speaker_preset: str = ""
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    reference_audio: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    parent_job_id: str | None = None
    generation: dict[str, str] = Field(default_factory=dict)
    internal_project_id: str | None = Field(default=None, exclude=True)


class SettingsRequest(BaseModel):
    locale: Literal["zh-CN", "en-US"] | None = None
    gateway_token: str | None = Field(default=None, max_length=512)
    comfyui_url: str | None = None
    comfyui_output_dir: str | None = None
    ai_provider: str | None = None
    ai_base_url: str | None = None
    ai_api_key: str | None = None
    ai_model: str | None = None
    ai_multimodal_video: bool | None = None
    ai_thinking_mode: str | None = None
    resource_directory: str | None = None


class AIModelsRequest(BaseModel):
    ai_base_url: str = Field(min_length=1)
    ai_api_key: str = ""
    ai_provider: str = "openai"


class AgentReference(BaseModel):
    kind: str
    name: str = ""
    media_type: str = ""
    data_url: str | None = None


class AgentChatRequest(BaseModel):
    category_id: str | None = Field(default=None, max_length=120)
    session_id: str | None = None
    progress_id: str | None = None
    message: str = Field(min_length=1, max_length=20000)
    kind: str = "video"
    model: str = ""
    mode: str = ""
    duration_seconds: float = Field(default=5, ge=1, le=360)
    ratio: str = "16:9"
    resolution: int = 720
    references: list[AgentReference] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)
    review_mode: str = Field(default="human", pattern="^(human|external)$")
    collaboration_mode: str = Field(default="director", pattern="^(quick|director)$")
    client_request_id: str | None = Field(default=None, max_length=120)
    project_id: str | None = Field(default=None, min_length=1, max_length=120)
