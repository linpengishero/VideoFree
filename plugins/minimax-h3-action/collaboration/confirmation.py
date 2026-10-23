"""Plugin-owned adjustments made when a collaboration is confirmed.

The director's segment plan travels in generation_payload; confirmation turns
it into the single generation request's plugin parameters and settings. The
user owns the total duration and frame (ratio/resolution via the submit UI);
the director allocates that total through parameters.durations.
"""


def _durations(value, segments):
    if isinstance(value, str):
        value = value.replace("，", ",").split(",")
    if not isinstance(value, list) or len(value) != segments:
        return None
    numbers = []
    for item in value:
        try:
            number = float(item)
        except (TypeError, ValueError):
            return None
        if not 1 <= number <= 15:
            return None
        numbers.append(number)
    return numbers


def prepare(source, result, runtime):
    payload = result.get("generation_payload") if isinstance(result.get("generation_payload"), dict) else {}
    patch = {}
    parameters = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
    accepted = {}
    segments = parameters.get("segments")
    if type(segments) is int and 1 <= segments <= 5:
        accepted["segments"] = segments
        for index in range(2, segments + 1):
            value = parameters.get(f"prompt_{index}")
            if isinstance(value, str) and value.strip():
                accepted[f"prompt_{index}"] = value.strip()
        durations = _durations(parameters.get("durations"), segments)
        total = (source.get("settings", {}).get("duration")
                 if isinstance(source, dict) and isinstance(source.get("settings"), dict) else None)
        if total is None:
            total = (payload.get("settings", {}).get("duration")
                     if isinstance(payload.get("settings"), dict) else None)
        if durations is None or type(total) not in {int, float}:
            raise ValueError("导演确认稿缺少有效的分段时长或整片总时长，请重新生成方案")
        if abs(sum(durations) - float(total)) > 0.05:
            raise ValueError("导演确认稿各段时长合计与整片总时长不一致，请重新生成方案")
        accepted["durations"] = ",".join(f"{item:g}" for item in durations)
    if accepted:
        # Marks the job as director-confirmed; the compiler rejects plain direct
        # submissions because the framework always registers a direct mode.
        accepted["director_plan"] = "confirmed"
        patch["parameters"] = accepted
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    accepted_settings = {}
    duration = settings.get("duration")
    source_duration = (source.get("settings", {}).get("duration")
                       if isinstance(source, dict) and isinstance(source.get("settings"), dict) else None)
    if type(source_duration) in {int, float} and 1 <= source_duration <= 75:
        accepted_settings["duration"] = source_duration
    elif type(duration) in {int, float} and 1 <= duration <= 75:
        accepted_settings["duration"] = duration
    if accepted_settings:
        patch["settings"] = accepted_settings
    return patch
