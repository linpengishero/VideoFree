"""Build a small execution index from the ten reviewed production documents."""

import argparse
import hashlib
import json
from pathlib import Path
import re


DOCUMENTS = (
    "task_config.yaml", "research_notes.md", "dialogue_script.yaml",
    "production_plan.md", "asset_manifest.yaml", "scene_plan.yaml",
    "storyboard_groups.yaml", "asset_prompts.md", "video_prompts.yaml",
    "preproduction_qa.md",
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def structured(path):
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError(f"Empty document: {path.name}")
    if path.suffix == ".md":
        blocks = re.findall(r"^```(?:yaml|json)\s*\n(.*?)^```\s*$", text, re.M | re.S)
        if len(blocks) != 1:
            raise ValueError(f"{path.name}: exactly one yaml/json data block required")
        text = blocks[0]
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as exc:
            raise ValueError("Install OpenMontage requirements (PyYAML), using the same Python for skill scripts") from exc
        try:
            value = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ValueError(f"{path.name}: invalid YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name}: document data must be an object")
    return value


def by_id(values, field="id"):
    result = {}
    for value in values:
        key = value[field]
        if key in result:
            raise ValueError(f"Duplicate {field}: {key}")
        result[key] = value
    return result


def assemble(root):
    root = Path(root).resolve()
    for name in DOCUMENTS:
        path = root / name
        if not path.is_file() or not path.resolve().is_relative_to(root) or not path.read_text(encoding="utf-8-sig").strip():
            raise ValueError(f"Missing/empty/unsafe final document: {name}")
    data = {name: structured(root / name) for name in DOCUMENTS if name != "production_plan.md"}
    task = data["task_config.yaml"]
    review = data["preproduction_qa.md"]
    hashes = {name: digest(root / name) for name in DOCUMENTS if name != "preproduction_qa.md"}
    if review.get("source_sha256") != hashes:
        raise ValueError("Preproduction QA must bind the actual nine source documents; review changed files before indexing")
    turns = data["dialogue_script.yaml"]["turns"]
    turn_map = by_id(turns)
    assets = data["asset_manifest.yaml"]["episode_assets"]
    asset_map = by_id(assets)
    prompts = by_id(data["asset_prompts.md"]["prompts"], "asset_id")
    if set(prompts) != set(asset_map):
        raise ValueError("Asset prompts must cover every episode asset exactly once")
    for asset in assets:
        prompt = prompts[asset["id"]]
        if not all(isinstance(prompt.get(k), str) and prompt[k].strip() for k in ("draft", "reference")):
            raise ValueError("Each asset needs final draft and reference prompts")
        asset["prompts"] = {k: prompt[k] for k in ("draft", "reference")}
    scenes = data["scene_plan.yaml"]["scenes"]
    scene_map = by_id(scenes)
    if set(scene_map) != {a["id"] for a in assets if a["kind"] == "location"}:
        raise ValueError("Scene plan must cover the location assets exactly once")
    for key, scene in scene_map.items():
        asset_map[key]["scene_design"] = scene
    story = data["storyboard_groups.yaml"]
    shots = story["shots"]
    shot_map = by_id(shots)
    videos = by_id(data["video_prompts.yaml"]["shots"], "shot_id")
    if set(videos) != set(shot_map):
        raise ValueError("Video prompts must cover every storyboard shot exactly once")
    for shot in shots:
        if not isinstance(shot.get("storyboard_prompt"), str) or not shot["storyboard_prompt"].strip():
            raise ValueError(f"{shot['id']}: final four-panel image description required")
        for field in ("prompt", "speaker", "listener", "normalized_line", "voice_asset"):
            if field in shot:
                raise ValueError(f"{shot['id']}: {field} belongs to the script/video document, not storyboard")
        if shot["audio_mode"] == "h3_dialogue":
            turn = turn_map[shot["turn_id"]]
            shot.update({k: turn[k] for k in ("speaker", "listener", "normalized_line")})
            shot["voice_asset"] = f"{turn['speaker']}/voice_reference.flac"
        shot["prompt"] = {k: videos[shot["id"]][k] for k in ("reference_map", "execution")}
        shot["scene_design"] = scene_map[shot["scene_id"]]
    plan = {"schema_version": 1, "revision": task["revision"], "config": task["config"],
            "research": data["research_notes.md"]["research"], "turns": turns,
            "episode_assets": assets, "shots": shots, "storyboard_groups": story["storyboard_groups"],
            "preproduction_qa": review["qa"]}
    from validate import validate_plan
    errors = validate_plan(plan)
    if errors:
        raise ValueError("Final package failed: " + "; ".join(errors))
    sources = {name: {"path": name, "sha256": digest(root / name)} for name in DOCUMENTS}
    return plan, sources


def build_index(root):
    root = Path(root).resolve()
    plan, sources = assemble(root)
    output = root / "production.json"
    old = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    if old and (old.get("schema_version") != 2 or old.get("binding") != {k: plan["config"][k] for k in ("project_id", "workspace_id")}):
        raise ValueError("Existing index has a different project/format; use a separate run directory")
    if old and (plan["revision"] < old["revision"] or (plan["revision"] == old["revision"] and sources != old["sources"])):
        raise ValueError("Changed source documents require a new revision and current QA")
    index = {"schema_version": 2, "revision": plan["revision"], "sources": sources,
             "binding": {k: plan["config"][k] for k in ("project_id", "workspace_id")},
             "media_progress": old.get("media_progress", {})}
    if old.get("h3_delegation"):
        index["h3_delegation"] = old["h3_delegation"]
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)
    return index


