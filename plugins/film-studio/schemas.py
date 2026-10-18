"""Film timeline plan validation owned by the application plugin."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_MAIN = 200
MAX_OVERLAY = 50
MAX_AUDIO = 100
MAX_CAPTIONS = 1000
MAX_TEXTS = 200
MAX_TOTAL_SECONDS = 3600
TRANSITION_KINDS = ('fade', 'wipeleft', 'wiperight', 'slideleft', 'slideright', 'slideup', 'slidedown', 'circleopen', 'circleclose')


class Transition(BaseModel):
    """A cross-fade into the next main-track item; it consumes media on both sides."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    type: Literal[TRANSITION_KINDS]
    duration: float = Field(default=0.5, gt=0, le=3)


class Rect(BaseModel):
    """Canvas-relative placement of an overlay clip."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    x: int = Field(default=0, ge=0)
    y: int = Field(default=0, ge=0)
    w: int = Field(gt=0, le=8192)
    h: int = Field(gt=0, le=8192)
    opacity: int = Field(default=100, ge=0, le=100)


class Clip(BaseModel):
    """One main-track item: a cut from a source video, or a blank gap."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    kind: Literal['clip', 'blank'] = 'clip'
    job_id: str | None = Field(default=None, min_length=1, max_length=100)
    library_path: str | None = Field(default=None, min_length=1, max_length=1000)
    artifact_index: int = Field(default=0, ge=0)
    in_seconds: float = Field(default=0, ge=0, alias='in')
    out: float = Field(gt=0, le=86400)
    original: bool = True
    volume: int = Field(default=100, ge=0, le=100)
    fade_in: float = Field(default=0, ge=0, le=10)
    fade_out: float = Field(default=0, ge=0, le=10)
    transition: Transition | None = None

    @property
    def duration(self) -> float:
        return self.out - (0 if self.kind == 'blank' else self.in_seconds)

    @model_validator(mode='after')
    def valid_range(self):
        if self.kind == 'clip' and not self.job_id and not self.library_path:
            raise ValueError('镜头必须指定素材')
        if self.out <= self.in_seconds:
            raise ValueError('裁剪终点必须大于起点')
        if self.fade_in + self.fade_out > self.duration:
            raise ValueError('淡入淡出总长不能大于片段时长')
        return self


class PlacedClip(Clip):
    """An overlay or extra audio clip placed at an absolute timeline position."""
    start: float = Field(default=0, ge=0, le=86400)
    rect: Rect | None = None

    @model_validator(mode='after')
    def valid_source(self):
        if self.kind != 'clip':
            raise ValueError('叠加轨和音轨不能使用黑场片段')
        return self


class Caption(BaseModel):
    """One editable subtitle cue on the final timeline."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    text: str = Field(min_length=1, max_length=2000)
    start: float = Field(ge=0, le=86400)
    end: float = Field(gt=0, le=86400)

    @model_validator(mode='after')
    def valid_range(self):
        self.text = self.text.strip()
        if not self.text or self.end <= self.start:
            raise ValueError('字幕文本不能为空且结束时间必须大于开始时间')
        return self


class TextOverlay(Caption):
    """Freely positioned text rendered independently from subtitles."""
    x: int = Field(ge=0, le=8192)
    y: int = Field(ge=0, le=8192)
    font_size: int = Field(default=64, ge=12, le=300)
    color: str = Field(default='#FFFFFF', pattern=r'^#[0-9A-Fa-f]{6}$')


class FilmWrite(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    clips: list[Clip] = Field(default_factory=list, max_length=MAX_MAIN)
    overlay_clips: list[PlacedClip] = Field(default_factory=list, max_length=MAX_OVERLAY)
    audio_clips: list[PlacedClip] = Field(default_factory=list, max_length=MAX_AUDIO)
    captions: list[Caption] = Field(default_factory=list, max_length=MAX_CAPTIONS)
    texts: list[TextOverlay] = Field(default_factory=list, max_length=MAX_TEXTS)
    bgm_job_id: str | None = None
    volume: int = Field(default=18, ge=0, le=100)
    width: Literal[720, 1080, 1280, 1440, 1920] = 1920
    height: Literal[720, 1080, 1280, 1440, 1920] = 1080
    fps: Literal[24, 25, 30, 60] = 30
    fit: Literal['contain', 'cover'] = 'contain'
    timeline_version: Literal[1, 2] = 2

    @model_validator(mode='after')
    def valid_plan(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError('名称不能为空')
        total = 0.0
        for index, clip in enumerate(self.clips):
            total += clip.duration
            join = clip.transition
            if join and index + 1 < len(self.clips):
                if join.duration > min(clip.duration, self.clips[index + 1].duration):
                    raise ValueError(f'第 {index + 1} 段转场时长不能超过相邻片段时长')
                total -= join.duration
        if total > MAX_TOTAL_SECONDS:
            raise ValueError('成片总时长不能超过 1 小时')
        for overlay in self.overlay_clips:
            if not overlay.rect:
                raise ValueError('叠加片段必须指定位置与尺寸')
            if overlay.rect.x + overlay.rect.w > self.width or overlay.rect.y + overlay.rect.h > self.height:
                raise ValueError('叠加片段超出画幅')
            if overlay.start + overlay.duration > total + 0.05:
                raise ValueError('叠加片段落在成片时间范围之外')
        for audio in self.audio_clips:
            if audio.start + audio.duration > total + 0.05:
                raise ValueError('音轨片段落在成片时间范围之外')
        for caption in self.captions:
            if caption.end > total + 0.05:
                raise ValueError('字幕落在成片时间范围之外')
        for text in self.texts:
            if text.end > total + 0.05:
                raise ValueError('文字落在成片时间范围之外')
            if text.x > self.width or text.y > self.height:
                raise ValueError('文字位置超出画幅')
        return self


class StageWrite(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stage: Literal['writing', 'assets', 'generation', 'review', 'acceptance']
    status: Literal['pending', 'running', 'completed', 'failed', 'blocked']
    note: str = Field(default='', max_length=2000)
