"""Validate production dependencies before invoking videofree MCP tools."""

import argparse
import json
import os
from pathlib import Path
import sys
import urllib.request
import uuid

from validate import fingerprint, request_contract, validate_confirmation, validate_gate, validate_request

PROGRESS_STAGES = (("preproduction", "定稿包与前期QA"), ("drafts", "主体草稿"), ("references", "定版参考与声音"),
                   ("grids", "四宫格分镜图"), ("storyboard", "分镜单格"), ("compiled", "H3编译确认"),
                   ("media", "镜头草稿QA"), ("selected", "版本选定"), ("final", "成片合成"))
PROGRESS_STATUSES = {"pending", "running", "completed", "failed", "blocked", "skipped"}
ARCHIVE_TYPES = ("script", "storyboard", "prompts", "characters", "scenes", "final-package", "continuity")


def make_request(plan, operation, key, attempt=1):
    if type(attempt) is not int or not 1 <= attempt <= plan["config"]["max_attempts_per_shot"]:
        raise ValueError("Attempt exceeds the approved retry limit")
    capability, sources = request_contract(plan, operation, key)
    settings = dict(plan["config"].get("generation_settings", {}).get(operation, {}))
    settings["ratio"] = "16:9" if capability == "image.qwen.character" else plan["config"]["aspect"]
    if operation in ("drafts", "references"):
        asset = next(a for a in plan["episode_assets"] if a["id"] == key)
        prompt = asset["prompts"]["draft" if operation == "drafts" else "reference"]
    elif operation == "grids":
        group = next(g for g in plan["storyboard_groups"] if g["id"] == key)
        shots = {s["id"]: s for s in plan["shots"]}
        positions = ("top-left", "top-right", "bottom-left", "bottom-right")
        prompt = ("Exactly four panels in one strict 2 by 2 grid, read left to right, then top to bottom. "
                  + " ".join(f"Panel {index} ({position}): {shots[shot_id]['storyboard_prompt']}"
                             for index, (position, shot_id) in enumerate(zip(positions, group["shot_ids"]), 1)))
    elif operation == "panels":
        prompt = "Split the reference into four ordered panels."
    else:
        shot = next(s for s in plan["shots"] if s["id"] == key)
        prompt = shot["prompt"]["execution"]
        settings["duration"] = shot["duration"]
    arguments = {"capability_id": capability, "prompt": prompt, "settings": settings,
                 "inputs": [{"type": kind, "upload_id": value.get("upload_id"), "role": "reference"} for kind, value in sources],
                 "prompt_processing": "compile" if operation == "compilations" else "direct",
                 "project_id": plan["config"]["project_id"]}
    arguments["idempotency_key"] = f"dialogue-{fingerprint(arguments)}-{attempt}"
    return arguments


def call(endpoint, name, arguments):
    payload = {"jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("VIDEOFREE_API_TOKEN", "")
    if token:
        headers["x-api-token"] = token
    request = urllib.request.Request(endpoint, json.dumps(payload, ensure_ascii=False).encode(), headers)
    with urllib.request.urlopen(request, timeout=180) as response:
        result = json.load(response)
    if "error" in result:
        raise ValueError(result["error"])
    result = result["result"]
    if result.get("isError"):
        raise ValueError(result)
    return json.loads(next(item["text"] for item in result["content"] if item["type"] == "text"))


def execute(plan, root, endpoint, operation, key, arguments, caller=call):
    root = Path(root)
    if operation == "confirm":
        errors = validate_confirmation(plan, root, key, arguments)
        name = "confirm_collaboration"
    elif operation == "continue":
        errors = validate_gate(plan, root, "storyboard")
        compilation = plan.get("media_progress", {}).get("compilations", {}).get(key, {})
        response = compilation.get("response", {})
        if (response.get("status") != "needs_input" or arguments.get("session_id") != response.get("id")
                or not arguments.get("answer") or arguments.get("prompt_processing") != "compile"):
            errors.append("Continue only the recorded needs_input session with an answer")
        name = "submit_generation"
    else:
        errors = validate_request(plan, root, operation, key, arguments)
        name = "submit_generation"
    if operation == "continue" and arguments.get("project_id") != plan["config"]["project_id"]:
        errors.append("Wrong project_id")
    if errors:
        raise ValueError("Pre-submit gate failed: " + "; ".join(errors))
    event = {"operation": operation, "key": key, "tool": name, "arguments": arguments,
             "spec": fingerprint(arguments)}
    ledger = root / "jobs.jsonl"
    events = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()] if ledger.exists() else []
    if any(e.get("arguments", {}).get("idempotency_key") == arguments.get("idempotency_key")
           and e.get("spec") != event["spec"] for e in events):
        raise ValueError("Idempotency key already belongs to a different request")
    previous = next((e for e in reversed(events) if e.get("spec") == event["spec"] and e.get("event") == "submitted"), None)
    if previous:
        return previous["response"]
    with ledger.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({**event, "event": "intent"}, ensure_ascii=False) + "\n")
    result = caller(endpoint, name, arguments)
    with ledger.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({**event, "event": "submitted", "response": result}, ensure_ascii=False) + "\n")
    return result


