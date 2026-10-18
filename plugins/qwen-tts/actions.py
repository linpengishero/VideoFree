"""Qwen voice-description generation action."""
from backend.modules.shared.plugin_runtime import TTSRequest


def speech(request, runtime):
    values = request["inputs"]
    return "tts", TTSRequest(
        text=values["text"], mode="describe", voice_model="qwen3_tts",
        instruction=values["voice_description"], speed=values.get("speed", 1.0),
        category_id=values.get("category_id"),
    )
