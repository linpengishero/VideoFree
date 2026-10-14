from typing import Any

from pydantic import BaseModel, Field, model_validator


class AssetInput(BaseModel):
    type: str = Field(pattern="^(image|video|audio)$")
    upload_id: str = Field(min_length=8, max_length=80)
    role: str = "reference"


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    content_summary: str = Field(default="", max_length=3000)


class ProjectSelectRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=120)


class CreateSettings(BaseModel):
    ratio: str = "16:9"
    resolution: str = "720P"
    duration: float = Field(default=5, ge=1, le=360)
    variant: str = "normal"
    seed: int | None = None
    style_id: str = ""
    music_style_id: str = "pop"
    music_preset_id: str = ""
    singer_id: str = "female"
    voice_texture_id: str = "natural"
    music_bpm: int = Field(default=100, ge=10, le=300)
    music_key: str = Field(default="C minor", pattern=r"^[A-G](?:#|b)? (?:major|minor)$")
    music_timesignature: str = Field(default="4", pattern="^(2|3|4|6)$")
    voice_id: str = "orion_7"
    voice_model: str = Field(default="qwen3_tts", pattern="^(qwen3_tts|cosyvoice3)$")
    voice_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    instruction: str = ""
    shots: list[str] = Field(default_factory=list)
    native_model: str = ""
    confirmed_prompt_zh: str = ""
    execution_prompt_en: str = ""
    h3_camera_lora: str = Field(default="auto", pattern="^(auto|crash_zoom|off)$")
    h3_style_lora: str = Field(default="", pattern="^(|cinemagrade)$")


class CreateRequest(BaseModel):
    capability_id: str = ""
    prompt: str = ""
    lyrics: str = ""
    inputs: list[AssetInput] = Field(default_factory=list)
    settings: CreateSettings = Field(default_factory=CreateSettings)
    shots: list[str] | None = None
    prompt_processing: str = Field(default="direct", pattern="^(direct|compile|director)$")
    session_id: str | None = Field(default=None, max_length=120)
    answer: str = Field(default="", max_length=100_000)
    project_id: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def normalize_legacy_shots(self):
        if self.shots and not self.settings.shots:
            self.settings.shots = self.shots
        return self


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


class PresetSpeechRequest(BaseModel):
    preset_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    text: str = Field(min_length=1, max_length=20_000)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class DescribedSpeechRequest(BaseModel):
    voice_description: str = Field(min_length=1, max_length=2_000)
    text: str = Field(min_length=1, max_length=20_000)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class ClonedSpeechRequest(BaseModel):
    reference_upload_id: str = Field(min_length=32, max_length=32, pattern=r"^[a-fA-F0-9]{32}$")
    text: str = Field(min_length=1, max_length=20_000)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class RegenerateRequest(BaseModel):
    prompt: str | None = None
    lyrics: str | None = None
    inputs: list[AssetInput] | None = None
    settings: CreateSettings | None = None
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


class CollaborationCreateRequest(BaseModel):
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
