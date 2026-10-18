"""CosyVoice speech actions; platform owns queueing and output storage."""
from backend.modules.shared.plugin_runtime import TTSRequest


def speech(request, runtime):
    values = request["inputs"]
    preset_mode = request["action"]["id"] == "speech_preset"
    preset = runtime.voice_preset(values["preset_id"]) if preset_mode else None
    return "tts", TTSRequest(
        text=values["text"], mode="preset" if preset_mode else "clone",
        character=values["preset_id"] if preset_mode else "orion_7",
        voice_model=preset["model"] if preset_mode else "cosyvoice3",
        speed=values.get("speed", 1.0), category_id=values.get("category_id"),
        reference_audio=None if preset_mode else runtime.reference(values["reference_upload_id"], "audio"),
    )
