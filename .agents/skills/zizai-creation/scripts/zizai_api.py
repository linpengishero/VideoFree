#!/usr/bin/env python3
import argparse
import json
import mimetypes
import os
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BASE = os.getenv("ZIZAI_API_URL", "http://127.0.0.1:8765").rstrip("/")
if BASE.endswith("/api/v2"):
    BASE = BASE[:-len("/api/v2")]
TOKEN = os.getenv("ZIZAI_API_TOKEN", "")
WORKSPACE_ID = os.getenv("ZIZAI_WORKSPACE_ID", "zizai-rest-default")


def call(method, path, body=None, headers=None, timeout=180):
    values = {"Accept": "application/json", "X-Workspace-Id": WORKSPACE_ID, **(headers or {})}
    if TOKEN:
        values["X-API-Token"] = TOKEN
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        values["Content-Type"] = "application/json"
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=values)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read()
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def upload(path):
    source = Path(path)
    if not source.is_file():
        raise RuntimeError(f"file not found: {source}")
    boundary = "----zizai" + uuid.uuid4().hex
    media_type = {
        ".flac": "audio/flac",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
    }.get(source.suffix.lower(), mimetypes.guess_type(source.name)[0] or "application/octet-stream")
    prefix = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{source.name}\"\r\n"
        f"Content-Type: {media_type}\r\n\r\n"
    ).encode()
    payload = prefix + source.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json", "X-Workspace-Id": WORKSPACE_ID}
    if TOKEN:
        headers["X-API-Token"] = TOKEN
    request = urllib.request.Request(BASE + "/api/v2/uploads", data=payload, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc


def download(job_id, directory):
    artifacts = call("GET", f"/api/v2/jobs/{job_id}/artifacts").get("items", [])
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    saved = []
    for index, artifact in enumerate(artifacts, 1):
        url = str(artifact.get("url", ""))
        if not url.startswith("/"):
            continue
        name = Path(str(artifact.get("name", ""))).name or f"artifact-{index}"
        headers = {"X-Workspace-Id": WORKSPACE_ID}
        if TOKEN:
            headers["X-API-Token"] = TOKEN
        request = urllib.request.Request(BASE + url, headers=headers)
        with urllib.request.urlopen(request, timeout=600) as response:
            path = target / name
            path.write_bytes(response.read())
        saved.append(str(path.resolve()))
    return {"job_id": job_id, "files": saved}


def query(path, values):
    clean = {key: value for key, value in values.items() if value is not None}
    return path + ("?" + urllib.parse.urlencode(clean) if clean else "")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description="videofree AI API client")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    sub.add_parser("projects")
    current_project = sub.add_parser("current-project")
    create_project = sub.add_parser("create-project"); create_project.add_argument("name"); create_project.add_argument("--description", default=""); create_project.add_argument("--content-summary", default="")
    select_project = sub.add_parser("select-project"); select_project.add_argument("project_id")
    cap = sub.add_parser("capabilities"); cap.add_argument("--kind"); cap.add_argument("--operation", default="generate")
    up = sub.add_parser("upload"); up.add_argument("file")
    sub.add_parser("voices")
    preset_speech = sub.add_parser("speech-preset"); preset_speech.add_argument("preset_id"); preset_speech.add_argument("text"); preset_speech.add_argument("--speed", type=float, default=1.0)
    described_speech = sub.add_parser("speech-describe"); described_speech.add_argument("voice_description"); described_speech.add_argument("text"); described_speech.add_argument("--speed", type=float, default=1.0)
    cloned_speech = sub.add_parser("speech-clone"); cloned_speech.add_argument("reference_audio"); cloned_speech.add_argument("text"); cloned_speech.add_argument("--speed", type=float, default=1.0)
    music = sub.add_parser("music"); music.add_argument("category", choices=["styles", "singers", "voice-textures", "presets"])
    sub.add_parser("image-styles")
    create = sub.add_parser("create"); create.add_argument("request"); create.add_argument("--idempotency-key")
    collaborate = sub.add_parser("collaborate"); collaborate.add_argument("request")
    collaboration = sub.add_parser("collaboration"); collaboration.add_argument("collaboration_id")
    reply = sub.add_parser("reply"); reply.add_argument("collaboration_id"); reply.add_argument("message")
    progress = sub.add_parser("collaboration-progress"); progress.add_argument("collaboration_id")
    confirm = sub.add_parser("confirm"); confirm.add_argument("collaboration_id"); confirm.add_argument("revision", type=int); confirm.add_argument("--idempotency-key"); confirm.add_argument("--execution-prompt-en-file"); confirm.add_argument("--confirmed-prompt-zh-file")
    job = sub.add_parser("job"); job.add_argument("job_id")
    wait = sub.add_parser("wait"); wait.add_argument("job_id"); wait.add_argument("--timeout", type=int, default=60)
    artifacts = sub.add_parser("artifacts"); artifacts.add_argument("job_id")
    inputs = sub.add_parser("inputs"); inputs.add_argument("job_id")
    get_files = sub.add_parser("download"); get_files.add_argument("job_id"); get_files.add_argument("directory")
    actions = sub.add_parser("actions"); actions.add_argument("job_id")
    action = sub.add_parser("run-action"); action.add_argument("job_id"); action.add_argument("action_id")
    regen = sub.add_parser("regenerate"); regen.add_argument("job_id"); regen.add_argument("changes")
    cancel = sub.add_parser("cancel"); cancel.add_argument("job_id")
    api = sub.add_parser("api"); api.add_argument("method"); api.add_argument("path"); api.add_argument("--json")
    args = parser.parse_args()

    if args.command == "health": result = call("GET", "/api/v2/health")
    elif args.command == "projects": result = call("GET", "/api/v2/projects")
    elif args.command == "current-project": result = call("GET", "/api/v2/projects/current")
    elif args.command == "create-project": result = call("POST", "/api/v2/projects", {"name": args.name, "description": args.description, "content_summary": args.content_summary})
    elif args.command == "select-project": result = call("PUT", "/api/v2/projects/current", {"project_id": args.project_id})
    elif args.command == "capabilities": result = call("GET", query("/api/v2/capabilities", {"kind": args.kind, "operation": args.operation}))
    elif args.command == "upload": result = upload(args.file)
    elif args.command == "voices": result = call("GET", "/api/v2/voices")
    elif args.command == "speech-preset": result = call("POST", "/api/v2/tts/preset", {"preset_id": args.preset_id, "text": args.text, "speed": args.speed}, timeout=30)
    elif args.command == "speech-describe": result = call("POST", "/api/v2/tts/describe", {"voice_description": args.voice_description, "text": args.text, "speed": args.speed}, timeout=30)
    elif args.command == "speech-clone":
        uploaded = upload(args.reference_audio)
        result = call("POST", "/api/v2/tts/clone", {"reference_upload_id": uploaded["upload_id"], "text": args.text, "speed": args.speed}, timeout=30)
    elif args.command == "music": result = call("GET", "/api/v2/music/" + args.category)
    elif args.command == "image-styles": result = call("GET", "/api/v2/image/styles")
    elif args.command == "create":
        headers = {"Idempotency-Key": args.idempotency_key} if args.idempotency_key else None
        result = call("POST", "/api/v2/generations", load_json(args.request), headers)
    elif args.command == "collaborate": result = call("POST", "/api/v2/collaborations", load_json(args.request), timeout=1800)
    elif args.command == "collaboration": result = call("GET", f"/api/v2/collaborations/{args.collaboration_id}")
    elif args.command == "reply": result = call("POST", f"/api/v2/collaborations/{args.collaboration_id}/messages", {"message": args.message}, timeout=1800)
    elif args.command == "collaboration-progress": result = call("GET", f"/api/v2/collaborations/{args.collaboration_id}/progress")
    elif args.command == "confirm":
        body = {"revision": args.revision, "idempotency_key": args.idempotency_key}
        if args.execution_prompt_en_file:
            body["execution_prompt_en"] = Path(args.execution_prompt_en_file).read_text(encoding="utf-8")
        if args.confirmed_prompt_zh_file:
            body["confirmed_prompt_zh"] = Path(args.confirmed_prompt_zh_file).read_text(encoding="utf-8")
        result = call("POST", f"/api/v2/collaborations/{args.collaboration_id}/confirm", body)
    elif args.command == "job": result = call("GET", f"/api/v2/jobs/{args.job_id}")
    elif args.command == "wait": result = call("GET", query(f"/api/v2/jobs/{args.job_id}/wait", {"timeout": args.timeout}))
    elif args.command == "artifacts": result = call("GET", f"/api/v2/jobs/{args.job_id}/artifacts")
    elif args.command == "inputs": result = call("GET", f"/api/v2/jobs/{args.job_id}/inputs")
    elif args.command == "download": result = download(args.job_id, args.directory)
    elif args.command == "actions": result = call("GET", f"/api/v2/jobs/{args.job_id}/actions")
    elif args.command == "run-action": result = call("POST", f"/api/v2/jobs/{args.job_id}/actions/{args.action_id}", {})
    elif args.command == "regenerate": result = call("POST", f"/api/v2/jobs/{args.job_id}/regenerate", load_json(args.changes))
    elif args.command == "cancel": result = call("POST", f"/api/v2/jobs/{args.job_id}/cancel", {})
    else: result = call(args.method.upper(), args.path, load_json(args.json) if args.json else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
