"""Deterministic contract checks, not a substitute for semantic review."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re


CHECKS = {
    "preproduction": {"facts", "speech", "assets", "storyboard"},
    "image": {"identity", "composition", "continuity"},
    "voice": {"intelligibility", "identity", "quality"},
    "media": {"identity", "speaker", "dialogue", "voice", "action", "continuity"},
    "final": {"dialogue", "audio_mix", "continuity", "technical"},
}


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def visible_characters(shot):
    return list(dict.fromkeys([c for c in (shot.get("speaker"), shot.get("listener"), *shot.get("visible_characters", [])) if c]))


def reference_sources(plan, keys):
    progress = plan.get("media_progress", {})
    return [progress.get("references", {}).get(key, {}) for key in keys]


def grid_keys(plan, group):
    keys = [group["scene_id"]]
    shots = {s["id"]: s for s in plan["shots"]}
    for shot_id in group["shot_ids"]:
        shot = shots[shot_id]
        keys.extend(visible_characters(shot))
        keys.extend(shot["required_assets"])
    return list(dict.fromkeys(keys))


def specification(plan, section, key):
    assets = {a["id"]: a for a in plan["episode_assets"]}
    shots = {s["id"]: s for s in plan["shots"]}
    groups = {g["id"]: g for g in plan["storyboard_groups"]}
    settings = plan["config"].get("generation_settings", {}).get("compilations" if section == "videos" else section, {})
    if section in ("drafts", "references", "voices"):
        asset = {k: v for k, v in assets[key].items() if k != "revision"}
        ratio = "16:9" if section == "references" and asset["kind"] != "location" else plan["config"]["aspect"]
        return fingerprint({"asset": asset, "ratio": ratio, "settings": settings})
    if section == "grids":
        return fingerprint({"group": groups[key], "shots": [shots[s] for s in groups[key]["shot_ids"]], "ratio": plan["config"]["aspect"], "settings": settings})
    return fingerprint({"shot": shots[key], "ratio": plan["config"]["aspect"], "settings": settings})


def request_contract(plan, operation, key):
    """Derive ordered inputs from locked assets, never from caller claims."""
    p = plan.get("media_progress", {})
    assets = {a["id"]: a for a in plan["episode_assets"]}
    shots = {s["id"]: s for s in plan["shots"]}
    groups = {g["id"]: g for g in plan["storyboard_groups"]}
    audio = []
    if operation == "drafts":
        capability, sources = "image.qwen.text_to_image", []
    elif operation == "references":
        capability = "image.qwen.image_to_image" if assets[key]["kind"] == "location" else "image.qwen.character"
        sources = [p.get("drafts", {}).get(key, {})]
    elif operation == "grids":
        capability, sources = "image.qwen.storyboard_4", reference_sources(plan, grid_keys(plan, groups[key]))
    elif operation == "panels":
        group = next(g for g in groups.values() if key in g["shot_ids"])
        capability, sources = "image.split", [p.get("grids", {}).get(group["id"], {})]
    elif operation == "compilations":
        shot = shots[key]
        capability = "video.reference"
        sources = [p.get("panels", {}).get(key, {})]
        sources.extend(reference_sources(plan, list(dict.fromkeys([*visible_characters(shot), shot["scene_id"], *shot["required_assets"]]))))
        if shot["audio_mode"] == "h3_dialogue":
            voice = p.get("voices", {}).get(shot["speaker"], {})
            audio = [{"upload_id": voice.get("upload_id"), "sha256": voice.get("sha256")}]
    else:
        raise ValueError("Unknown operation")
    return capability, [("image", source) for source in sources] + [("audio", source) for source in audio]


def check_request(plan, operation, key, request):
    errors = []
    try:
        capability, sources = request_contract(plan, operation, key)
        expected = [(kind, source.get("upload_id")) for kind, source in sources]
        if any(not nonempty(uid) for _, uid in expected):
            errors.append("Upload all required source files before submitting")
        actual = [(i.get("type"), i.get("upload_id")) for i in request.get("inputs", [])]
        if actual != expected:
            errors.append("Actual inputs must match all locked references in order")
        if len([i for i in expected if i[0] == "image"]) > 8:
            errors.append("Too many image references; redesign/split the shot instead of dropping assets")
        if request.get("capability_id") != capability:
            errors.append(f"Requires capability {capability}")
        if request.get("project_id") != plan["config"]["project_id"]:
            errors.append("Wrong project_id")
        if not nonempty(request.get("idempotency_key")):
            errors.append("Stable idempotency_key required")
        if not nonempty(request.get("prompt")):
            errors.append("Prompt required")
        if operation in ("drafts", "references"):
            asset = next(a for a in plan["episode_assets"] if a["id"] == key)
            field = "draft" if operation == "drafts" else "reference"
            if request.get("prompt") != asset.get("prompts", {}).get(field):
                errors.append("Use the exact final asset prompt")
        mode = "compile" if operation == "compilations" else "direct"
        if request.get("prompt_processing") != mode:
            errors.append(f"Requires prompt_processing={mode}")
        settings = request.get("settings", {})
        configured = plan["config"].get("generation_settings", {}).get(operation, {})
        derived = {"ratio"}
        if operation == "compilations":
            derived.add("duration")
        if any(settings.get(k) != v for k, v in configured.items() if k not in derived):
            errors.append("Generation settings must preserve the reviewed final configuration")
        ratio = "16:9" if capability == "image.qwen.character" else plan["config"]["aspect"]
        if operation != "panels" and settings.get("ratio") != ratio:
            errors.append(f"Requires settings.ratio={ratio}")
        if operation == "grids":
            group = next(g for g in plan["storyboard_groups"] if g["id"] == key)
            shots = {s["id"]: s for s in plan["shots"]}
            prompt = request.get("prompt", "")
            if settings.get("shots"):
                errors.append("Qwen storyboard grids embed the four descriptions in the prompt, not settings.shots")
            cursor = 0
            for description in [shots[s]["storyboard_prompt"] for s in group["shot_ids"]]:
                position = prompt.find(description, cursor)
                if position < 0:
                    errors.append("Prompt must embed all four storyboard descriptions in shot_ids order")
                    break
                cursor = position + len(description)
        if operation == "compilations":
            shot = next(s for s in plan["shots"] if s["id"] == key)
            if request.get("prompt") != shot["prompt"]["execution"] or settings.get("duration") != shot["duration"]:
                errors.append("H3 request must preserve exact shot prompt and duration")
    except (KeyError, TypeError, ValueError, AttributeError, StopIteration) as exc:
        errors.append(f"Malformed request: {exc}")
    return errors


def validate_request(plan, root, operation, key, request):
    stages = {"drafts": None, "references": "drafts", "grids": "references", "panels": "grids", "compilations": "storyboard"}
    if operation not in stages:
        return ["Unknown operation"]
    stage = stages[operation]
    errors = validate_gate(plan, root, stage) if stage else validate_plan(plan)
    return errors + check_request(plan, operation, key, request)


def validate_reviewed_file(value, root, stage, revision, shots, allow_self=False):
    if not isinstance(value, dict):
        return ["Reviewed file must be an object"]
    errors = validate_qa(value.get("qa"), stage, revision, shots, allow_self)
    if type(revision) is not int or revision < 1:
        errors.append("Reviewed file requires positive revision")
    try:
        path = (Path(root) / value["path"]).resolve()
        if not path.is_relative_to(Path(root).resolve()) or not path.is_file() or not path.stat().st_size:
            raise ValueError("missing/empty file or path outside run_root")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != value.get("sha256") or value.get("qa", {}).get("input_sha256", {}).get(value["path"]) != digest:
            raise ValueError("artifact and QA hashes differ")
    except (KeyError, OSError, ValueError, TypeError, AttributeError) as exc:
        errors.append(f"Invalid reviewed {stage} file: {exc}")
    return errors


def selected_videos(plan):
    progress = plan.get("media_progress", {})
    result = {}
    for shot in plan["shots"]:
        key = shot["id"]
        candidates = [progress.get("videos", {}).get(key, {}), *progress.get("refinements", {}).get(key, [])]
        result[key] = next((v for v in candidates if v.get("job_id") == progress.get("selected", {}).get(key)), {})
    return result


def selection_hash(plan):
    return fingerprint({k: {f: v.get(f) for f in ("path", "sha256", "job_id")} for k, v in selected_videos(plan).items()})


def check_file(root, value, label):
    errors = []
    try:
        path = (Path(root) / value["path"]).resolve()
        if not path.is_relative_to(Path(root).resolve()) or not path.is_file() or not path.stat().st_size:
            raise ValueError("missing, empty or outside run_root")
        if hashlib.sha256(path.read_bytes()).hexdigest() != value.get("sha256"):
            raise ValueError("SHA256 mismatch")
    except (KeyError, OSError, TypeError, ValueError) as exc:
        errors.append(f"{label}: invalid downloaded file: {exc}")
    return errors


def validate_composition(plan, root, composition):
    """Check videofree film-studio plan, render receipts and the downloaded final file."""
    errors, shots = [], {s["id"]: s for s in plan["shots"]}
    if not isinstance(composition, dict):
        return ["media_progress.composition must record the film-studio plan and render receipts"]
    film_id = composition.get("film_id", "")
    if not isinstance(film_id, str) or not re.fullmatch(r"film-[a-f0-9]{12}", film_id):
        errors.append("composition.film_id must be the actual film-studio plan ID")
    sources = composition.get("sources")
    if not isinstance(sources, list) or not all(isinstance(s, dict) for s in sources) \
            or [s.get("shot_id") for s in sources] != [s["id"] for s in plan["shots"]]:
        errors.append("composition.sources must list every shot exactly once in planned order")
    else:
        selected = plan.get("media_progress", {}).get("selected", {})
        for item in sources:
            key = item["shot_id"]
            if item.get("job_id") != selected.get(key):
                errors.append(f"{key}: composition source must be the selected reviewed job")
            if item.get("audio_mode") != shots[key].get("audio_mode"):
                errors.append(f"{key}: composition audio_mode differs from the locked shot")
    narration = [s["id"] for s in plan["shots"] if s.get("audio_mode") == "pre_recorded_narration"]
    clips = composition.get("audio_clips", [])
    if not isinstance(clips, list) or not all(isinstance(c, dict) for c in clips) \
            or {c.get("shot_id") for c in clips} != set(narration) \
            or any(not nonempty(c.get("job_id")) for c in clips):
        errors.append("Narration shots require audio_clips bound to their reviewed narration jobs")
    for field in ("validate", "preview", "render"):
        receipt = composition.get(field)
        if not isinstance(receipt, dict) or receipt.get("film_id") != film_id or receipt.get("status") != "completed":
            errors.append(f"composition.{field} must record a completed film-studio receipt for this plan")
    if isinstance(composition.get("render"), dict) and not nonempty(composition["render"].get("url")):
        errors.append("composition.render must record the gateway output url")
    preview = composition.get("preview")
    if isinstance(preview, dict):
        errors.extend(check_file(root, preview, "composition.preview"))
    output = composition.get("output")
    if not isinstance(output, dict) or not nonempty(output.get("library_path")):
        errors.append("composition.output.library_path must be the rendered films/final.mp4 library path")
    else:
        errors.extend(check_file(root, output, "composition.output"))
    return errors


def validate_confirmation(plan, root, key, arguments):
    errors = validate_gate(plan, root, "compiled", key)
    compilation = plan.get("media_progress", {}).get("compilations", {}).get(key, {})
    response = compilation.get("response", {})
    if arguments.get("collaboration_id") != response.get("id") or arguments.get("revision") != response.get("revision"):
        errors.append("Confirm only the recorded current H3 session/revision")
    if any(f in arguments for f in ("execution_prompt_en", "confirmed_prompt_zh")):
        errors.append("Do not replace reviewed H3 prompts during confirmation")
    authorization = compilation.get("authorization", {})
    delegated = plan.get("h3_delegation", {})
    delegate_valid = (delegated.get("approved_by") == "user" and nonempty(delegated.get("evidence"))
                      and delegated.get("allow_review_and_confirm") is True
                      and delegated.get("shot_specs", {}).get(key) == specification(plan, "compilations", key))
    explicit_valid = (authorization.get("approved_by") == "user" and nonempty(authorization.get("evidence"))
                      and authorization.get("response_sha256") == fingerprint(response))
    if not explicit_valid and not delegate_valid:
        errors.append("Explicit user approval or scoped H3 review-and-confirm delegation required")
    if not nonempty(arguments.get("idempotency_key")):
        errors.append("Confirmation idempotency_key required")
    return errors


def validate_qa(report, stage, revision, shots, allow_self_review=False):
    errors = []
    if not isinstance(report, dict):
        return ["QA must be an object"]
    for field, expected in (("schema_version", 1), ("stage", stage), ("revision", revision)):
        if report.get(field) != expected:
            errors.append(f"QA {field} must be {expected}")
    actual = report.get("shot_ids")
    if not isinstance(actual, list) or not all(nonempty(s) for s in actual):
        errors.append("QA shot_ids must be a string list")
    elif len(actual) != len(set(actual)) or set(actual) != set(shots):
        errors.append("QA shot_ids must cover exactly the requested shots")
    if not nonempty(report.get("reviewer")):
        errors.append("QA requires a real reviewer identifier")
    mode = report.get("review_mode")
    if mode not in ("independent", "self_review") or (mode == "self_review" and not allow_self_review):
        errors.append("QA review mode not authorized")
    evidence = report.get("evidence")
    if not isinstance(evidence, list) or not evidence or not all(nonempty(e) for e in evidence):
        errors.append("QA requires concrete evidence")
    checks = report.get("checks")
    if not isinstance(checks, dict) or not CHECKS.get(stage, set()).issubset(checks):
        errors.append("QA required checks missing")
    elif any(v not in ("PASS", "FAIL", "BLOCKED") for v in checks.values()):
        errors.append("QA checks contain an unknown status")
    issues = report.get("issues")
    limits = report.get("limitations")
    if not isinstance(issues, list) or not all(isinstance(i, dict) for i in issues):
        errors.append("QA issues must be an object list")
    if not isinstance(limits, list) or not all(nonempty(v) for v in limits):
        errors.append("QA limitations must be a string list")
    if mode == "self_review" and not limits:
        errors.append("Self review must disclose its limitation")
    if report.get("status") != "PASS":
        errors.append("QA gate not PASS")
    if isinstance(checks, dict) and any(v != "PASS" for v in checks.values()):
        errors.append("QA cannot pass with incomplete or failed checks")
    if isinstance(issues, list) and any(isinstance(i, dict) and i.get("severity") == "blocking" for i in issues):
        errors.append("QA contains blocking issues")
    return errors


def validate_plan(plan):
    try:
        return _validate_plan(plan)
    except (TypeError, ValueError, KeyError, AttributeError) as exc:
        return [f"Malformed production contract: {exc}"]


def _validate_plan(plan):
    if not isinstance(plan, dict):
        return ["Production must be an object"]
    errors = []
    config = plan.get("config", {})
    if not isinstance(config, dict):
        return ["config must be an object"]
    if plan.get("schema_version") != 1 or type(plan.get("revision")) is not int or plan["revision"] < 1:
        errors.append("Positive revision and schema_version=1 required")
    for field in ("title", "project_id", "workspace_id", "aspect"):
        if not nonempty(config.get(field)):
            errors.append(f"config.{field} required")
    if not positive(config.get("duration_target_sec")):
        errors.append("Positive duration_target_sec required")
    for field in ("max_attempts_per_shot", "min_scenes"):
        if type(config.get(field)) is not int or config[field] < 1:
            errors.append(f"Positive integer config.{field} required")
    for field in ("allow_self_review", "refine", "subtitles"):
        if type(config.get(field)) is not bool:
            errors.append(f"Boolean config.{field} required")

    def indexed(field):
        items = plan.get(field)
        if not isinstance(items, list) or not items or not all(isinstance(i, dict) for i in items):
            errors.append(f"{field} must be a nonempty object list")
            return {}
        result = {}
        for item in items:
            key = item.get("id")
            if not nonempty(key):
                errors.append(f"{field}: nonempty id required")
            elif key in result:
                errors.append(f"{field}: duplicate id {key}")
            else:
                result[key] = item
        return result

    assets = indexed("episode_assets")
    for key, asset in assets.items():
        if not nonempty(asset.get("kind")) or not nonempty(asset.get("description")):
            errors.append(f"{key}: asset kind and design description required")
    shots = indexed("shots")
    groups = indexed("storyboard_groups")
    turns = {}
    if plan.get("turns") != []:
        turns = indexed("turns")
    research = plan.get("research")
    if not isinstance(research, dict) or research.get("kind") not in ("factual", "fictional"):
        errors.append("Research kind must be factual or fictional")
    elif research["kind"] == "factual":
        sources = research.get("sources")
        if not isinstance(sources, list) or not sources or not all(
            isinstance(s, dict) and nonempty(s.get("claim")) and
            isinstance(s.get("url"), str) and s["url"].startswith(("https://", "http://"))
            for s in sources
        ):
            errors.append("Factual research needs source URLs and supported claims")
        if research.get("uncertainties") != []:
            errors.append("Resolve factual uncertainties before generation")
    for key, turn in turns.items():
        speaker, listener = turn.get("speaker"), turn.get("listener")
        if (speaker not in assets or listener not in assets or speaker == listener
                or assets[speaker].get("kind") == "location" or assets[listener].get("kind") == "location"):
            errors.append(f"{key}: speaker/listener must be two distinct non-location assets")
        for field in ("line", "normalized_line", "function", "knowledge_delta"):
            if not nonempty(turn.get(field)):
                errors.append(f"{key}: {field} required")
        if turn.get("typo_checked") is not True or turn.get("speech_checked") is not True:
            errors.append(f"{key}: speech checks not completed")
    for key in sorted({t.get("speaker") for t in turns.values()} & set(assets)):
        voice = assets[key].get("voice")
        if not isinstance(voice, dict) or voice.get("source") not in ("generated", "provided"):
            errors.append(f"{key}: speaking asset requires a voice plan with source generated or provided")
        elif voice.get("source") == "generated" and not (nonempty(voice.get("description")) and nonempty(voice.get("sample_text"))):
            errors.append(f"{key}: generated voice needs description and sample_text")
        elif voice.get("source") == "provided" and not nonempty(voice.get("file")):
            errors.append(f"{key}: provided voice requires the source file")
    scenes, used_turns = set(), set()
    for key, shot in shots.items():
        scene = shot.get("scene_id")
        if not isinstance(scene, str) or scene not in assets or assets[scene].get("kind") != "location":
            errors.append(f"{key}: unknown location asset")
        else:
            scenes.add(scene)
        if not positive(shot.get("duration")):
            errors.append(f"{key}: positive duration required")
        refs = shot.get("required_assets")
        if not isinstance(refs, list) or not all(isinstance(r, str) and r in assets for r in refs):
            errors.append(f"{key}: invalid required_assets")
        cast = shot.get("visible_characters", [])
        if not isinstance(cast, list) or any(c not in assets or assets[c].get("kind") == "location" for c in cast):
            errors.append(f"{key}: visible_characters must contain non-location asset IDs")
        for field in ("action_start", "action_process", "action_end", "camera", "continuity_in", "continuity_out", "scene_function", "shot_pattern"):
            if not nonempty(shot.get(field)):
                errors.append(f"{key}: {field} required")
        prompt = shot.get("prompt", {})
        if not isinstance(prompt, dict) or not all(nonempty(prompt.get(f)) for f in ("reference_map", "execution")):
            errors.append(f"{key}: reference mapping and execution prompt required")
            prompt = {}
        mode = shot.get("audio_mode")
        if mode == "h3_dialogue":
            turn_id = shot.get("turn_id")
            turn = turns.get(turn_id) if isinstance(turn_id, str) else None
            if turn is None:
                errors.append(f"{key}: unknown dialogue turn")
                continue
            used_turns.add(turn_id)
            for field in ("speaker", "listener", "normalized_line"):
                if shot.get(field) != turn.get(field):
                    errors.append(f"{key}: {field} differs from turn")
            speaker = shot.get("speaker")
            if nonempty(shot.get("normalized_line")) and shot["normalized_line"] not in prompt.get("execution", ""):
                errors.append(f"{key}: prompt missing exact dialogue")
            dominance = shot.get("visual_dominance", {})
            if not isinstance(dominance, dict) or dominance.get("primary") != speaker or dominance.get("secondary") != shot.get("listener") or dominance.get("lighting_priority") != "primary":
                errors.append(f"{key}: speaker must be visually primary")
            if not nonempty(shot.get("listener_face_policy")) or shot.get("listener_mouth") != "closed":
                errors.append(f"{key}: listener performance unspecified")
        elif mode in ("silent", "pre_recorded_narration"):
            if any(shot.get(f) for f in ("turn_id", "speaker", "listener", "normalized_line")):
                errors.append(f"{key}: silent H3 inputs must not have speaker or dialogue")
            if mode == "pre_recorded_narration" and (
                not nonempty(shot.get("narration_text")) or not nonempty(shot.get("narration_audio")) or
                not positive(shot.get("narration_duration")) or shot["narration_duration"] > shot.get("duration", 0)
            ):
                errors.append(f"{key}: narration metadata missing or longer than shot")
        else:
            errors.append(f"{key}: unknown audio_mode")
    if set(turns) != used_turns:
        errors.append("Every turn must appear in a dialogue shot")
    if type(config.get("min_scenes")) is int and len(scenes) < config["min_scenes"] and not nonempty(config.get("single_scene_reason")):
        errors.append("Too few scenes without an explanation")
    covered = []
    for key, group in groups.items():
        ids = group.get("shot_ids")
        if group.get("panels") != 4 or not isinstance(ids, list) or len(ids) != 4:
            errors.append(f"{key}: this pipeline requires exactly 4 shots per grid")
            continue
        for shot_id in ids:
            if not isinstance(shot_id, str) or shot_id not in shots:
                errors.append(f"{key}: unknown shot id")
            else:
                covered.append(shot_id)
                if shots[shot_id].get("scene_id") != group.get("scene_id"):
                    errors.append(f"{key}: mixed scene group")
    if len(covered) != len(set(covered)) or set(covered) != set(shots):
        errors.append("Storyboard groups must cover each shot exactly once")
    errors.extend(validate_qa(plan.get("preproduction_qa"), "preproduction", plan.get("revision"), list(shots), config.get("allow_self_review") is True))
    return errors


def validate_gate(plan, root, stage, shot_id=None):
    """Check cumulative production evidence, not merely planned asset IDs."""
    errors = validate_plan(plan)
    if errors:
        return errors
    root = Path(root).resolve()
    progress = plan.get("media_progress", {})
    revision = plan["revision"]
    allow_self = plan["config"]["allow_self_review"]

    def record(section, key, capability=None, parent=None, qa_stage="image", ids=None):
        value = progress.get(section, {}).get(key)
        if not isinstance(value, dict):
            errors.append(f"{section}.{key}: real production evidence missing")
            return {}
        try:
            path = (root / value["path"]).resolve()
            if not path.is_relative_to(root) or not path.is_file() or not path.stat().st_size:
                raise ValueError("missing, empty or outside run_root")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != value.get("sha256"):
                raise ValueError("SHA256 mismatch")
        except (KeyError, OSError, TypeError, ValueError) as exc:
            errors.append(f"{section}.{key}: invalid artifact: {exc}")
        own_revision = value.get("revision")
        if type(own_revision) is not int or not 1 <= own_revision <= revision or not nonempty(value.get("job_id")):
            errors.append(f"{section}.{key}: artifact revision and gateway job_id required")
        if section in ("drafts", "references", "grids", "panels", "videos") and value.get("spec_sha256") != specification(plan, section, key):
            errors.append(f"{section}.{key}: changed design/shot specification")
        if capability and value.get("capability_id") != capability:
            errors.append(f"{section}.{key}: requires {capability}")
        if parent is not None and value.get("parent_sha256") != parent:
            errors.append(f"{section}.{key}: wrong or stale source artifact")
        report = value.get("qa")
        errors.extend(validate_qa(report, qa_stage, own_revision, ids or [key], allow_self))
        if not isinstance(report, dict) or report.get("input_sha256", {}).get(value.get("path")) != value.get("sha256"):
            errors.append(f"{section}.{key}: QA not bound to artifact hash")
        return value

    def submitted(section, key, value):
        request = value.get("request", {})
        errors.extend(f"{section}.{key}: {e}" for e in check_request(plan, section, key, request))
        capability, sources = request_contract(plan, section, key)
        receipt = value.get("gateway_inputs", {})
        expected = [(kind, s.get("upload_id"), s.get("sha256")) for kind, s in sources]
        actual = [(i.get("type"), i.get("upload_id"), i.get("sha256")) for i in receipt.get("items", [])]
        if (receipt.get("job_id") != value.get("job_id") or actual != expected
                or any(not nonempty(h) for _, _, h in expected)):
            errors.append(f"{section}.{key}: gateway input receipt must prove actual source uploads and hashes")

    try:
        if not isinstance(progress, dict):
            raise ValueError("media_progress must be an object")
        ranks = {"drafts": 0, "references": 1, "grids": 2, "storyboard": 3, "compiled": 4, "media": 5, "selected": 6, "final": 7}
        rank = ranks[stage]
        speaking = {s["speaker"] for s in plan["shots"] if s.get("audio_mode") == "h3_dialogue"}
        for asset in plan["episode_assets"]:
            key = asset["id"]
            draft = record("drafts", key, "image.qwen.text_to_image")
            submitted("drafts", key, draft)
            if rank >= 1:
                capability = "image.qwen.image_to_image" if asset["kind"] == "location" else "image.qwen.character"
                reference = record("references", key, capability, draft.get("sha256", ""))
                submitted("references", key, reference)
                if capability == "image.qwen.character" and reference.get("request", {}).get("settings", {}).get("ratio") != "16:9":
                    errors.append(f"{key}: character/multiview sheets require settings.ratio=16:9")
                if not nonempty(reference.get("upload_id")):
                    errors.append(f"{key}: locked reference upload_id required")
                if key in speaking:
                    voice = progress.get("voices", {}).get(key)
                    if not isinstance(voice, dict):
                        errors.append(f"voices.{key}: reviewed voice reference evidence missing")
                    else:
                        errors.extend(validate_reviewed_file(voice, root, "voice", voice.get("revision"), [key], allow_self))
                        if voice.get("spec_sha256") != specification(plan, "voices", key):
                            errors.append(f"voices.{key}: changed voice specification")
                        if not nonempty(voice.get("upload_id")):
                            errors.append(f"voices.{key}: locked voice upload_id required")
        if rank >= 2:
            for group in plan["storyboard_groups"]:
                grid = record("grids", group["id"], "image.qwen.storyboard_4", ids=group["shot_ids"])
                submitted("grids", group["id"], grid)
                keys = grid_keys(plan, group)
                expected = {key: source.get("sha256") for key, source in zip(keys, reference_sources(plan, keys))}
                if grid.get("reference_sha256") != expected:
                    errors.append(f"{group['id']}: grid must use locked reference assets")
                for index, key in enumerate(group["shot_ids"] if rank >= 3 else []):
                    panel = record("panels", key, "image.split", grid.get("sha256", ""))
                    submitted("panels", key, panel)
                    if panel.get("panel_index") != index or not nonempty(panel.get("upload_id")):
                        errors.append(f"{key}: ordered split panel and upload_id required")
        if rank >= 4:
            selected = [s for s in plan["shots"] if shot_id is None or s["id"] == shot_id]
            if not selected:
                errors.append("Unknown shot_id")
            for shot in selected:
                key = shot["id"]
                compilation = progress.get("compilations", {}).get(key, {})
                request = compilation.get("request", {})
                errors.extend(f"{key}: {e}" for e in check_request(plan, "compilations", key, request))
                response = compilation.get("response", {})
                inputs = request.get("inputs", [])
                panel = progress.get("panels", {}).get(key, {})
                expected_images = [panel.get("upload_id")]
                expected_images.extend(progress.get("references", {}).get(c, {}).get("upload_id") for c in visible_characters(shot))
                if shot["audio_mode"] == "h3_dialogue":
                    expected_audio = progress.get("voices", {}).get(shot["speaker"], {}).get("upload_id")
                    if not nonempty(expected_audio) or [i.get("upload_id") for i in inputs if i.get("type") == "audio"] != [expected_audio]:
                        errors.append(f"{key}: wrong or missing speaker voice reference")
                elif any(i.get("type") == "audio" for i in inputs):
                    errors.append(f"{key}: silent H3 shot must not receive audio reference")
                asset_ids = list(dict.fromkeys([shot["scene_id"], *shot["required_assets"]]))
                expected_images.extend(progress.get("references", {}).get(a, {}).get("upload_id") for a in asset_ids)
                if (not all(nonempty(i) for i in expected_images)
                        or [i.get("upload_id") for i in inputs if i.get("type") == "image"] != expected_images):
                    errors.append(f"{key}: split panel, visible character boards and locked assets must be supplied in order")
                if (compilation.get("spec_sha256") != specification(plan, "compilations", key) or request.get("prompt_processing") != "compile"
                        or request.get("capability_id") != "video.reference"
                        or request.get("project_id") != plan["config"]["project_id"]
                        or request.get("prompt") != shot["prompt"]["execution"]
                        or not inputs or inputs[0].get("upload_id") != panel.get("upload_id")):
                    errors.append(f"{key}: H3 compile request must use current project and split panel")
                execution = response.get("confirmation", {}).get("execution_prompt_en", response.get("result", {}).get("optimized_prompt", ""))
                fields = ("subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape", "non_diegetic_music")
                if (not nonempty(response.get("id")) or response.get("model_id") != "minimax-h3"
                        or response.get("collaboration_mode") != "quick"
                        or response.get("status") != "awaiting_confirmation"
                        or not isinstance(execution, str) or not all(f in execution for f in fields)):
                    errors.append(f"{key}: ready H3 conversion response required; direct is forbidden")
                if shot.get("normalized_line") and shot["normalized_line"] not in execution:
                    errors.append(f"{key}: H3 conversion lost exact dialogue")
                if rank >= 5:
                    video = record("videos", key, "video.reference", qa_stage="media")
                    capability, sources = request_contract(plan, "compilations", key)
                    receipt = video.get("gateway_inputs", {})
                    actual = [(i.get("type"), i.get("upload_id"), i.get("sha256")) for i in receipt.get("items", [])]
                    expected = [(kind, s.get("upload_id"), s.get("sha256")) for kind, s in sources]
                    if receipt.get("job_id") != video.get("job_id") or actual != expected:
                        errors.append(f"{key}: video gateway inputs differ from compiled references")
                    if video.get("compiled_sha256") != fingerprint(execution):
                        errors.append(f"{key}: video must bind the exact compiled prompt")
                    submission = compilation.get("submission", {})
                    if (submission.get("collaboration_id") != response.get("id")
                            or submission.get("job_id") != video.get("job_id")):
                        errors.append(f"{key}: video must come from recorded H3 session confirmation")
        if rank >= 6:
            selected = progress.get("selected", {})
            if set(selected) != {s["id"] for s in plan["shots"]}:
                errors.append("Select exactly one reviewed video per shot")
            for shot in plan["shots"]:
                key = shot["id"]
                parent = progress.get("videos", {}).get(key, {})
                seen = {parent.get("job_id"): parent}
                for entry in progress.get("refinements", {}).get(key, []):
                    parent = seen.get(entry.get("parent_job_id"), {})
                    if entry.get("job_id") in seen or not parent or entry.get("parent_sha256") != parent.get("sha256"):
                        errors.append(f"{key}: invalid refinement parent chain")
                    seen[entry.get("job_id")] = entry
                    # Same artifact/QA checks, without mutating the initial video ledger.
                    wrapped = {**plan, "media_progress": {**progress, "videos": {**progress["videos"], key: entry}}}
                    errors.extend(validate_reviewed_file(entry, root, "media", entry.get("revision"), [key], allow_self))
                    if entry.get("spec_sha256") != specification(wrapped, "videos", key):
                        errors.append(f"{key}: stale refinement specification")
                    if not nonempty(entry.get("action_id")):
                        errors.append(f"{key}: refinement action_id required")
                    if type(entry.get("revision")) is not int or not 1 <= entry["revision"] <= revision:
                        errors.append(f"{key}: invalid refinement revision")
                    receipt = entry.get("gateway_job", {})
                    if (receipt.get("id") != entry.get("job_id") or receipt.get("status") != "completed"
                            or receipt.get("parent_job_id") != entry.get("parent_job_id")):
                        errors.append(f"{key}: completed gateway refinement parent receipt required")
                candidates = [progress.get("videos", {}).get(key, {}), *progress.get("refinements", {}).get(key, [])]
                chosen = next((v for v in candidates if v.get("job_id") == selected.get(key)), None)
                if chosen is None:
                    errors.append(f"{key}: selected video missing from reviewed chain")
        if rank >= 7:
            composition = progress.get("composition", {})
            errors.extend(validate_composition(plan, root, composition))
            final = progress.get("final", {})
            errors.extend(validate_reviewed_file(final, root, "final", revision, [s["id"] for s in plan["shots"]], allow_self))
            if final.get("selection_sha256") != selection_hash(plan):
                errors.append("Final output uses stale selected media")
            if final.get("compose_sha256") != fingerprint(composition):
                errors.append("Final QA must bind the actual film-studio composition evidence")
            if (root / final.get("path", "")).resolve() != (root / composition.get("output", {}).get("path", "")).resolve():
                errors.append("Final file differs from the downloaded render")
    except (KeyError, TypeError, ValueError, AttributeError, OSError) as exc:
        errors.append(f"Malformed gate evidence: {exc}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "qa", "gate", "request"):
        p = sub.add_parser(name)
        p.add_argument("path", type=Path)
        if name == "gate":
            p.add_argument("--stage", choices=("drafts", "references", "grids", "storyboard", "compiled", "media", "selected", "final"), required=True)
            p.add_argument("--shot-id")
        if name == "request":
            p.add_argument("--operation", choices=("drafts", "references", "grids", "panels", "compilations"), required=True)
            p.add_argument("--key", required=True)
            p.add_argument("--inputs", type=Path, required=True)
        if name == "qa":
            p.add_argument("--stage", choices=CHECKS, required=True)
            p.add_argument("--revision", type=int, required=True)
            p.add_argument("--shots", nargs="+", required=True)
            p.add_argument("--allow-self-review", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "qa":
            data = json.loads(args.path.read_text(encoding="utf-8"))
        else:
            from preproduction import load_production
            data = load_production(args.path)
        if args.command == "gate":
            errors = validate_gate(data, args.path.parent, args.stage, args.shot_id)
        elif args.command == "request":
            errors = validate_request(data, args.path.parent, args.operation, args.key, json.loads(args.inputs.read_text(encoding="utf-8")))
        else:
            errors = validate_plan(data) if args.command == "plan" else validate_qa(data, args.stage, args.revision, args.shots, args.allow_self_review)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors = [str(exc)]
    print(json.dumps({"status": "FAIL" if errors else "PASS", "errors": errors}, ensure_ascii=False))
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