def archive_content(plan, root, key, override):
    root = Path(root)
    if key == "continuity":
        if not isinstance(override, dict) or set(override) != {"decisions", "completed", "blockers", "next_action"} \
                or not all(isinstance(value, str) for value in override.values()):
            raise ValueError("continuity requires --inputs with string decisions/completed/blockers/next_action")
        return override
    if key == "script":
        return (root / "dialogue_script.yaml").read_text(encoding="utf-8-sig")
    selected = plan.get("media_progress", {}).get("selected", {})
    if key == "storyboard":
        shots = []
        for shot in plan["shots"]:
            item = {"id": shot["id"], "scene": shot["scene_id"], "scene_id": shot["scene_id"],
                    "duration": shot["duration"], "audio_mode": shot["audio_mode"], "camera": shot["camera"],
                    "visual": shot["storyboard_prompt"], "storyboard_prompt": shot["storyboard_prompt"],
                    "action_start": shot["action_start"], "action_process": shot["action_process"],
                    "action_end": shot["action_end"], "required_assets": shot["required_assets"],
                    "status": "selected" if shot["id"] in selected else "planned"}
            if shot["audio_mode"] == "h3_dialogue":
                item.update(turn_id=shot["turn_id"], speaker=shot["speaker"], listener=shot["listener"],
                            dialogue=shot["normalized_line"])
            if shot["id"] in selected:
                item["selected_job_id"] = selected[shot["id"]].get("job_id")
            shots.append(item)
        groups = [{"id": group["id"], "kind": "sequence", "shot_ids": group["shot_ids"]}
                  for group in plan["storyboard_groups"]]
        return {"notes": f"定稿revision {plan['revision']}", "shots": shots, "groups": groups}
    if key == "prompts":
        items = [{"id": f"img-{asset['id']}", "kind": "image", "purpose": "planned", "target_id": asset["id"],
                  "draft_zh": asset["prompts"]["draft"], "execution": asset["prompts"]["reference"]}
                 for asset in plan["episode_assets"]]
        items += [{"id": shot["id"], "kind": "video", "purpose": "planned", "target_id": shot["id"],
                   "execution": shot["prompt"]["execution"]} for shot in plan["shots"]]
        return {"notes": f"定稿revision {plan['revision']}；image条目draft/execution对应asset_prompts的draft/reference", "items": items}
    if key == "characters":
        kind_map = {"character": "character", "object": "prop"}
        items = []
        for asset in plan["episode_assets"]:
            if asset["kind"] == "location":
                continue
            items.append({"id": asset["id"], "name": asset["id"], "kind": kind_map.get(asset["kind"], "other"),
                          "description": asset["description"]})
            if asset.get("voice"):
                items.append({"id": f"{asset['id']}-voice", "name": f"{asset['id']} 声音计划", "kind": "voice",
                              "description": json.dumps(asset["voice"], ensure_ascii=False)})
        return {"notes": f"定稿revision {plan['revision']}；voice条目对应asset_manifest的voice计划", "items": items}
    if key == "scenes":
        items = [{"id": asset["id"], "name": asset["id"], "kind": "scene", "description": asset["description"],
                  "consistency": json.dumps(asset["scene_design"], ensure_ascii=False)}
                 for asset in plan["episode_assets"] if asset["kind"] == "location"]
        return {"notes": f"定稿revision {plan['revision']}", "items": items}
    if key == "final-package":
        config, qa = plan["config"], plan["preproduction_qa"]
        sources = json.loads((root / "production.json").read_text(encoding="utf-8")).get("sources", {})
        return {"summary": (f"{config['title']}：revision {plan['revision']}，画幅{config['aspect']}，"
                            f"目标{config['duration_target_sec']}秒，{len(plan['turns'])} turn、"
                            f"{len(plan['episode_assets'])}资产、{len(plan['shots'])}镜头"),
                "deliverables": "\n".join(f"{name}  {info.get('sha256')}" for name, info in sorted(sources.items())),
                "acceptance": (f"前期QA {qa['status']}（{qa['review_mode']}，reviewer {qa['reviewer']}）："
                               + json.dumps(qa["checks"], ensure_ascii=False))}
    raise ValueError(f"Unknown archive document: {key}")


