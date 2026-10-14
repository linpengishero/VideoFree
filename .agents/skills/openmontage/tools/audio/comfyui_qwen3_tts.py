"""Local Qwen3-TTS narration through a ComfyUI server."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool, Determinism, ExecutionMode, ResourceProfile, RetryPolicy,
    ToolResult, ToolRuntime, ToolStability, ToolStatus, ToolTier,
)
from tools._comfyui.client import ComfyUIClient, ComfyUIError


class ComfyUIQwen3TTS(BaseTool):
    """Use ComfyUI-Qwen3-TTS models already installed on a LAN ComfyUI host."""

    name = "comfyui_qwen3_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "comfyui"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.SEEDED
    runtime = ToolRuntime.LOCAL_GPU

    dependencies: list[str] = []
    install_instructions = (
        "Set COMFYUI_TTS_SERVER_URL (or COMFYUI_SERVER_URL) to a running ComfyUI server. "
        "The server must expose Qwen3Loader, Qwen3CustomVoice, and SaveAudio, "
        "and have a local Qwen3-TTS model installed."
    )
    agent_skills = ["comfyui", "text-to-speech"]
    capabilities = ["text_to_speech", "voice_selection", "multilingual", "offline_generation"]
    supports = {"voice_cloning": False, "multilingual": True, "offline": True, "native_audio": True}
    best_for = ["offline Chinese and multilingual narration via local Qwen3-TTS", "local GPU production without API costs"]
    not_good_for = ["voice cloning without a user-supplied authorized reference recording"]
    fallback_tools = ["piper_tts", "dashscope_tts", "openai_tts"]

    input_schema = {
        "type": "object", "required": ["text"], "properties": {
            "text": {"type": "string", "description": "Narration text."},
            "model": {"type": "string", "default": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"},
            "voice": {"type": "string", "default": "Vivian", "description": "Qwen3 CustomVoice speaker."},
            "language": {"type": "string", "default": "Chinese", "enum": ["Auto", "Chinese", "English", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian"]},
            "instructions": {"type": "string", "description": "Optional delivery direction; switches to the VoiceDesign model."},
            "seed": {"type": "integer", "description": "Optional deterministic seed."},
            "output_path": {"type": "string", "description": "Destination .flac file."},
            "timeout_seconds": {"type": "integer", "default": 900},
            "resume_prompt_id": {"type": "string"},
        },
    }
    resource_profile = ResourceProfile(cpu_cores=2, ram_mb=8000, vram_mb=8000, disk_mb=200, network_required=False)
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=["timeout"])
    idempotency_key_fields = ["text", "model", "voice", "language", "instructions", "seed"]
    side_effects = ["writes audio file to output_path"]
    user_visible_verification = ["Listen for intelligibility, voice choice, and pacing."]

    def __init__(self) -> None:
        self._client = ComfyUIClient(capability="tts")

    def get_status(self) -> ToolStatus:
        if not self._client.is_available():
            return ToolStatus.UNAVAILABLE
        required = {"Qwen3Loader", "Qwen3CustomVoice", "SaveAudio"}
        return ToolStatus.AVAILABLE if all(self._client.has_node(n) for n in required) else ToolStatus.DEGRADED

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def estimate_runtime(self, inputs: dict[str, Any]) -> float:
        return max(15.0, len(inputs.get("text", "")) * 0.4)

    def _build_workflow(self, inputs: dict[str, Any]) -> dict[str, dict[str, Any]]:
        model = inputs.get("model", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
        voice_design = bool(inputs.get("instructions"))
        if voice_design:
            model = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
        voice_node = "Qwen3VoiceDesign" if voice_design else "Qwen3CustomVoice"
        voice_inputs: dict[str, Any] = {
            "model": ["1", 0], "text": inputs["text"], "language": inputs.get("language", "Chinese"),
            "seed": int(inputs.get("seed", 42)),
        }
        if voice_design:
            voice_inputs["instruct"] = inputs["instructions"]
        else:
            voice_inputs["speaker"] = inputs.get("voice", "Vivian")
        return {
            "1": {"class_type": "Qwen3Loader", "inputs": {"repo_id": model, "source": "HuggingFace", "precision": "bf16", "attention": "auto"}},
            "2": {"class_type": voice_node, "inputs": voice_inputs},
            "3": {"class_type": "SaveAudio", "inputs": {"audio": ["2", 0], "filename_prefix": "openmontage/qwen3-tts"}},
        }

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        if self.get_status() != ToolStatus.AVAILABLE:
            return ToolResult(success=False, error="Local Qwen3-TTS is unavailable. " + self.install_instructions)
        output = Path(inputs.get("output_path", "qwen3_tts.flac"))
        started = time.time()
        try:
            paths = self._client.generate(self._build_workflow(inputs), "3", output,
                timeout=int(inputs.get("timeout_seconds", 900)), resume_prompt_id=inputs.get("resume_prompt_id"))
        except ComfyUIError as exc:
            return ToolResult(success=False, error=str(exc))
        return ToolResult(success=True, data={"provider": self.provider, "model": inputs.get("model", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"), "voice": inputs.get("voice", "Vivian"), "language": inputs.get("language", "Chinese"), "output": str(paths[0]), "format": paths[0].suffix.lstrip(".")}, artifacts=[str(p) for p in paths], cost_usd=0.0, duration_seconds=round(time.time()-started,2), seed=inputs.get("seed"), model=inputs.get("model", "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"))
