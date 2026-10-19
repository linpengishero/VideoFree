"""Plugin-owned adjustments made when a collaboration is confirmed."""


def prepare(source, result, runtime):
    payload = result.get("generation_payload", {})
    capability_id = payload.get("capability_id") if isinstance(payload, dict) else None
    if capability_id == "video.text_to_video" and source.get("capability_id") == "video.reference":
        return {"capability_id": capability_id}
    return {}
