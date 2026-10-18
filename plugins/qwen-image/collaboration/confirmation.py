"""Keep qwen-image settings stable and canonical during confirmation."""

_RESOLUTION_ALIASES = {
    "720P": "768P", "768": "768P", "1024": "1K", "1024P": "1K",
    "1440": "1440P", "2048": "2K", "2048P": "2K",
}

def _resolution(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip().upper()
    if value in {"768P", "1K", "1440P", "2K"}:
        return value
    return _RESOLUTION_ALIASES.get(value, "1K")


def confirm(source, result, runtime):
    settings = source.get("settings") if isinstance(source, dict) else None
    if not isinstance(settings, dict):
        return {}
    patch = {}
    for key in ("ratio", "resolution"):
        value = settings.get(key)
        if key == "resolution":
            value = _resolution(value)
        if isinstance(value, str) and value.strip():
            patch[key] = value
    return {"settings": patch} if patch else {}