def load_production(path):
    path = Path(path).resolve()
    index = json.loads(path.read_text(encoding="utf-8"))
    if index.get("schema_version") != 2:
        raise ValueError("Build production.json from the ten final documents; handwritten execution snapshots are not final packages")
    root = path.parent
    sources = index.get("sources", {})
    if set(sources) != set(DOCUMENTS):
        raise ValueError("Index must contain all ten final documents")
    for name in DOCUMENTS:
        document = root / name
        if not document.resolve().is_relative_to(root):
            raise ValueError(f"Unsafe final document: {name}")
        if sources[name].get("path") != name or digest(document) != sources[name].get("sha256"):
            raise ValueError(f"Final document changed: {name}; revise, review and rebuild the index")
    plan, current = assemble(root)
    if current != sources or index["revision"] != plan["revision"] or index["binding"] != {k: plan["config"][k] for k in ("project_id", "workspace_id")}:
        raise ValueError("Index does not match the final package")
    plan["media_progress"] = index.get("media_progress", {})
    if "h3_delegation" in index:
        plan["h3_delegation"] = index["h3_delegation"]
    return plan


def _asset_card(asset, prompt_kind=None):
    card = {key: asset[key] for key in ("id", "kind", "description", "scene_design") if key in asset}
    if prompt_kind and asset.get("prompts", {}).get(prompt_kind):
        card["prompt"] = asset["prompts"][prompt_kind]
    elif "prompts" in asset:
        card["prompts"] = asset["prompts"]
    return card


