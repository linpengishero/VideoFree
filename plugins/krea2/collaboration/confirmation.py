"""Apply Krea2 settings selected or revised by the collaboration result."""

_RESOLUTIONS = {
    "720P": "768P", "768": "768P", "768P": "768P",
    "1024": "1K", "1024P": "1K", "1K": "1K",
    "1440": "1440P", "1440P": "1440P",
    "2048": "2K", "2048P": "2K", "2K": "2K",
}


def confirm(source, result, runtime):
    payload = result.get("generation_payload", {}) if isinstance(result, dict) else {}
    original = source.get("settings", {}) if isinstance(source, dict) else {}
    resolution = payload.get("resolution", original.get("resolution", "1K"))
    resolution = _RESOLUTIONS.get(str(resolution).strip().upper(), "1K")
    ratio = payload.get("aspect_ratio", original.get("ratio", "16:9"))
    patch = {"resolution": resolution}
    if isinstance(ratio, str) and ratio.strip():
        patch["ratio"] = ratio.strip()
    return {"settings": patch}
