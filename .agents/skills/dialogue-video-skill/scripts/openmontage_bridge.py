"""Delegate production state and media operations to installed OpenMontage."""

import argparse
import importlib
import json
import os
from pathlib import Path
import re
import sys


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openmontage-root", required=True, type=Path)
    parser.add_argument("--projects-root", required=True, type=Path)
    parser.add_argument("--project-id", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    init = commands.add_parser("init")
    init.add_argument("--title", required=True)
    commands.add_parser("next")
    checkpoint = commands.add_parser("checkpoint")
    checkpoint.add_argument("--stage", required=True)
    checkpoint.add_argument("--status", required=True,
                            choices=["in_progress", "completed", "awaiting_human", "failed"])
    checkpoint.add_argument("--artifacts", required=True, type=Path)
    checkpoint.add_argument("--require-approval", action="store_true")
    checkpoint.add_argument("--approved", action="store_true")
    checkpoint.add_argument("--production", type=Path)
    tool = commands.add_parser("tool")
    tool.add_argument("name", choices=["video_compose", "audio_mixer"])
    tool.add_argument("--inputs", required=True, type=Path)
    tool.add_argument("--production", type=Path)
    args = parser.parse_args()
    root = args.openmontage_root.resolve()
    projects = args.projects_root.resolve()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}", args.project_id):
        raise ValueError("Use a single portable project ID, not a path")
    if root == projects or root in projects.parents:
        raise ValueError("Projects must be outside the installed OpenMontage directory")
    if not (root / "pipeline_defs/dialogue-video.yaml").is_file():
        raise ValueError("Install the OpenMontage package with dialogue-video integration")
    os.environ["OPENMONTAGE_PROJECTS_DIR"] = str(projects)
    # Embedded Python may omit the script directory from sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(root))
    from lib.checkpoint import init_project, write_checkpoint, get_next_stage
    from lib.pipeline_loader import load_pipeline
    from schemas.artifacts import validate_artifact

    manifest = load_pipeline("dialogue-video")
    project = projects / args.project_id
    if project.resolve().parent != projects:
        raise ValueError("Project path escapes the selected projects root")
    marker = project / "project.json"
    if marker.exists() and read_json(marker).get("pipeline_type") != "dialogue-video":
        raise ValueError("Existing project belongs to a different pipeline")
    if args.command == "preflight":
        result = {"pipeline": manifest["name"], "openmontage_root": str(root)}
    elif args.command == "init":
        result = str(init_project(args.project_id, title=args.title,
                                 pipeline_type="dialogue-video", pipeline_dir=projects))
    else:
        if not marker.is_file():
            raise ValueError("Initialize this project before resuming or executing tools")
        if args.command == "next":
            result = get_next_stage(projects, args.project_id, pipeline_type="dialogue-video")
        elif args.command == "checkpoint":
            if args.status == "completed" and args.stage in ("assets", "edit", "compose", "publish"):
                if args.production is None:
                    raise ValueError("Completed media stages require --production and the media evidence gate")
                from validate import validate_gate
                gate = "final" if args.stage in ("compose", "publish") else "selected"
                from preproduction import load_production
                production = load_production(args.production)
                errors = validate_gate(production, args.production.parent, gate)
                if errors:
                    raise ValueError("Production gate failed: " + "; ".join(errors))
                artifacts = read_json(args.artifacts)
                if args.stage in ("compose", "publish"):
                    final = production["media_progress"]["final"]
                    expected = (args.production.parent / final["path"]).resolve()
                    if args.stage == "compose" and {expected} != {Path(o["path"]).resolve() for o in artifacts.get("render_report", {}).get("outputs", [])}:
                        raise ValueError("Render report must contain only the reviewed final file")
                    if args.stage == "publish":
                        log = artifacts.get("publish_log", {})
                        if log.get("metadata", {}).get("source_sha256") != final["sha256"]:
                            raise ValueError("Publish log must bind the reviewed final hash")
                        entries = log.get("entries", [])
                        if not entries or any(e.get("status") not in ("exported", "published") for e in entries):
                            raise ValueError("Completed publish requires successful export/publish entries")
                        if any(e.get("status") == "exported" and Path(e.get("export_path", "")).resolve() != expected for e in entries):
                            raise ValueError("Export path must be the reviewed final file")
            result = str(write_checkpoint(
                projects, args.project_id, args.stage, args.status, read_json(args.artifacts),
                pipeline_type="dialogue-video", human_approval_required=args.require_approval,
                human_approved=args.approved))
        else:
            inputs = read_json(args.inputs)
            output = Path(inputs["output_path"])
            if not output.is_absolute():
                raise ValueError("Tool paths must be absolute")
            if output.exists():
                raise ValueError("Output exists; choose a new revision filename")
            if args.name == "video_compose":
                if args.production is None:
                    raise ValueError("Rendering requires --production and reviewed selected media")
                from validate import validate_composition
                from preproduction import load_production
                errors = validate_composition(load_production(args.production), args.production.parent, inputs)
                if errors:
                    raise ValueError("Compose gate failed: " + "; ".join(errors))
                if inputs.get("operation") != "render":
                    raise ValueError("Use native render with canonical edit decisions")
                for artifact in ("edit_decisions", "asset_manifest", "proposal_packet"):
                    validate_artifact(artifact, inputs[artifact])
                runtime = inputs["edit_decisions"]["render_runtime"]
                if runtime != inputs["proposal_packet"]["production_plan"]["render_runtime"]:
                    raise ValueError("Render runtime differs from approved proposal")
            inputs["project_dir"] = str(project)
            from tools.tool_registry import ToolRegistry
            registry = ToolRegistry()
            module = importlib.import_module(
                "tools.video.video_compose" if args.name == "video_compose"
                else "tools.audio.audio_mixer")
            registry.register_module(module)
            native_result = registry.get(args.name).execute(inputs)
            result = {"success": native_result.success, "data": native_result.data,
                      "artifacts": native_result.artifacts, "error": native_result.error}
            print(json.dumps(result, ensure_ascii=False, default=str))
            return 0 if native_result.success else 1
    print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)