def execute_project(plan, root, endpoint, operation, key, override):
    root = Path(root)
    project_id = plan["config"]["project_id"]
    if operation == "progress":
        names = dict(PROGRESS_STAGES)
        if key == "plan":
            current = call(endpoint, "run_plugin_action",
                           {"action_id": "ai-project-progress.get", "project_id": project_id})["result"]
            if {stage["id"] for stage in current.get("stages", [])} == set(names):
                return current
            arguments = {"action_id": "ai-project-progress.plan", "project_id": project_id,
                         "inputs": {"stages": [{"id": stage, "name": name, "order": order}
                                               for order, (stage, name) in enumerate(PROGRESS_STAGES)]}}
        else:
            if key not in names:
                raise ValueError(f"Unknown progress stage: {key}")
            if override is not None:
                inputs = override
                if not isinstance(inputs, dict) or inputs.get("stage_id") != key or key not in names \
                        or inputs.get("status") not in PROGRESS_STATUSES or not isinstance(inputs.get("stage_name"), str) \
                        or not inputs["stage_name"].strip() or not isinstance(inputs.get("note", ""), str):
                    raise ValueError("progress --inputs must be {stage_id, stage_name, status, note}")
            else:
                errors = [] if key == "preproduction" else validate_gate(plan, root, key)
                inputs = {"stage_id": key, "stage_name": names[key],
                          "status": "blocked" if errors else "completed",
                          "note": ("; ".join(errors)[:2000] if errors
                                   else f"revision {plan['revision']} 闸门通过")}
            arguments = {"action_id": "ai-project-progress.update", "project_id": project_id, "inputs": inputs}
    elif operation == "archive":
        if key not in ARCHIVE_TYPES:
            raise ValueError(f"Unknown archive document: {key}")
        content = archive_content(plan, root, key, override)
        current = call(endpoint, "run_plugin_action",
                       {"action_id": "project-archive.get_document", "project_id": project_id,
                        "inputs": {"document_type": key}})["result"]
        arguments = {"action_id": "project-archive.save_document", "project_id": project_id,
                     "inputs": {"document_type": key, "content": content,
                                "status": "draft" if key == "continuity" else "final",
                                "expected_revision": current.get("revision", 0)}}
    else:
        raise ValueError(f"Unknown project operation: {operation}")
    event = {"operation": operation, "key": key, "tool": "run_plugin_action", "arguments": arguments,
             "spec": fingerprint(arguments)}
    ledger = root / "jobs.jsonl"
    with ledger.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({**event, "event": "intent"}, ensure_ascii=False) + "\n")
    result = call(endpoint, "run_plugin_action", arguments)
    with ledger.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({**event, "event": "submitted", "response": result}, ensure_ascii=False) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", required=True, type=Path)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--operation", required=True, choices=("drafts", "references", "grids", "panels", "compilations", "continue", "confirm", "progress", "archive"))
    parser.add_argument("--key", required=True)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args()
    from preproduction import load_production
    plan = load_production(args.production)
    if args.operation in ("progress", "archive"):
        override = json.loads(args.inputs.read_text(encoding="utf-8")) if args.inputs else None
        result = execute_project(plan, args.production.resolve().parent, args.endpoint, args.operation, args.key, override)
        print(json.dumps(result, ensure_ascii=False))
        return
    if args.inputs:
        arguments = json.loads(args.inputs.read_text(encoding="utf-8"))
    elif args.operation in ("continue", "confirm"):
        raise ValueError("Continue/confirm require --inputs with the actual session/approval")
    else:
        arguments = make_request(plan, args.operation, args.key, args.attempt)
    result = execute(plan, args.production.resolve().parent, args.endpoint, args.operation, args.key, arguments)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
