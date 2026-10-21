import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "examples/skills/story-video-skill"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location(f"story_video_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = load("validate")
guard = load("guarded_mcp")


def plan_fixture():
    sys.path.insert(0, str(ROOT / "examples/tests"))
    from test_story_video_skill import production

    plan = production()
    plan["story_beats"] = [{"id": "beat_chase", "purpose": "A pursuit forces the protagonist to confront the threat"}]
    plan["turns"] = []
    plan["episode_assets"] = [asset for asset in plan["episode_assets"] if asset["kind"] == "location"]
    for shot in plan["shots"]:
        shot.update(audio_mode="h3_scene_audio", story_beat_ids=["beat_chase"],
                    scene_function="pursuit", shot_pattern="tracking_wide",
                    action_start="The protagonist spots the pursuer",
                    action_process="The protagonist sprints through the alley as the pursuer closes in",
                    action_end="The protagonist escapes behind the gate; the pursuer is blocked outside")
        for field in ("turn_id", "speaker", "listener", "normalized_line", "visual_dominance",
                      "listener_face_policy", "listener_mouth", "voice_asset"):
            shot.pop(field, None)
        shot["prompt"]["execution"] = "A wordless chase with clear screen direction and continuous geography"
    return plan


class CandidateSubmissionTests(unittest.TestCase):
    def test_action_story_without_dialogue_turns_passes_plan_validation(self):
        plan = plan_fixture()
        self.assertEqual(validator.validate_plan(plan), [])

    def test_batch_has_distinct_seeds_and_replay_reuses_each_receipt(self):
        plan = plan_fixture()
        plan["config"]["generation_settings"] = {"drafts": {"seed": 100}}
        with tempfile.TemporaryDirectory() as root:
            caller = Mock(side_effect=[{"job_id": "job-1"}, {"job_id": "job-2"}, {"job_id": "job-3"}])
            first = guard.execute_candidates(plan, root, "unused", "drafts", "lab", 1, 3, caller)
            self.assertEqual(first["status"], "completed")
            self.assertEqual([candidate["seed"] for candidate in first["candidates"]], [100, 101, 102])
            again = guard.execute_candidates(plan, root, "unused", "drafts", "lab", 1, 3, caller)
            self.assertEqual([candidate["response"]["job_id"] for candidate in again["candidates"]],
                             ["job-1", "job-2", "job-3"])
            self.assertEqual(caller.call_count, 3)

    def test_batch_is_limited_to_supported_image_operations_and_count(self):
        plan = plan_fixture()
        with tempfile.TemporaryDirectory() as root:
            for operation, count in (("compilations", 2), ("drafts", 5)):
                with self.assertRaises(ValueError):
                    guard.execute_candidates(plan, root, "unused", operation, "lab", 1, count, Mock())

    def test_failed_candidate_does_not_discard_successful_candidates(self):
        plan = plan_fixture()
        with tempfile.TemporaryDirectory() as root:
            caller = Mock(side_effect=[{"job_id": "job-1"}, RuntimeError("temporary submit failure"), {"job_id": "job-3"}])
            result = guard.execute_candidates(plan, root, "unused", "drafts", "lab", 1, 3, caller)
            self.assertEqual(result["status"], "partial")
            self.assertEqual([item["status"] for item in result["candidates"]], ["submitted", "failed", "submitted"])


class BatchQaTests(unittest.TestCase):
    def test_batch_qa_binds_each_result_to_exact_file_hash(self):
        with tempfile.TemporaryDirectory() as root:
            files = {"asset-1": "a.png", "asset-2": "b.png"}
            candidates = []
            for candidate_id, path in files.items():
                content = candidate_id.encode()
                (Path(root) / path).write_bytes(content)
                candidates.append({"id": candidate_id, "path": path,
                    "sha256": hashlib.sha256(content).hexdigest(), "status": "PASS",
                    "checks": {name: "PASS" for name in validator.CHECKS["draft"]},
                    "evidence": [f"Reviewed {candidate_id}"], "issues": []})
            report = {"reviewer": "reviewer-1", "review_mode": "independent", "limitations": [],
                      "candidates": candidates}
            result = validator.materialize_candidate_qa(report, root, "draft", 1, list(files.items()),
                                                        selections=[("asset-2", "asset")])
            self.assertEqual(set(result["qa_by_candidate"]), set(files))
            self.assertEqual(result["selected_qa_by_artifact"]["asset"]["shot_ids"], ["asset"])
            self.assertEqual(result["selected_qa_by_artifact"]["asset"]["input_sha256"]["b.png"], candidates[1]["sha256"])
            image_report = {**report, "candidates": [
                {**candidate, "checks": {name: "PASS" for name in validator.CHECKS["image"]}}
                for candidate in candidates]}
            grid = validator.materialize_candidate_qa(image_report, root, "image", 1, list(files.items()),
                selections=[("asset-2", "g1")], selected_shot_ids=["s0", "s1", "s2", "s3"])
            self.assertEqual(grid["selected_qa_by_artifact"]["g1"]["shot_ids"], ["s0", "s1", "s2", "s3"])
            candidates[0]["status"] = "FAIL"
            candidates[0]["checks"]["usability"] = "FAIL"
            candidates[0]["issues"] = [{"check": "usability", "severity": "blocking", "evidence": "Unusable"}]
            with self.assertRaisesRegex(ValueError, "Only a PASS"):
                validator.materialize_candidate_qa(report, root, "draft", 1, list(files.items()),
                    selections=[("asset-1", "asset")])
            candidates[0]["status"] = "PASS"
            candidates[0]["checks"]["usability"] = "PASS"
            candidates[0]["issues"] = []
            report["candidates"][1]["sha256"] = "wrong"
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                validator.materialize_candidate_qa(report, root, "draft", 1, list(files.items()))

    def test_additional_checks_and_silent_audio_na_follow_required_semantics(self):
        draft = {"schema_version": 1, "stage": "draft", "revision": 1, "reviewer": "reviewer-1",
                 "review_mode": "independent", "status": "PASS", "shot_ids": ["asset"],
                 "checks": {"usability": "PASS", "direction_match": "PASS", "style": "FAIL"},
                 "evidence": ["Usable concept", "Minor optional style mismatch"],
                 "issues": [{"check": "style", "severity": "minor"}], "limitations": []}
        self.assertEqual(validator.validate_qa(draft, "draft", 1, ["asset"]), [])
        media = {"schema_version": 1, "stage": "media", "revision": 1, "reviewer": "reviewer-1",
                 "review_mode": "independent", "status": "PASS", "shot_ids": ["s0"],
                 "checks": {"identity": "PASS", "speaker": "N/A", "dialogue": "N/A",
                            "voice": "N/A", "action": "PASS", "continuity": "PASS"},
                 "evidence": ["No dialogue or audio is designed for this silent shot"],
                 "issues": [], "limitations": []}
        self.assertEqual(validator.validate_qa(media, "media", 1, ["s0"],
                                               shot_audio_modes={"s0": "silent"}), [])
        self.assertTrue(validator.validate_qa(media, "media", 1, ["s0"]))


if __name__ == "__main__":
    unittest.main()
