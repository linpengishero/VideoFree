import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "examples/skills/story-video-skill"


def load(name):
    spec = importlib.util.spec_from_file_location(f"story_video_{name}", SKILL / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load("validate")
sys_path = str(SKILL / "scripts")
import sys
sys.path.insert(0, sys_path)
guard = load("guarded_mcp")
package = load("preproduction")
bridge = SKILL / "scripts/openmontage_bridge.py"
OPENMONTAGE = ROOT / "examples/skills/openmontage"


def qa(stage, shots):
    return {"schema_version": 1, "stage": stage, "revision": 1, "reviewer": "test-reviewer",
            "review_mode": "independent", "status": "PASS", "shot_ids": shots,
            "checks": {c: "PASS" for c in validator.CHECKS[stage]},
            "evidence": ["Test fixture evidence"], "issues": [], "limitations": []}


def production():
    shots = []
    turns = []
    for i in range(4):
        line = f"Test dialogue {i}"
        turns.append({"id": f"t{i}", "speaker": "host_robot", "listener": "host_young_man",
                      "function": "explain", "line": line, "normalized_line": line,
                      "knowledge_delta": "A new fact", "typo_checked": True, "speech_checked": True})
        shots.append({"id": f"s{i}", "turn_id": f"t{i}", "speaker": "host_robot", "listener": "host_young_man",
                      "normalized_line": line, "audio_mode": "h3_dialogue", "duration": 14,
                      "scene_id": "lab", "scene_function": "dialogue", "shot_pattern": "over_shoulder",
                      "listener_face_policy": "rear", "listener_mouth": "closed",
                      "voice_asset": "host_robot/voice_reference.flac", "required_assets": ["lab"],
                      "action_start": "raises hand", "action_process": "explains", "action_end": "lowers hand",
                      "camera": "fixed", "continuity_in": "same position", "continuity_out": "same position",
                      "storyboard_prompt": f"Panel {i}: robot explaining in lab, listener silent",
                      "scene_design": {"id": "lab", "description": "Lab"},
                      "visual_dominance": {"primary": "host_robot", "secondary": "host_young_man", "lighting_priority": "primary"},
                      "prompt": {"reference_map": "Picture 1 robot", "execution": line}})
    return {"schema_version": 1, "revision": 1,
            "config": {"title": "Test", "project_id": "p1", "workspace_id": "test1", "aspect": "9:16",
                       "duration_target_sec": 56, "max_attempts_per_shot": 3, "min_scenes": 3,
                       "single_scene_reason": "A focused lab interview", "allow_self_review": False,
                       "refine": True, "subtitles": False},
            "research": {"kind": "fictional", "sources": [], "uncertainties": []},
            "episode_assets": [{"id": "lab", "kind": "location", "description": "Lab",
                                "scene_design": {"id": "lab", "description": "Lab"},
                                "prompts": {"draft": "Lab concept", "reference": "Final lab scene"}}],
            "turns": turns, "shots": shots,
            "storyboard_groups": [{"id": "g1", "scene_id": "lab", "panels": 4, "shot_ids": [s["id"] for s in shots]}],
            "preproduction_qa": qa("preproduction", [s["id"] for s in shots])}


def write_package(root, plan):
    data = copy.deepcopy(plan)
    shots = data["shots"]
    assets = data["episode_assets"]
    docs = {
        "task_config.yaml": {"revision": data["revision"], "config": data["config"]},
        "research_notes.md": {"research": data["research"]},
        "story_script.yaml": {"story_beats": data.get("story_beats", []), "turns": data["turns"]},
        "asset_manifest.yaml": {"episode_assets": [{k: v for k, v in a.items() if k not in ("prompts", "scene_design")} for a in assets]},
        "scene_plan.yaml": {"scenes": [a["scene_design"] for a in assets if a["kind"] == "location"]},
        "storyboard_groups.yaml": {"shots": [{k: v for k, v in s.items() if k not in
            ("speaker", "listener", "normalized_line", "voice_asset", "prompt", "scene_design")} for s in shots],
            "storyboard_groups": data["storyboard_groups"]},
        "asset_prompts.md": {"prompts": [{"asset_id": a["id"], **a["prompts"]} for a in assets]},
        "video_prompts.yaml": {"shots": [{"shot_id": s["id"], **s["prompt"]} for s in shots]},
    }
    for name, value in docs.items():
        text = json.dumps(value, ensure_ascii=False, indent=2)
        if name.endswith(".md"):
            text = "# Final document\n\n```json\n" + text + "\n```\n"
        (root / name).write_text(text, encoding="utf-8")
    (root / "production_plan.md").write_text("# Final plan\nUse Qwen then H3, videofree film-studio composition.\n", encoding="utf-8")
    review = {"qa": data["preproduction_qa"], "source_sha256": {
        name: package.digest(root / name) for name in package.DOCUMENTS if name != "preproduction_qa.md"}}
    (root / "preproduction_qa.md").write_text("# Review\n```json\n" + json.dumps(review) + "\n```\n", encoding="utf-8")
    index = package.build_index(root)
    index["media_progress"] = data.get("media_progress", {})
    (root / "production.json").write_text(json.dumps(index), encoding="utf-8")
    return index


class FinalPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = production()

    def test_index_contains_no_duplicate_text_and_loads_final_documents(self):
        index = write_package(self.root, self.plan)
        self.assertNotIn("shots", index)
        self.assertNotIn("turns", index)
        self.assertNotIn("config", index)
        loaded = package.load_production(self.root / "production.json")
        self.assertEqual(loaded["shots"], self.plan["shots"])
        self.assertEqual(validator.validate_plan(loaded), [])

    def test_preproduction_completes_without_generated_assets_but_grid_waits_for_them(self):
        write_package(self.root, self.plan)
        plan = package.load_production(self.root / "production.json")
        self.assertEqual(plan["media_progress"], {})
        draft = guard.make_request(plan, "drafts", "lab")
        self.assertEqual(validator.validate_request(plan, self.root, "drafts", "lab", draft), [])
        caller = Mock()
        grid = guard.make_request(plan, "grids", "g1")
        with self.assertRaises(ValueError):
            guard.execute(plan, self.root, "unused", "grids", "g1", grid, caller=caller)
        caller.assert_not_called()

    def test_context_cards_are_stage_scoped(self):
        write_package(self.root, self.plan)
        plan = package.load_production(self.root / "production.json")
        script = package.context_card(plan, "script")
        media = package.context_card(plan, "media", "s0")
        final = package.context_card(plan, "final")
        self.assertIn("turns", script)
        self.assertNotIn("episode_assets", script)
        self.assertIn("shot", media)
        self.assertNotIn("prompt", media["shot"])
        self.assertIn("related_shots", media)
        self.assertNotIn("research", media)
        self.assertIn("selected", final)
        self.assertNotIn("prompt", final)

    def test_media_context_rejects_unknown_shot(self):
        write_package(self.root, self.plan)
        plan = package.load_production(self.root / "production.json")
        with self.assertRaises(ValueError):
            package.context_card(plan, "media", "missing")

    def test_modified_missing_and_unreviewed_sources_block_execution(self):
        for name in package.DOCUMENTS:
            with self.subTest(name=name):
                write_package(self.root, self.plan)
                (self.root / name).write_text("Changed document", encoding="utf-8")
                with self.assertRaises((ValueError, KeyError)):
                    package.load_production(self.root / "production.json")
        write_package(self.root, self.plan)
        (self.root / "production_plan.md").unlink()
        with self.assertRaises(ValueError):
            package.build_index(self.root)

    def test_rebuild_requires_new_revision_and_preserves_execution_records(self):
        self.plan["media_progress"] = {"videos": {"s0": {"job_id": "keep-existing-job"}}}
        write_package(self.root, self.plan)
        path = self.root / "production_plan.md"
        path.write_text("# Changed final plan", encoding="utf-8")
        with self.assertRaises(ValueError):
            package.build_index(self.root)
        self.plan["revision"] = 2
        self.plan["preproduction_qa"]["revision"] = 2
        index = write_package(self.root, self.plan)
        self.assertEqual(index["media_progress"]["videos"]["s0"]["job_id"], "keep-existing-job")

    def test_image_and_video_descriptions_are_not_interchangeable(self):
        fixture = ProductionGateTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        request = copy.deepcopy(fixture.plan["media_progress"]["grids"]["g1"]["request"])
        request["prompt"] = " ".join(s["prompt"]["execution"] for s in fixture.plan["shots"])
        self.assertTrue(validator.check_request(fixture.plan, "grids", "g1", request))
        request = copy.deepcopy(fixture.plan["media_progress"]["drafts"]["lab"]["request"])
        request["prompt"] = "Invent a new design during generation"
        self.assertTrue(validator.check_request(fixture.plan, "drafts", "lab", request))


class ContractTests(unittest.TestCase):
    def test_long_shots_are_allowed(self):
        self.assertEqual(validator.validate_plan(production()), [])

    def test_assets_are_complete_and_portable(self):
        self.assertEqual(validator.validate_assets(SKILL), [])
        with tempfile.TemporaryDirectory() as tmp:
            relocated = Path(tmp) / "relocated"
            shutil.copytree(SKILL / "assets", relocated / "assets")
            self.assertEqual(validator.validate_assets(relocated), [])
            (relocated / "assets/dialogue-cast/host_robot/voice_reference.flac").write_bytes(b"changed")
            self.assertTrue(validator.validate_assets(relocated))

    def test_plan_regressions(self):
        changes = [
            lambda p: p["shots"][0].update(voice_asset="host_young_man/voice_reference.flac"),
            lambda p: p["shots"][0].update(speaker="host_young_man"),
            lambda p: p["shots"][0].update(id="s1"),
            lambda p: p["shots"][0]["prompt"].update(execution="missing dialogue"),
            lambda p: p["storyboard_groups"][0].update(shot_ids=["s0"] * 4),
            lambda p: p["preproduction_qa"].update(revision=0),
            lambda p: p["config"].update(single_scene_reason=""),
            lambda p: p["shots"][0].update(duration=float("nan")),
            lambda p: p["turns"][0].update(speaker=[]),
        ]
        for change in changes:
            with self.subTest(change=change):
                p = production()
                change(p)
                self.assertTrue(validator.validate_plan(p))

    def test_malformed_inputs(self):
        for value in (None, [], {}, {"config": []}, {"config": {"min_scenes": []}}):
            self.assertTrue(validator.validate_plan(value))

    def test_qa_gates(self):
        report = qa("final", ["s0"])
        self.assertEqual(validator.validate_qa(report, "final", 1, ["s0"]), [])
        for field, value in (("status", "BLOCKED"), ("revision", 2), ("shot_ids", ["other"]),
                             ("evidence", []), ("review_mode", "self_review"),
                             ("checks", {"technical": "PASS"}),
                             ("issues", [{"severity": "blocking"}])):
            altered = copy.deepcopy(report)
            altered[field] = value
            self.assertTrue(validator.validate_qa(altered, "final", 1, ["s0"]))
        report.update(review_mode="self_review", limitations=["User authorized non-independent review"])
        self.assertEqual(validator.validate_qa(report, "final", 1, ["s0"], True), [])

    def test_extra_check_requires_an_issue_but_does_not_fail_the_required_gate(self):
        report = qa("image", ["asset-a"])
        report["checks"]["color_style"] = "FAIL"
        report["issues"] = [{"check": "color_style", "severity": "minor", "evidence": "Slight tint"}]
        self.assertEqual(validator.validate_qa(report, "image", 1, ["asset-a"]), [])
        report["issues"] = []
        self.assertTrue(validator.validate_qa(report, "image", 1, ["asset-a"]))

    def test_silent_media_checks_accept_explained_na_only(self):
        report = qa("media", ["s0"])
        report["checks"].update(speaker="N/A", dialogue="N/A", voice="N/A")
        self.assertEqual(validator.validate_qa(report, "media", 1, ["s0"], shot_audio_modes={"s0": "silent"}), [])
        self.assertTrue(validator.validate_qa(report, "media", 1, ["s0"], shot_audio_modes={"s0": "h3_dialogue"}))
        self.assertTrue(validator.validate_qa(report, "media", 1, ["s0"]))
        report["checks"]["voice"] = "PASS"
        self.assertEqual(validator.validate_qa(report, "media", 1, ["s0"], shot_audio_modes={"s0": "narration"}), [])

    def test_batch_qa_splits_single_review_into_hash_bound_reports(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        paths = {"asset-a-1": "a.png", "asset-a-2": "b.png"}
        report = {"reviewer": "independent-reviewer", "review_mode": "independent", "limitations": [],
                  "candidates": []}
        for key, relative in paths.items():
            content = key.encode()
            (root / relative).write_bytes(content)
            report["candidates"].append({"id": key, "path": relative,
                "sha256": hashlib.sha256(content).hexdigest(), "status": "PASS",
                "checks": {name: "PASS" for name in validator.CHECKS["draft"]},
                "evidence": [f"Reviewed {key}"], "issues": []})
        result = validator.materialize_candidate_qa(report, root, "draft", 1, list(paths.items()))
        self.assertEqual(set(result), set(paths))
        self.assertEqual(result["asset-a-1"]["input_sha256"]["a.png"], report["candidates"][0]["sha256"])
        report["candidates"].pop()
        with self.assertRaises(ValueError):
            validator.materialize_candidate_qa(report, root, "draft", 1, list(paths.items()))


class ProductionGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plan = production()
        progress = {key: {} for key in ("drafts", "references", "grids", "panels", "compilations", "videos")}
        self.plan["media_progress"] = progress

        def artifact(section, key, capability, ids, parent=None, stage=None):
            path = f"{section}-{key}.bin"
            content = path.encode()
            (self.root / path).write_bytes(content)
            digest = hashlib.sha256(content).hexdigest()
            if stage is None and section != "panels":
                stage = "draft" if section == "drafts" else "image"
            report = qa(stage, ids) if stage else {}
            if stage:
                report["input_sha256"] = {path: digest}
            value = {"path": path, "sha256": digest, "revision": 1, "job_id": f"job-{section}-{key}",
                     "capability_id": capability, "qa": report, "upload_id": f"upload-{section}-{key}"}
            if parent is not None:
                value["parent_sha256"] = parent
            progress[section][key] = value
            return value

        draft = artifact("drafts", "lab", "image.qwen.text_to_image", ["lab"])
        reference = artifact("references", "lab", "image.qwen.image_to_image", ["lab"], draft["sha256"])
        grid = artifact("grids", "g1", "image.qwen.storyboard_4", [f"s{i}" for i in range(4)])
        grid["reference_sha256"] = {"lab": reference["sha256"]}
        progress["fixed_uploads"] = {
            host: {"character_sheet": f"board-{host}", "voice_reference": f"audio-{host}"}
            for host in validator.HOSTS}
        cast = json.loads((SKILL / "assets/cast.json").read_text(encoding="utf-8"))
        for host in validator.HOSTS:
            for field in ("character_sheet", "voice_reference"):
                progress["fixed_uploads"][host][field + "_sha256"] = hashlib.sha256((SKILL / "assets" / cast[host][field]).read_bytes()).hexdigest()
        for shot in self.plan["shots"]:
            key = shot["id"]
            panel = artifact("panels", key, "image.split", [key], grid["sha256"])
            panel["panel_index"] = int(key[1:])
            video = artifact("videos", key, "video.reference", [key], stage="media")
            images = [panel["upload_id"], "board-host_robot", "board-host_young_man", reference["upload_id"]]
            inputs = [{"type": "image", "upload_id": v} for v in images]
            inputs.append({"type": "audio", "upload_id": "audio-host_robot"})
            execution = "\n".join(["subject_definitions:", "summary:", "retention_analysis:",
                                   "detailed_description:", shot["normalized_line"],
                                   "overall_soundscape:", "non_diegetic_music:"])
            progress["compilations"][key] = {
                "revision": 1,
                "request": {"prompt_processing": "compile", "project_id": "p1",
                            "capability_id": "video.reference", "prompt": shot["prompt"]["execution"], "inputs": inputs},
                "response": {"id": f"collab-{key}", "status": "awaiting_confirmation", "model_id": "minimax-h3",
                             "collaboration_mode": "quick", "confirmation": {"execution_prompt_en": execution}},
                "submission": {"collaboration_id": f"collab-{key}", "job_id": video["job_id"]}}
        self.bind_requests()

    def bind_requests(self):
        p = self.plan["media_progress"]
        for section in ("drafts", "references", "grids", "panels", "compilations"):
            for key, value in p[section].items():
                capability, sources = validator.request_contract(self.plan, section, key)
                request = guard.make_request(self.plan, section, key)
                request["idempotency_key"] = f"{section}-{key}"
                value["request"] = request
                if section == "compilations":
                    value["response"].update(revision=1, confirmed_prompt_zh="Test")
                    video = p["videos"][key]
                    video["compiled_sha256"] = validator.fingerprint(value["response"]["confirmation"]["execution_prompt_en"])
                    receipt_value = video
                else:
                    receipt_value = value
                receipt_value["gateway_inputs"] = {"job_id": receipt_value["job_id"], "items": [
                    {"type": kind, "upload_id": source["upload_id"], "sha256": source["sha256"]} for kind, source in sources]}
                value["spec_sha256"] = validator.specification(self.plan, section, key)
        for key, grid in p["grids"].items():
            group = next(g for g in self.plan["storyboard_groups"] if g["id"] == key)
            keys = validator.grid_keys(self.plan, group)
            grid["reference_sha256"] = {k: source["sha256"] for k, source in zip(keys, validator.reference_sources(self.plan, keys))}
        for key, video in p["videos"].items():
            video["spec_sha256"] = validator.specification(self.plan, "videos", key)
        p["selected"] = {key: video["job_id"] for key, video in p["videos"].items()}

    def test_full_pipeline_all_gates(self):
        for stage in ("drafts", "references", "grids", "storyboard", "compiled", "media", "selected"):
            self.assertEqual(validator.validate_gate(self.plan, self.root, stage), [], stage)

    def test_requests_derive_final_prompts_and_actual_references(self):
        for operation, key in (("drafts", "lab"), ("references", "lab"), ("grids", "g1"),
                               ("panels", "s0"), ("compilations", "s0")):
            with self.subTest(operation=operation):
                request = guard.make_request(self.plan, operation, key)
                self.assertEqual(validator.validate_request(self.plan, self.root, operation, key, request), [])
                self.assertEqual(request, guard.make_request(self.plan, operation, key))
                self.assertNotEqual(request["idempotency_key"], guard.make_request(self.plan, operation, key, 2)["idempotency_key"])
        video = guard.make_request(self.plan, "compilations", "s0")
        self.assertEqual(video["prompt_processing"], "compile")
        self.assertEqual(video["prompt"], self.plan["shots"][0]["prompt"]["execution"])
        self.assertEqual(video["settings"]["duration"], 14)
        self.assertEqual(video["inputs"][-1]["type"], "audio")
        with self.assertRaises(ValueError):
            guard.make_request(self.plan, "drafts", "lab", 4)

    def test_character_request_overrides_project_and_configured_ratio(self):
        self.plan["episode_assets"][0]["kind"] = "object"
        self.plan["config"]["generation_settings"] = {"references": {"ratio": "9:16", "resolution": "1K"}}
        request = guard.make_request(self.plan, "references", "lab")
        self.assertEqual(request["settings"], {"ratio": "16:9", "resolution": "1K"})
        self.assertEqual(validator.check_request(self.plan, "references", "lab", request), [])

    def test_grid_inputs_follow_final_group_order(self):
        self.plan["shots"][0]["required_assets"].append("prop_a")
        self.plan["shots"][1]["required_assets"].append("prop_b")
        group = self.plan["storyboard_groups"][0]
        group["shot_ids"] = ["s1", "s0", "s2", "s3"]
        keys = validator.grid_keys(self.plan, group)
        self.assertLess(keys.index("prop_b"), keys.index("prop_a"))

    def test_configured_settings_invalidate_old_artifacts_and_cannot_be_overridden(self):
        self.plan["config"]["generation_settings"] = {"drafts": {"resolution": "1K"}}
        request = guard.make_request(self.plan, "drafts", "lab")
        self.assertEqual(validator.check_request(self.plan, "drafts", "lab", request), [])
        request["settings"]["resolution"] = "2K"
        self.assertTrue(validator.check_request(self.plan, "drafts", "lab", request))
        self.assertTrue(validator.validate_gate(self.plan, self.root, "drafts"))

    def test_automatic_request_missing_upload_is_blocked_before_network(self):
        self.plan["media_progress"]["fixed_uploads"]["host_robot"].pop("character_sheet")
        request = guard.make_request(self.plan, "grids", "g1")
        caller = Mock()
        with self.assertRaises(ValueError):
            guard.execute(self.plan, self.root, "unused", "grids", "g1", request, caller=caller)
        caller.assert_not_called()

    def test_skip_or_stale_production_is_blocked(self):
        mutations = [
            lambda p: p["media_progress"]["drafts"].clear(),
            lambda p: p["media_progress"]["references"].clear(),
            lambda p: p["media_progress"]["panels"].clear(),
            lambda p: p["media_progress"]["references"]["lab"].update(capability_id="image.gpt.character"),
            lambda p: p["media_progress"]["references"]["lab"].update(parent_sha256="wrong"),
            lambda p: p["media_progress"]["grids"]["g1"].update(reference_sha256={}),
            lambda p: p["media_progress"]["panels"]["s0"].update(panel_index=2),
            lambda p: p["media_progress"]["panels"]["s0"]["qa"].update(revision=0),
            lambda p: p["media_progress"]["panels"]["s0"]["qa"].update(input_sha256={}),
            lambda p: p["media_progress"]["drafts"]["lab"].update(path="../escape.bin"),
            lambda p: p["media_progress"]["videos"]["s0"].update(sha256="wrong"),
            lambda p: p.update(media_progress=[]),
        ]
        for mutate in mutations:
            p = copy.deepcopy(self.plan)
            mutate(p)
            self.assertTrue(validator.validate_gate(p, self.root, "media"))

    def test_h3_direct_and_wrong_inputs_are_blocked(self):
        for mode in ("direct", "raw", None):
            p = copy.deepcopy(self.plan)
            p["media_progress"]["compilations"]["s0"]["request"]["prompt_processing"] = mode
            self.assertTrue(validator.validate_gate(p, self.root, "compiled", "s0"))
        for change in (
            lambda c: c["request"].update(inputs=[]),
            lambda c: c["request"].update(project_id="wrong"),
            lambda c: c["request"]["inputs"][-1].update(upload_id="audio-host_young_man"),
            lambda c: c["request"]["inputs"][0].update(upload_id="whole-grid"),
            lambda c: c["response"].update(status="needs_input"),
            lambda c: c["response"]["confirmation"].update(execution_prompt_en="one line translation"),
            lambda c: c["submission"].update(job_id="unrelated-direct-job"),
        ):
            p = copy.deepcopy(self.plan)
            change(p["media_progress"]["compilations"]["s0"])
            self.assertTrue(validator.validate_gate(p, self.root, "media"))

    def test_missing_file_and_unknown_shot(self):
        (self.root / "drafts-lab.bin").unlink()
        self.assertTrue(validator.validate_gate(self.plan, self.root, "drafts"))
        self.assertTrue(validator.validate_gate(self.plan, self.root, "compiled", "unknown"))

    def test_four_panels_only(self):
        self.plan["storyboard_groups"][0]["panels"] = 6
        self.assertTrue(validator.validate_plan(self.plan))

    def test_character_sheets_require_landscape_independent_of_video(self):
        self.plan["episode_assets"].append({"id": "prop", "kind": "object", "description": "Recurring prop",
                                           "prompts": {"draft": "Prop concept", "reference": "Prop views"}})
        progress = self.plan["media_progress"]
        progress["drafts"]["prop"] = copy.deepcopy(progress["drafts"]["lab"])
        progress["references"]["prop"] = copy.deepcopy(progress["references"]["lab"])
        for section in ("drafts", "references"):
            progress[section]["prop"]["qa"]["shot_ids"] = ["prop"]
        reference = progress["references"]["prop"]
        reference["capability_id"] = "image.qwen.character"
        self.bind_requests()
        for settings in ({}, {"ratio": "9:16"}, {"ratio": "1:1"}):
            reference["request"]["settings"] = settings
            self.assertTrue(validator.validate_gate(self.plan, self.root, "references"))
        reference["request"]["settings"] = {"ratio": "16:9"}
        self.assertEqual(validator.validate_gate(self.plan, self.root, "references"), [])
        self.assertEqual(self.plan["config"]["aspect"], "9:16")

    def test_real_mcp_receipt_and_old_result_shape(self):
        c = self.plan["media_progress"]["compilations"]["s0"]
        c["response"]["result"] = {"optimized_prompt": c["response"].pop("confirmation")["execution_prompt_en"]}
        self.assertEqual(validator.validate_gate(self.plan, self.root, "compiled", "s0"), [])

    def test_missing_real_reference_requests_and_receipts_rejected(self):
        for section, key in (("references", "lab"), ("grids", "g1"), ("panels", "s0")):
            for field in ("request", "gateway_inputs"):
                p = copy.deepcopy(self.plan)
                p["media_progress"][section][key].pop(field)
                self.assertTrue(validator.validate_gate(p, self.root, "storyboard"))
        p = copy.deepcopy(self.plan)
        p["media_progress"]["grids"]["g1"]["request"]["inputs"] = p["media_progress"]["grids"]["g1"]["request"]["inputs"][:1]
        self.assertTrue(validator.validate_gate(p, self.root, "storyboard"))

    def test_local_revision_reuses_unchanged_assets(self):
        self.plan["revision"] = 2
        self.plan["preproduction_qa"]["revision"] = 2
        self.assertEqual(validator.validate_gate(self.plan, self.root, "media"), [])
        self.plan["shots"][0]["camera"] = "dolly"
        self.assertEqual(validator.validate_gate(self.plan, self.root, "references"), [])
        self.assertTrue(validator.validate_gate(self.plan, self.root, "storyboard"))

    def test_guard_blocks_before_network_and_reuses_recorded_submission(self):
        request = self.plan["media_progress"]["grids"]["g1"]["request"]
        caller = Mock(return_value={"job_id": "actual-job"})
        bad = {**request, "inputs": []}
        with self.assertRaises(ValueError):
            guard.execute(self.plan, self.root, "http://invalid/mcp", "grids", "g1", bad, caller)
        caller.assert_not_called()
        first = guard.execute(self.plan, self.root, "http://invalid/mcp", "grids", "g1", request, caller)
        self.assertEqual(first, guard.execute(self.plan, self.root, "http://invalid/mcp", "grids", "g1", request, caller))
        caller.assert_called_once()

    def test_scoped_user_confirmation_and_stale_delegation(self):
        c = self.plan["media_progress"]["compilations"]["s0"]
        args = {"collaboration_id": c["response"]["id"], "revision": 1, "idempotency_key": "confirm-s0"}
        self.assertTrue(validator.validate_confirmation(self.plan, self.root, "s0", args))
        self.plan["h3_delegation"] = {"approved_by": "user", "evidence": "User explicitly delegates H3 review and confirmation",
                                      "allow_review_and_confirm": True, "shot_specs": {"s0": validator.specification(self.plan, "compilations", "s0")}}
        self.assertEqual(validator.validate_confirmation(self.plan, self.root, "s0", args), [])
        self.plan["h3_delegation"]["shot_specs"]["s0"] = "stale"
        self.assertTrue(validator.validate_confirmation(self.plan, self.root, "s0", args))

    def test_refinement_requires_reviewed_parent_and_gateway_receipt(self):
        p = self.plan["media_progress"]
        entry = copy.deepcopy(p["videos"]["s0"])
        entry.update(job_id="refine-s0", parent_job_id=p["videos"]["s0"]["job_id"],
                     parent_sha256=p["videos"]["s0"]["sha256"], action_id="h3_refine")
        p["refinements"] = {"s0": [entry]}
        p["selected"]["s0"] = entry["job_id"]
        self.assertTrue(validator.validate_gate(self.plan, self.root, "selected"))
        entry["gateway_job"] = {"id": entry["job_id"], "status": "completed", "parent_job_id": entry["parent_job_id"]}
        self.assertEqual(validator.validate_gate(self.plan, self.root, "selected"), [])
        for field, value in (("parent_sha256", "wrong"), ("revision", None), ("qa", {})):
            original = entry[field]
            entry[field] = value
            self.assertTrue(validator.validate_gate(self.plan, self.root, "selected"))
            entry[field] = original

    def composition_evidence(self):
        film_id = "film-" + hashlib.sha256(b"test-film").hexdigest()[:12]
        preview = self.root / "preview.mp4"
        preview.write_bytes(b"offline preview fixture")
        output = self.root / "final.mp4"
        output.write_bytes(b"offline final fixture")
        return {"film_id": film_id,
                "sources": [{"shot_id": s["id"], "job_id": self.plan["media_progress"]["selected"][s["id"]],
                             "audio_mode": s["audio_mode"]} for s in self.plan["shots"]],
                "audio_clips": [],
                "validate": {"status": "completed", "film_id": film_id},
                "preview": {"status": "completed", "film_id": film_id, "path": "preview.mp4",
                            "sha256": hashlib.sha256(preview.read_bytes()).hexdigest()},
                "render": {"status": "completed", "film_id": film_id, "url": "http://gateway/films/final.mp4"},
                "output": {"path": "final.mp4",
                           "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}}

    def test_final_gate_binds_render_sources_and_output(self):
        progress = self.plan["media_progress"]
        composition = self.composition_evidence()
        self.assertEqual(validator.validate_composition(self.plan, self.root, composition), [])
        self.assertTrue(validator.validate_gate(self.plan, self.root, "final"))
        digest = hashlib.sha256((self.root / "final.mp4").read_bytes()).hexdigest()
        review = qa("final", [s["id"] for s in self.plan["shots"]])
        review["input_sha256"] = {"final.mp4": digest}
        progress["composition"] = composition
        progress["final"] = {"path": "final.mp4", "sha256": digest, "qa": review,
                             "selection_sha256": validator.selection_hash(self.plan),
                             "compose_sha256": validator.fingerprint(composition)}
        self.assertEqual(validator.validate_gate(self.plan, self.root, "final"), [])
        composition["sources"][0]["job_id"] = "unselected-job"
        self.assertTrue(validator.validate_gate(self.plan, self.root, "final"))
        composition["sources"][0]["job_id"] = progress["selected"]["s0"]
        (self.root / "final.mp4").write_bytes(b"swapped after render")
        self.assertTrue(validator.validate_gate(self.plan, self.root, "final"))

    def test_composition_requires_narration_audio_clips(self):
        composition = self.composition_evidence()
        plan = copy.deepcopy(self.plan)
        plan["shots"][0]["audio_mode"] = "narration"
        composition["sources"][0]["audio_mode"] = "narration"
        self.assertTrue(any("narration" in e for e in validator.validate_composition(plan, self.root, composition)))
        composition["audio_clips"] = [{"shot_id": "s0", "job_id": "job-narration-s0"}]
        self.assertEqual(validator.validate_composition(plan, self.root, composition), [])

    def test_guard_refuses_changed_request_with_same_key(self):
        request = self.plan["media_progress"]["drafts"]["lab"]["request"]
        caller = Mock(return_value={"job_id": "j1"})
        guard.execute(self.plan, self.root, "http://invalid/mcp", "drafts", "lab", request, caller)
        with self.assertRaises(ValueError):
            guard.execute(self.plan, self.root, "http://invalid/mcp", "drafts", "lab", {**request, "prompt": "New design"}, caller)
        caller.assert_called_once()


class ProjectManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        write_package(self.root, production())
        self.plan = package.load_production(self.root / "production.json")
        self.original_call = guard.call
        self.addCleanup(setattr, guard, "call", self.original_call)
        self.calls = []

    def fake(self, *responses):
        def call(endpoint, name, arguments):
            self.calls.append((name, arguments))
            return responses[len(self.calls) - 1]
        guard.call = call

    def test_archive_projects_fixed_cast_and_final_documents(self):
        characters = guard.archive_content(self.plan, self.root, "characters", None)
        ids = [item["id"] for item in characters["items"]]
        self.assertIn("host_robot", ids)
        self.assertIn("host_young_man-voice", ids)
        self.assertNotIn("lab", ids)
        storyboard = guard.archive_content(self.plan, self.root, "storyboard", None)
        self.assertEqual(storyboard["shots"][0]["speaker"], "host_robot")
        self.assertEqual(storyboard["shots"][0]["status"], "planned")
        self.assertNotIn("selected_job_id", storyboard["shots"][0])
        self.plan["media_progress"] = {"selected": {"s0": "job-s0"}}
        storyboard = guard.archive_content(self.plan, self.root, "storyboard", None)
        self.assertEqual(storyboard["shots"][0]["selected_job_id"], "job-s0")
        self.assertEqual(storyboard["shots"][0]["status"], "selected")
        self.assertEqual(guard.archive_content(self.plan, self.root, "script", None),
                         (self.root / "story_script.yaml").read_text(encoding="utf-8-sig"))
        self.assertEqual([item["id"] for item in guard.archive_content(self.plan, self.root, "scenes", None)["items"]], ["lab"])
        prompt_ids = [item["id"] for item in guard.archive_content(self.plan, self.root, "prompts", None)["items"]]
        self.assertIn("img-lab", prompt_ids)
        self.assertIn("s0", prompt_ids)
        self.assertIn("Test", guard.archive_content(self.plan, self.root, "final-package", None)["summary"])
        with self.assertRaises(ValueError):
            guard.archive_content(self.plan, self.root, "continuity", None)
        with self.assertRaises(ValueError):
            guard.archive_content(self.plan, self.root, "unknown", None)

    def test_progress_plan_is_idempotent_and_gates_drive_status(self):
        self.fake({"result": {"stages": []}}, {"result": {"status": "ok"}},
                  {"result": {"stages": [{"id": stage, "name": name} for stage, name in guard.PROGRESS_STAGES]}},
                  {"result": {"status": "updated"}}, {"result": {"status": "updated"}})
        guard.execute_project(self.plan, self.root, "http://invalid/mcp", "progress", "plan", None)
        self.assertEqual(self.calls[0][1]["action_id"], "ai-project-progress.get")
        self.assertEqual(self.calls[1][1]["action_id"], "ai-project-progress.plan")
        self.assertEqual(len(self.calls[1][1]["inputs"]["stages"]), 9)
        guard.execute_project(self.plan, self.root, "http://invalid/mcp", "progress", "plan", None)
        self.assertEqual(len(self.calls), 3)
        guard.execute_project(self.plan, self.root, "http://invalid/mcp", "progress", "drafts", None)
        self.assertEqual(self.calls[-1][1]["action_id"], "ai-project-progress.update")
        self.assertEqual(self.calls[-1][1]["inputs"]["status"], "blocked")
        self.assertIn("drafts", self.calls[-1][1]["inputs"]["note"])
        guard.execute_project(self.plan, self.root, "http://invalid/mcp", "progress", "drafts",
                              {"stage_id": "drafts", "stage_name": "主体草稿", "status": "running", "note": "start"})
        self.assertEqual(self.calls[-1][1]["inputs"]["status"], "running")
        with self.assertRaises(ValueError):
            guard.execute_project(self.plan, self.root, "http://invalid/mcp", "progress", "drafts",
                                  {"stage_id": "drafts", "stage_name": "x", "status": "teleported"})
        with self.assertRaises(ValueError):
            guard.execute_project(self.plan, self.root, "http://invalid/mcp", "progress", "nope", None)
        events = [json.loads(line) for line in (self.root / "jobs.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events[0]["event"], "intent")
        self.assertTrue(any(e["event"] == "submitted" and e["operation"] == "progress" for e in events))

    def test_archive_saves_with_cas_revision_and_draft_continuity(self):
        self.fake({"result": {"revision": 2}}, {"result": {"saved": True}},
                  {"result": {}}, {"result": {"saved": True}})
        guard.execute_project(self.plan, self.root, "http://invalid/mcp", "archive", "script", None)
        self.assertEqual(self.calls[0][1]["action_id"], "project-archive.get_document")
        save = self.calls[1][1]
        self.assertEqual(save["action_id"], "project-archive.save_document")
        self.assertEqual(save["inputs"]["expected_revision"], 2)
        self.assertEqual(save["inputs"]["status"], "final")
        self.assertIsInstance(save["inputs"]["content"], str)
        guard.execute_project(self.plan, self.root, "http://invalid/mcp", "archive", "continuity",
                              {"decisions": "d", "completed": "c", "blockers": "b", "next_action": "n"})
        self.assertEqual(self.calls[-1][1]["inputs"]["status"], "draft")
        self.assertEqual(self.calls[-1][1]["inputs"]["expected_revision"], 0)

    def test_max_shot_duration_comes_from_capability_discovery(self):
        plan = copy.deepcopy(self.plan)
        plan["config"]["max_shot_duration"] = 10
        self.assertTrue(any("max_shot_duration" in e for e in validator.validate_plan(plan)))
        plan["config"]["max_shot_duration"] = 14
        self.assertEqual(validator.validate_plan(plan), [])


class OpenMontageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def call(self, *args, project_id="test", success=True):
        import sys
        result = subprocess.run([
            os.environ.get("OPENMONTAGE_TEST_PYTHON", sys.executable), "-X", "utf8", "-B", str(bridge),
            "--openmontage-root", str(OPENMONTAGE),
            "--projects-root", str(self.base / "projects"),
            "--project-id", project_id, *args], capture_output=True, text=True, encoding="utf-8")
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result.stdout

    def manifest(self, data, name="artifacts.json"):
        path = self.base / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_manifest_init_resume_and_predecessors(self):
        self.assertIn("story-video", self.call("preflight"))
        self.call("init", "--title", "Portable test")
        self.assertIn("research", self.call("next"))
        path = str(self.manifest({}))
        self.call("checkpoint", "--stage", "script", "--status", "in_progress", "--artifacts", path)
        self.call("checkpoint", "--stage", "script", "--status", "completed", "--artifacts", path,
                  success=False)
        self.call("checkpoint", "--stage", "research", "--status", "completed", "--artifacts", path,
                  success=False)

    def test_path_and_pipeline_guards(self):
        self.call("init", "--title", "Invalid", project_id="../escape", success=False)
        self.call("init", "--title", "Portable")
        marker = self.base / "projects/test/project.json"
        data = json.loads(marker.read_text(encoding="utf-8"))
        data["pipeline_type"] = "pk-dialogue-story"
        marker.write_text(json.dumps(data), encoding="utf-8")
        self.call("init", "--title", "Overwrite", success=False)

    def test_media_checkpoint_requires_actual_production(self):
        self.call("init", "--title", "Media gate")
        artifacts = str(self.manifest({}))
        result = self.call("checkpoint", "--stage", "assets", "--status", "completed",
                           "--artifacts", artifacts, success=False)
        self.assertIn("--production", result)
        write_package(self.base, production())
        path = str(self.base / "production.json")
        result = self.call("checkpoint", "--stage", "assets", "--status", "completed",
                           "--artifacts", artifacts, "--production", path, success=False)
        self.assertIn("Production gate failed", result)

    def test_bridge_exposes_no_media_tool_channel(self):
        # Composition runs on the videofree gateway via film-studio actions; the bridge is state-only.
        self.call("init", "--title", "No media tools")
        result = subprocess.run([
            os.environ.get("OPENMONTAGE_TEST_PYTHON", sys.executable), "-X", "utf8", "-B", str(bridge),
            "--openmontage-root", str(OPENMONTAGE),
            "--projects-root", str(self.base / "projects"),
            "--project-id", "test", "tool", "video_compose"], capture_output=True, text=True, encoding="utf-8")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice: 'tool'", result.stderr)


if __name__ == "__main__":
    unittest.main()
