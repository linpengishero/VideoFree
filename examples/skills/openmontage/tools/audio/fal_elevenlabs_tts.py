"""Generate ElevenLabs speech through fal.ai using the shared FAL credential."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class FalElevenLabsTTS(BaseTool):
    """Generate expressive narration with ElevenLabs models hosted by fal.ai."""

    name = "fal_elevenlabs_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "fal.ai"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.ASYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:FAL_KEY"]
    install_instructions = (
        "Set FAL_KEY to a fal.ai API key. No separate ElevenLabs key is needed. "
        "Get a fal.ai key at https://fal.ai/dashboard/keys"
    )
    fallback_tools = ["google_tts", "piper_tts", "elevenlabs_tts"]
    agent_skills = ["elevenlabs"]

    capabilities = [
        "text_to_speech",
        "voice_selection",
        "expressive_delivery",
        "multilingual",
        "word_timestamps",
    ]
    supports = {
        "voice_cloning": False,
        "multilingual": True,
        "offline": False,
        "native_audio": True,
        "inline_audio_tags": True,
        "word_timestamps": True,
    }
    best_for = [
        "expressive ElevenLabs narration through an existing fal.ai connection",
        "emotionally directed voiceover with Eleven v3 audio tags",
        "multilingual narration without a separate ElevenLabs credential",
    ]
    not_good_for = [
        "offline generation",
        "voice cloning or private custom ElevenLabs voices",
    ]

    _MODELS = {
        "eleven-v3": "fal-ai/elevenlabs/tts/eleven-v3",
        "multilingual-v2": "fal-ai/elevenlabs/tts/multilingual-v2",
        "turbo-v2.5": "fal-ai/elevenlabs/tts/turbo-v2.5",
    }
    _MODEL_ALIASES = {
        "eleven_v3": "eleven-v3",
        "eleven_multilingual_v2": "multilingual-v2",
        "multilingual_v2": "multilingual-v2",
        "eleven_turbo_v2_5": "turbo-v2.5",
        "turbo_v2_5": "turbo-v2.5",
        **{value: key for key, value in _MODELS.items()},
    }
    _PRICE_PER_CHARACTER = {
        "eleven-v3": 0.0001,
        "multilingual-v2": 0.0001,
        "turbo-v2.5": 0.00005,
    }
    _POLL_INTERVAL_SECONDS = 2
    _MAX_WAIT_SECONDS = 300

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to speak. Eleven v3 supports inline tags such as [whispers].",
            },
            "voice": {
                "type": "string",
                "default": "Rachel",
                "description": "fal.ai ElevenLabs voice name or ID",
            },
            "voice_id": {
                "type": "string",
                "description": "Alias for voice, for compatibility with tts_selector",
            },
            "model_id": {
                "type": "string",
                "default": "eleven-v3",
                "description": "eleven-v3, multilingual-v2, or turbo-v2.5",
            },
            "stability": {
                "type": "number",
                "default": 0.5,
                "minimum": 0,
                "maximum": 1,
            },
            "similarity_boost": {
                "type": "number",
                "default": 0.75,
                "minimum": 0,
                "maximum": 1,
            },
            "style": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
            "speed": {
                "type": "number",
                "default": 1.0,
                "minimum": 0.7,
                "maximum": 1.2,
            },
            "language_code": {
                "type": "string",
                "description": "Optional ISO 639-1 language code",
            },
            "timestamps": {
                "type": "boolean",
                "default": False,
            },
            "apply_text_normalization": {
                "type": "string",
                "default": "auto",
                "enum": ["auto", "on", "off"],
            },
            "output_format": {
                "type": "string",
                "default": "mp3_44100_128",
                "enum": [
                    "mp3_22050_32",
                    "mp3_44100_64",
                    "mp3_44100_96",
                    "mp3_44100_128",
                    "mp3_44100_192",
                    "pcm_16000",
                    "pcm_24000",
                    "pcm_44100",
                    "pcm_48000",
                    "opus_48000_64",
                    "opus_48000_96",
                    "opus_48000_128",
                    "opus_48000_192",
                ],
            },
            "seed": {"type": "integer"},
            "output_path": {"type": "string"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1,
        ram_mb=256,
        vram_mb=0,
        disk_mb=50,
        network_required=True,
    )
    retry_policy = RetryPolicy(
        max_retries=0,
        retryable_errors=["rate_limit", "timeout"],
    )
    idempotency_key_fields = [
        "text",
        "voice",
        "voice_id",
        "model_id",
        "stability",
        "similarity_boost",
        "style",
        "speed",
        "language_code",
        "seed",
    ]
    side_effects = [
        "writes an audio file to output_path",
        "submits one paid fal.ai ElevenLabs speech request",
    ]
    user_visible_verification = [
        "Listen to the generated voice sample before approving full narration",
    ]

    def _get_api_key(self) -> str | None:
        return os.environ.get("FAL_KEY") or os.environ.get("FAL_AI_API_KEY")

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if self._get_api_key() else ToolStatus.UNAVAILABLE

    def _resolve_model(self, requested: str | None) -> tuple[str, str]:
        model_name = requested or "eleven-v3"
        model_name = self._MODEL_ALIASES.get(model_name, model_name)
        if model_name not in self._MODELS:
            choices = ", ".join(self._MODELS)
            raise ValueError(f"model_id must be one of: {choices}")
        return model_name, self._MODELS[model_name]

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        model_name, _ = self._resolve_model(inputs.get("model_id"))
        return round(
            len(inputs.get("text", "")) * self._PRICE_PER_CHARACTER[model_name],
            4,
        )

    @staticmethod
    def _output_extension(output_format: str) -> str:
        return {
            "mp3": "mp3",
            "pcm": "pcm",
            "opus": "opus",
        }.get(output_format.split("_", 1)[0], "audio")

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="No fal.ai API key found. " + self.install_instructions,
            )

        text = str(inputs.get("text", "")).strip()
        if not text:
            return ToolResult(success=False, error="text is required")

        try:
            model_name, model_id = self._resolve_model(inputs.get("model_id"))
        except ValueError as exc:
            return ToolResult(success=False, error=str(exc))

        stability = float(inputs.get("stability", 0.5))
        similarity_boost = float(inputs.get("similarity_boost", 0.75))
        speed = float(inputs.get("speed", 1.0))
        if not 0 <= stability <= 1 or not 0 <= similarity_boost <= 1:
            return ToolResult(
                success=False,
                error="stability and similarity_boost must be between 0 and 1",
            )
        if not 0.7 <= speed <= 1.2:
            return ToolResult(success=False, error="speed must be between 0.7 and 1.2")

        output_format = inputs.get("output_format", "mp3_44100_128")
        voice = inputs.get("voice") or inputs.get("voice_id") or "Rachel"
        payload: dict[str, Any] = {
            "text": text,
            "voice": voice,
            "stability": stability,
            "similarity_boost": similarity_boost,
            "speed": speed,
            "timestamps": bool(inputs.get("timestamps", False)),
            "apply_text_normalization": inputs.get("apply_text_normalization", "auto"),
            "output_format": output_format,
        }
        for optional in ("language_code", "seed", "style"):
            if inputs.get(optional) is not None:
                payload[optional] = inputs[optional]

        import requests

        started = time.time()
        headers = {
            "Authorization": f"Key {api_key}",
            "Content-Type": "application/json",
        }
        queue_url = f"https://queue.fal.run/{model_id}"

        try:
            submit_response = requests.post(
                queue_url,
                headers=headers,
                json=payload,
                timeout=30,
            )
            submit_response.raise_for_status()
            queue_data = submit_response.json()
            status_url = queue_data["status_url"]
            response_url = queue_data["response_url"]

            deadline = time.monotonic() + self._MAX_WAIT_SECONDS
            while True:
                if time.monotonic() >= deadline:
                    return ToolResult(
                        success=False,
                        error="fal.ai ElevenLabs speech timed out while waiting in the queue",
                        duration_seconds=round(time.time() - started, 2),
                    )
                time.sleep(self._POLL_INTERVAL_SECONDS)
                status_response = requests.get(status_url, headers=headers, timeout=20)
                status_response.raise_for_status()
                status = status_response.json().get("status", "UNKNOWN")
                if status == "COMPLETED":
                    break
                if status in {"FAILED", "CANCELLED"}:
                    return ToolResult(
                        success=False,
                        error=f"fal.ai ElevenLabs speech {status.lower()}",
                        duration_seconds=round(time.time() - started, 2),
                    )

            result_response = requests.get(response_url, headers=headers, timeout=30)
            result_response.raise_for_status()
            result_data = result_response.json()
            audio_url = result_data["audio"]["url"]

            audio_response = requests.get(audio_url, timeout=120)
            audio_response.raise_for_status()
            default_output = f"fal_elevenlabs_tts.{self._output_extension(output_format)}"
            output_path = Path(inputs.get("output_path", default_output))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(audio_response.content)
        except Exception as exc:
            safe_error = str(exc).replace(api_key, "[REDACTED]")
            return ToolResult(
                success=False,
                error=f"fal.ai ElevenLabs speech failed: {safe_error}",
                duration_seconds=round(time.time() - started, 2),
            )

        data = {
            "provider": self.provider,
            "model": model_id,
            "voice": voice,
            "text_length": len(text),
            "stability": stability,
            "similarity_boost": similarity_boost,
            "speed": speed,
            "output": str(output_path),
            "format": output_format,
        }
        if payload["timestamps"] and "timestamps" in result_data:
            data["timestamps"] = result_data["timestamps"]

        return ToolResult(
            success=True,
            data=data,
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost({**inputs, "model_id": model_name, "text": text}),
            duration_seconds=round(time.time() - started, 2),
            model=model_id,
        )
