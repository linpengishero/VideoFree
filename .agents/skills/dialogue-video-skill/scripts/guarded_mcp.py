"""Validate production dependencies before invoking videofree MCP tools."""

import argparse
import json
from pathlib import Path
import sys
import urllib.request
import uuid

from validate import fingerprint, request_contract, validate_confirmation, validate_gate, validate_request


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
        settings["shots"] = [shots[s]["storyboard_prompt"] for s in group["shot_ids"]]
        prompt = "Exactly four panels in a 2 by 2 grid, ordered top-left, top-right, bottom-left, bottom-right."
    elif operation == "panels":
        prompt = "Split the reference into four ordered panels."
    else:
        shot = next(s for s in plan["shots"] if s["id"] == key)
        prompt = shot["prompt"]["execution"]
        settings["duration"] = shot["duration"]
    arguments = {"capability_id": capability, "prompt": prompt, "settings": settings,
                 "inputs": [{"type": kind, "upload_id": value.get("upload_id"), "role": "reference"} for kind, value in sources],
                 "prompt_processing": "compile" if operation == "compilations" else "direct",
                 "project_id": plan["config"]["project_id"], "workspace_id": plan["config"]["workspace_id"]}
    arguments["idempotency_key"] = f"dialogue-{fingerprint(arguments)}-{attempt}"
    return arguments


def call(endpoint, name, arguments):
    payload = {"jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "tools/call",
               "params": {"name": name, "arguments": arguments}}
    request = urllib.request.Request(endpoint, json.dumps(payload, ensure_ascii=False).encode(),
                                     {"Content-Type": "application/json"})
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
    if arguments.get("workspace_id") != plan["config"]["workspace_id"]:
        errors.append("Wrong workspace_id")
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", required=True, type=Path)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--operation", required=True, choices=("drafts", "references", "grids", "panels", "compilations", "continue", "confirm"))
    parser.add_argument("--key", required=True)
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args()
    from preproduction import load_production
    plan = load_production(args.production)
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
