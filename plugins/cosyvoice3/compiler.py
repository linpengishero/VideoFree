"""CosyVoice speech nodes belong to the CosyVoice plugin."""


def prepare_speech(request, preset, runtime):
    if request.mode != "preset":
        return request
    sample = runtime.voice_sample(preset)
    if sample:
        return request.model_copy(update={"reference_audio": str(sample)})
    if not request.speaker_preset:
        raise ValueError("CosyVoice3 预设缺少参考音频或可用 speaker preset")
    return request


def prepare(workflow, config, request, media, job_id, prompt):
    for node in workflow.values():
        kind, inputs = node.get("class_type"), node.setdefault("inputs", {})
        if kind in {"FL_CosyVoice3_ZeroShot", "FL_CosyVoice3_Instruct2", "FL_CosyVoice3_SpeakerClone", "FL_CosyVoice3_SpeakerInstruct2"}:
            inputs.update(text=request.text, speed=request.speed)
        if kind == "FL_CosyVoice3_Instruct2":
            inputs["instruct_text"] = request.instruction or "请自然、清楚地说这句话。"
        if kind in {"FL_CosyVoice3_SpeakerClone", "FL_CosyVoice3_SpeakerInstruct2"}:
            inputs["speaker_preset"] = request.speaker_preset
        if kind == "LoadAudio" and media["audio"]:
            inputs["audio"] = media["audio"][0]
