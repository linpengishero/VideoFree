from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssetInput(BaseModel):
    type: str = Field(pattern="^(image|video|audio)$")
    upload_id: str = Field(min_length=8, max_length=80)
    role: str = "reference"


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    content_summary: str = Field(default="", max_length=3000)
    ai_created: bool = False


class ProjectSelectRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=120)


class CreateSettings(BaseModel):
    # Plugin-specific settings are validated against the selected capability UI.
    model_config = ConfigDict(extra="allow")
    ratio: str = "16:9"
    resolution: str = "720P"
    duration: float = Field(default=5, ge=1, le=360)
    variant: str = "normal"
    seed: int | None = None
    style_id: str = ""
    voice_id: str = ""
    voice_model: str = Field(default="", max_length=120)
    voice_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    instruction: str = ""
    shots: list[str] = Field(default_factory=list)
    native_model: str = ""
    confirmed_prompt_zh: str = ""
    execution_prompt_en: str = ""


class CreateRequest(BaseModel):
    parent_job_id: str | None = Field(default=None, min_length=1, max_length=120)
    category_id: str | None = Field(default=None, max_length=120)
    capability_id: str = ""
    prompt: str = ""
    lyrics: str = ""
    inputs: list[AssetInput] = Field(default_factory=list)
    settings: CreateSettings = Field(default_factory=CreateSettings)
    prompt_processing: str = Field(default="direct", min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    parameters: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = Field(default=None, max_length=120)
    answer: str = Field(default="", max_length=100_000)
    project_id: str | None = Field(default=None, min_length=1, max_length=120)

class PresetWrite(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=1000)
    instruction: str = Field(min_length=1, max_length=4000)
    config: dict[str, Any] = Field(default_factory=dict)


class VoiceWrite(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=80)
    instruction: str = Field(min_length=1, max_length=2000)
    speaker: str = ""
    language: str = "Chinese"
    model: str = ""


class RegenerateRequest(BaseModel):
    prompt: str | None = None
    lyrics: str | None = None
    inputs: list[AssetInput] | None = None
    settings: CreateSettings | None = None
    parameters: dict[str, Any] | None = None
    execution_prompt_en: str | None = None
    confirmed_prompt_zh: str | None = None

    @model_validator(mode="after")
    def validate_prompt_snapshots(self):
        if (self.execution_prompt_en is None) != (self.confirmed_prompt_zh is None):
            raise ValueError("修改英文执行稿时必须同时提交对应的中文稿")
        if self.execution_prompt_en is not None and (
            not self.execution_prompt_en.strip() or not self.confirmed_prompt_zh.strip()
        ):
            raise ValueError("英文执行稿和中文稿不能为空")
        return self


class PluginActionExecuteRequest(BaseModel):
    category_id: str | None = Field(default=None, max_length=120)
    source_job_id: str | None = Field(default=None, min_length=1, max_length=120)
    source_upload_id: str | None = Field(default=None, pattern=r"^[a-fA-F0-9]{32}$")
    project_id: str | None = Field(default=None, min_length=1, max_length=120)
    inputs: dict[str, Any] = Field(default_factory=dict)


class PluginActionResponse(BaseModel):
    action_id: str
    status: str
    capability_id: str | None = None
    job_id: str | None = None
    job_url: str | None = None
    wait_url: str | None = None
    result: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class CollaborationCreateRequest(BaseModel):
    project_id: str | None = Field(default=None, max_length=120)
    category_id: str | None = Field(default=None, max_length=120)
    capability_id: str
    model_id: str = Field(min_length=1, max_length=80)
    mode_id: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=100_000)
    prompt: str = ""
    lyrics: str = ""
    inputs: list[AssetInput] = Field(default_factory=list)
    settings: CreateSettings = Field(default_factory=CreateSettings)
    collaboration_mode: str = Field(default="director", pattern="^(quick|director)$")


class CollaborationMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=100_000)


class CollaborationConfirmRequest(BaseModel):
    revision: int = Field(ge=1)
    idempotency_key: str | None = Field(default=None, max_length=120)
    execution_prompt_en: str | None = None
    confirmed_prompt_zh: str | None = None

    @model_validator(mode="after")
    def validate_prompt_snapshots(self):
        if (self.execution_prompt_en is None) != (self.confirmed_prompt_zh is None):
            raise ValueError("修改英文执行稿时必须同时提交对应的中文稿")
        if self.execution_prompt_en is not None and (
            not self.execution_prompt_en.strip() or not self.confirmed_prompt_zh.strip()
        ):
            raise ValueError("英文执行稿和中文稿不能为空")
        return self
