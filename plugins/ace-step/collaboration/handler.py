async def director(request, runtime):
    return await runtime.single(request)


def confirmation(source, result, runtime):
    payload = result.get("generation_payload", {})
    return {
        "lyrics": "[Instrumental]",
        "settings": {key: payload[key] for key in ("music_bpm", "music_key", "music_timesignature")
                     if isinstance(payload, dict) and key in payload},
    }
