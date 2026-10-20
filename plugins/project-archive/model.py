"""Plugin-owned archive formats. IDs remain stable when records are reordered."""
from copy import deepcopy

from jsonschema import Draft202012Validator
from backend.modules.shared.plugin_runtime import PluginError

TYPES = ("profile", "story", "episode", "script", "storyboard", "prompts", "characters", "scenes", "continuity", "final-package")
TEXT_TYPES = {"profile", "story", "episode", "script"}
TEXT = {"type": "string", "maxLength": 100000}
ID = {"type": "string", "minLength": 1, "maxLength": 100, "pattern": "^[a-zA-Z0-9_.:-]+$"}


def obj(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def rows(schema):
    return {"type": "array", "items": schema, "maxItems": 2000}


REF = obj({"kind": {"enum": ["asset", "job", "library"]}, "id": {**TEXT, "minLength": 1}, "role": TEXT, "name": TEXT}, ["kind", "id"])
REFS = rows(REF)
SHOT = obj({"id": ID, "title": TEXT, "scene": TEXT, "duration": {"type": "number", "minimum": 0, "maximum": 86400},
            **{key: TEXT for key in ("scene_id", "turn_id", "speaker", "listener", "audio_mode", "framing", "camera", "visual", "dialogue", "audio", "continuity", "script_excerpt", "storyboard_prompt", "action_start", "action_process", "action_end", "selected_job_id")},
            "required_assets": {"type": "array", "items": TEXT, "maxItems": 200},
            "script_revision": {"type": "integer", "minimum": 0},
            "status": {"enum": ["planned", "generating", "review", "selected"]}, "references": REFS}, ["id"])
GROUP = obj({"id": ID, "title": TEXT, "kind": {"enum": ["sequence", "character_views", "first_last"]},
             "shot_ids": {"type": "array", "items": ID, "maxItems": 2000, "uniqueItems": True}, "references": REFS}, ["id", "shot_ids"])
PROMPT = obj({"id": ID, "title": TEXT, "kind": {"enum": ["image", "video", "speech", "music", "sound", "template"]},
              "purpose": {"enum": ["template", "planned", "submitted"]}, "target_id": TEXT,
              **{key: TEXT for key in ("capability_id", "model", "mode", "draft_zh", "execution", "job_id")},
              "parameters": {"type": "object"}, "references": REFS}, ["id", "kind", "purpose"])
ENTITY = obj({"id": ID, "name": TEXT, "kind": {"enum": ["character", "scene", "prop", "voice", "other"]},
              "description": TEXT, "consistency": TEXT, "variation": TEXT, "references": REFS}, ["id"])
SCHEMAS = {
    **{kind: TEXT for kind in TEXT_TYPES},
    "storyboard": obj({"notes": TEXT, "shots": rows(SHOT), "groups": rows(GROUP)}),
    "prompts": obj({"notes": TEXT, "items": rows(PROMPT)}),
    "characters": obj({"notes": TEXT, "items": rows(ENTITY)}),
    "scenes": obj({"notes": TEXT, "items": rows(ENTITY)}),
    "continuity": obj({"decisions": TEXT, "completed": TEXT, "blockers": TEXT, "next_action": TEXT, "references": REFS}),
    "final-package": obj({"summary": TEXT, "deliverables": TEXT, "acceptance": TEXT, "references": REFS}),
}


def empty_content(kind):
    if kind in TEXT_TYPES:
        return ""
    if kind == "storyboard":
        return {"notes": "", "shots": [], "groups": []}
    if kind in {"prompts", "characters", "scenes"}:
        return {"notes": "", "items": []}
    return {}


def normalize(kind, content):
    # Flatten earlier form-based manuscripts without discarding their content.
    if kind in TEXT_TYPES and isinstance(content, dict):
        labels = {"project_type": "作品类型", "synopsis": "梗概", "audience": "受众", "tone": "基调",
                  "target_duration": "目标时长", "outline": "大纲", "rules": "创作约定", "premise": "命题",
                  "world": "世界观", "ending": "结尾", "number": "集数", "goal": "目标", "opening": "开场",
                  "dependencies": "前后承接", "title": "场次", "location": "地点", "time": "时间",
                  "characters": "人物", "action": "动作", "dialogue": "对白", "narration": "旁白",
                  "scenes": "场次", "notes": "备注"}

        def readable(value):
            if isinstance(value, list):
                return "\n\n".join(readable(item) for item in value)
            if isinstance(value, dict):
                return "\n\n".join((str(v) if k == "text" else f"{labels.get(k, k)}：{readable(v)}")
                                    for k, v in value.items() if v and k not in {"id", "references"})
            return {"single": "单片故事", "series": "连续剧"}.get(str(value), str(value))

        content = readable(content)
    if isinstance(content, str) and kind not in TEXT_TYPES:
        target = {"continuity": "decisions", "final-package": "summary"}.get(kind, "notes")
        content = dict(empty_content(kind), **{target: content})
    content = deepcopy(content)
    errors = sorted(Draft202012Validator(SCHEMAS[kind]).iter_errors(content), key=lambda error: str(error.path))
    if errors:
        error = errors[0]
        raise PluginError(422, f"档案格式错误 {'.'.join(map(str, error.path))}: {error.message}")
    for field in (() if isinstance(content, str) else ("items", "shots", "groups", "scenes")):
        ids = [item["id"] for item in content.get(field, [])]
        if len(ids) != len(set(ids)):
            raise PluginError(422, f"{field} 中存在重复 ID")
    if kind == "storyboard":
        shots = {item["id"] for item in content.get("shots", [])}
        for group in content.get("groups", []):
            if not set(group["shot_ids"]).issubset(shots):
                raise PluginError(422, "分镜组引用了不存在的镜头")
    return content


def reference_jobs(app, project_id, content, explicit):
    jobs = set(explicit)

    def collect(value):
        if isinstance(value, dict):
            if value.get("kind") == "job":
                jobs.add(value["id"])
            if value.get("job_id"):
                jobs.add(value["job_id"])
            if value.get("selected_job_id"):
                jobs.add(value["selected_job_id"])
            for key, child in value.items():
                if key != "parameters":
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(content)
    for job_id in jobs:
        job = app.job(job_id)
        if not job or job.get("project_id") != project_id:
            raise PluginError(422, f"引用任务不存在或不属于当前项目：{job_id}")
    return sorted(jobs)