def context_card(plan, stage, key=None):
    """Return the smallest deterministic context needed by one production stage."""
    config = plan["config"]
    base = {"revision": plan["revision"], "project_id": config["project_id"],
            "workspace_id": config["workspace_id"], "title": config["title"],
            "aspect": config["aspect"]}
    turns = {turn["id"]: turn for turn in plan["turns"]}
    assets = {asset["id"]: asset for asset in plan["episode_assets"]}
    shots = {shot["id"]: shot for shot in plan["shots"]}
    if stage == "script":
        return {**base, "research": plan["research"], "turns": plan["turns"]}
    if stage == "assets":
        return {**base, "turns": [{"id": t["id"], "speaker": t["speaker"],
                                   "listener": t["listener"], "line": t["normalized_line"]}
                                  for t in plan["turns"]],
                "episode_assets": [_asset_card(asset) for asset in plan["episode_assets"]]}
    if stage == "storyboard":
        return {**base,
                "turns": [{"id": t["id"], "speaker": t["speaker"],
                           "listener": t["listener"], "line": t["normalized_line"]}
                          for t in plan["turns"]],
                "episode_assets": [_asset_card(asset) for asset in plan["episode_assets"]],
                "shots": [{field: shot[field] for field in (
                    "id", "turn_id", "scene_id", "scene_function", "shot_pattern",
                    "required_assets", "action_start", "action_process", "action_end",
                    "camera", "continuity_in", "continuity_out", "storyboard_prompt")
                    if field in shot} for shot in plan["shots"]],
                "storyboard_groups": plan["storyboard_groups"]}
    if stage == "preproduction_qa":
        return {**base, "source_documents": plan.get("source_documents", []),
                "counts": {"turns": len(plan["turns"]), "assets": len(plan["episode_assets"]),
                           "shots": len(plan["shots"]), "storyboard_groups": len(plan["storyboard_groups"])},
                "qa": plan["preproduction_qa"]}
    if stage == "media":
        if key not in shots:
            raise ValueError("media context requires a shot id")
        shot = shots[key]
        media_fields = ("id", "turn_id", "speaker", "listener", "normalized_line", "audio_mode",
                        "duration", "scene_id", "scene_function", "shot_pattern", "required_assets",
                        "action_start", "action_process", "action_end", "camera", "continuity_in",
                        "continuity_out", "visual_dominance", "listener_face_policy", "listener_mouth",
                        "voice_asset")
        shot_card = {field: shot[field] for field in media_fields if field in shot}
        related = [shots[item] for item in (shot.get("previous_shot_id"), key, shot.get("next_shot_id"))
                   if item in shots]
        related_assets = {asset_id for item in related for asset_id in item.get("required_assets", [])}
        related_assets.update(item.get("scene_id") for item in related)
        related_assets.update(item.get("speaker") for item in related if item.get("speaker"))
        return {**base, "shot": shot_card, "turn": turns.get(shot.get("turn_id")),
                "related_shots": [{"id": item["id"], "continuity_in": item.get("continuity_in"),
                                   "continuity_out": item.get("continuity_out")} for item in related if item["id"] != key],
                "assets": [_asset_card(assets[item], "reference") for item in related_assets if item in assets],
                "media_progress": {section: values.get(key) for section, values in plan.get("media_progress", {}).items()
                                    if isinstance(values, dict) and key in values}}
    if stage == "final":
        return {**base, "turns": [{"id": t["id"], "line": t["normalized_line"]} for t in plan["turns"]],
                "shots": [{"id": s["id"], "duration": s["duration"], "turn_id": s.get("turn_id"),
                           "audio_mode": s["audio_mode"]} for s in plan["shots"]],
                "selected": plan.get("media_progress", {}).get("selected", {}),
                "mix": plan.get("media_progress", {}).get("mix", {})}
    raise ValueError(f"Unknown context stage: {stage}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("hashes", "build", "context"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--stage", choices=("script", "assets", "storyboard", "preproduction_qa", "media", "final"))
    parser.add_argument("--key")
    args = parser.parse_args()
    if args.command == "hashes":
        result = {name: digest(args.root / name) for name in DOCUMENTS if name != "preproduction_qa.md"}
    elif args.command == "build":
        result = build_index(args.root)
    else:
        if not args.stage:
            parser.error("context requires --stage")
        result = context_card(load_production(args.root / "production.json"), args.stage, args.key)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        parser_result = {"status": "BLOCKED", "error": str(exc)}
        print(json.dumps(parser_result, ensure_ascii=False))
        raise SystemExit(1)
