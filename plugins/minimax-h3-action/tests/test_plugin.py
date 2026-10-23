# -*- coding: utf-8 -*-
"""Contract checks for the minimax-h3-action plugin manifest, compiler, and collaboration."""

import asyncio
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1]
REPO = PLUGIN.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
MANIFEST = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
WORKFLOW = json.loads(
    (PLUGIN / MANIFEST["capabilities"]["video.two_segment_reference"]["file"]).read_text(encoding="utf-8")
)
CAPABILITY = MANIFEST["capabilities"]["video.two_segment_reference"]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_package_module(name, path):
    """Load a collaboration module the way the gateway does: inside a synthetic package."""
    import types
    package_name = "videofree_plugin_test_minimax_h3_action"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(PLUGIN / "collaboration")]
        package.__package__ = package_name
        sys.modules[package_name] = package
    full_name = package_name + "." + name
    spec = importlib.util.spec_from_file_location(full_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


compiler = load_module("h3_action_compiler", PLUGIN / "compiler.py")
confirmation = load_module("h3_action_confirmation", PLUGIN / "collaboration" / "confirmation.py")
handler = load_package_module("handler", PLUGIN / "collaboration" / "handler.py")
pipeline = load_package_module("pipeline", PLUGIN / "collaboration" / "pipeline.py")
analysis = load_package_module("analysis", PLUGIN / "collaboration" / "analysis.py")


class FakeRequest:
    def __init__(self, plugin_parameters, duration_seconds=10):
        self.params = {"plugin_parameters": plugin_parameters, "width": 1344, "height": 768}
        self.duration_seconds = duration_seconds


def compiled(plugin_parameters, prompt="rainy rooftop fight", duration_seconds=10):
    from backend.integrations.comfyui.compiler import prune_workflow
    workflow = json.loads(json.dumps(WORKFLOW))
    workflow["136"]["inputs"]["prompt"] = prompt
    # Director confirmation always carries the marker; the compiler rejects it otherwise.
    plugin_parameters = dict(plugin_parameters, director_plan="confirmed")
    compiler.prepare(workflow, CAPABILITY, FakeRequest(plugin_parameters, duration_seconds),
                     {"image": [], "video": [], "audio": []}, "job-test", prompt)
    prune_workflow(workflow, CAPABILITY["output_nodes"])
    return workflow


def dangling(workflow):
    return [f"{node}.{key}->{value[0]}" for node, node_data in workflow.items() for key, value in
            node_data["inputs"].items() if isinstance(value, list) and str(value[0]) not in workflow]


class TestManifest(unittest.TestCase):
    def test_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema is not installed")
        schema = json.loads((REPO / "docs" / "schemas" / "plugin-manifest-v1.schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(MANIFEST, schema)

    def _localizable_keys(self, node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key.endswith("_key") and isinstance(value, str):
                    yield value
                else:
                    yield from self._localizable_keys(value)
        elif isinstance(node, list):
            for item in node:
                yield from self._localizable_keys(item)

    def test_locale_packs_cover_every_declared_key(self):
        localization = MANIFEST["localization"]
        keys = set(self._localizable_keys(MANIFEST))
        self.assertTrue(keys)
        for locale, path in localization["messages"].items():
            pack = json.loads((PLUGIN / path).read_text(encoding="utf-8"))
            missing = keys - set(pack)
            self.assertFalse(missing, f"{locale} pack missing keys: {sorted(missing)}")

    def test_director_mode_registered_with_handler(self):
        modes = {mode["id"]: mode for mode in MANIFEST["modes"]}
        self.assertEqual(modes["director"]["handler"], "collaboration/handler.py:director")
        self.assertEqual(CAPABILITY["processing_modes"], ["director"])
        self.assertEqual(CAPABILITY["compiler_handler"], "compiler.py:prepare")
        self.assertEqual(CAPABILITY["confirmation_handler"], "collaboration/confirmation.py:prepare")

    def test_minimal_ui_matches_minimax_h3_composer(self):
        body = [f for f in CAPABILITY["ui"]["fields"] if f["section"] == "body"]
        self.assertEqual({f["bind"] for f in body},
                         {"prompt", "settings.reference_image", "settings.reference_video", "settings.reference_audio"})
        # The user owns the frame: ratio and resolution are selectable, like minimax-h3.
        settings = [f for f in CAPABILITY["ui"]["fields"] if f["section"] == "settings"]
        self.assertEqual({f["bind"] for f in settings}, {"settings.ratio", "settings.resolution"})
        self.assertEqual({f["default"] for f in settings}, {"16:9", "480P"})
        duration = next(f for f in CAPABILITY["ui"]["fields"] if f["bind"] == "settings.duration")
        self.assertEqual((duration["minimum"], duration["maximum"], duration["default"]), (1, 75, 10))
        self.assertEqual(duration["section"], "submit")
        self.assertEqual(CAPABILITY["duration"], {"min": 1, "max": 75, "default": 10})

    def test_segment_parameters_declared(self):
        parameters = CAPABILITY["parameters"]
        self.assertEqual((parameters["segments"]["minimum"], parameters["segments"]["maximum"],
                          parameters["segments"]["default"]), (1, 5, 1))
        for index in range(2, 6):
            self.assertFalse(parameters[f"prompt_{index}"]["required"])

    def test_generation_capability_is_registered_in_workbench_ui(self):
        self.assertFalse(CAPABILITY.get("ui_hidden", False))
        model = next(item for item in MANIFEST["ui_models"] if item["id"] == "minimax-h3-action")
        self.assertEqual(model["category"], "video")
        self.assertIn("video.two_segment_reference", {item["capability_id"] for item in model["functions"]})

    def test_generation_collaboration_has_its_own_runtime_ui(self):
        entry = MANIFEST["collaboration_ui"]["entry"]
        self.assertEqual(entry, "ui/dist/collaboration.js")
        self.assertTrue((PLUGIN / entry).is_file())
        bundle = (PLUGIN / entry).read_text(encoding="utf-8")
        source = (PLUGIN / "ui/Collaboration.js").read_text(encoding="utf-8")
        self.assertTrue(bundle.endswith(source))
        self.assertIn("const H3A_STYLES =", bundle)
        self.assertIn(".h3a-collaboration", bundle)

    def test_plugin_does_not_register_an_application_menu(self):
        self.assertNotIn("application", MANIFEST)
        self.assertFalse((PLUGIN / "ui" / "dist" / "index.js").exists())


class TestWorkflow(unittest.TestCase):
    def test_links_reference_existing_nodes(self):
        self.assertEqual(dangling(WORKFLOW), [])

    def test_bindings_reference_existing_nodes(self):
        targets = [b["node"] for b in CAPABILITY["prompt_bindings"]]
        targets += [b["node"] for bindings in CAPABILITY["media_bindings"].values() for b in bindings]
        targets += [b["node"] for bindings in CAPABILITY["parameter_bindings"].values() for b in bindings]
        targets += [b["node"] for b in CAPABILITY["output_bindings"]]
        targets += CAPABILITY["output_nodes"]
        for node_id in targets:
            self.assertIn(str(node_id), WORKFLOW, f"binding node {node_id} missing from workflow")

    def test_media_binding_slots_match_node_inputs(self):
        source = json.loads(
            (PLUGIN / "workflows" / "source" / "10.16-minimax-action-two-segment.ui.json").read_text(encoding="utf-8")
        )
        names = {str(node["id"]): {entry["name"] for entry in node.get("inputs", [])} for node in source["nodes"]}
        for bindings in CAPABILITY["media_bindings"].values():
            for binding in bindings:
                self.assertIn(binding["input"], names[str(binding["node"])],
                              f"slot {binding['input']} not on node {binding['node']}")

    def test_final_output_is_saved_video(self):
        self.assertEqual(CAPABILITY["output_nodes"], ["237"])
        output = WORKFLOW["237"]
        self.assertEqual(output["class_type"], "VHS_VideoCombine")
        self.assertTrue(output["inputs"]["save_output"])

    def test_video_and_audio_references_bind_to_each_segment_template(self):
        for media_type, input_name in (("video", "ref_videos.ref_video_0"),
                                       ("audio", "ref_audios.ref_audio_0")):
            bindings = CAPABILITY["media_bindings"][media_type]
            self.assertEqual({item["node"] for item in bindings}, {"136", "224"})
            self.assertTrue(all(item["input"] == input_name for item in bindings))

    def test_cloned_segments_keep_media_inputs_bound_to_segment_template(self):
        workflow = json.loads(json.dumps(WORKFLOW))
        workflow["224"]["inputs"].update({
            "ref_videos.ref_video_0": "reference-video.mp4",
            "ref_audios.ref_audio_0": "reference-audio.wav",
        })
        clone = compiler._clone_segment(workflow, 3, "segment 3")
        self.assertEqual(workflow[clone["224"]]["inputs"]["ref_videos.ref_video_0"], "reference-video.mp4")
        self.assertEqual(workflow[clone["224"]]["inputs"]["ref_audios.ref_audio_0"], "reference-audio.wav")

    def test_duration_math_feeds_both_segments(self):
        for segment in ("136", "224"):
            self.assertEqual(WORKFLOW[segment]["inputs"]["length"], ["131", 1])
        self.assertEqual(CAPABILITY["parameter_bindings"]["duration"], [{"node": "132", "input": "value"}])
        self.assertEqual(WORKFLOW["131"]["inputs"]["values.a"], ["132", 0])

    def test_block_sparse_attention_uses_dynamic_combo_v3_keys(self):
        # comfy-core >= 0.37 validates nested DynamicCombo inputs under dotted keys
        # and only accepts the current option keys (sol-attn / sla / vsa).
        for node_id in ("165", "222", "239"):
            inputs = WORKFLOW[node_id]["inputs"]
            self.assertEqual(inputs["selection"], "sol-attn")
            self.assertIn("selection.tau", inputs)
            self.assertNotIn("tau", inputs)


class TestCompiler(unittest.TestCase):
    def test_direct_submission_without_director_marker_is_rejected(self):
        # The framework always registers a direct mode; the compiler is the guard.
        with self.assertRaises(compiler.PluginError):
            compiler.prepare(json.loads(json.dumps(WORKFLOW)), CAPABILITY, FakeRequest({}),
                             {"image": [], "video": [], "audio": []}, "job-test", "punch")

    def test_two_segments_sets_prompts_and_seeds(self):
        workflow = compiled({"segments": 2, "prompt_2": "finisher combo"})
        self.assertEqual(workflow["136"]["inputs"]["prompt"], "rainy rooftop fight")
        self.assertEqual(workflow["224"]["inputs"]["prompt"], "finisher combo")
        self.assertNotEqual(workflow["129"]["inputs"]["noise_seed"], workflow["225"]["inputs"]["noise_seed"])
        self.assertEqual(dangling(workflow), [])
        self.assertNotIn("3224", workflow)

    def test_missing_continuations_reuse_main_prompt(self):
        workflow = compiled({"segments": 2})
        self.assertEqual(workflow["224"]["inputs"]["prompt"], "rainy rooftop fight")

    def test_four_segments_clone_and_cascade(self):
        workflow = compiled({"segments": 4, "prompt_2": "b2", "prompt_3": "b3", "prompt_4": "b4"})
        self.assertEqual(dangling(workflow), [])
        # Clones exist for segments 3 and 4; segment 2 stays the template subgraph.
        self.assertNotIn("2224", workflow)
        for prefix in ("3", "4"):
            for suffix in ("224", "215", "219", "216", "217", "227", "232"):
                self.assertIn(prefix + suffix, workflow)
        self.assertEqual(workflow["3224"]["inputs"]["prompt"], "b3")
        self.assertEqual(workflow["4224"]["inputs"]["prompt"], "b4")
        # Guide cascade: each clone is guided by the previous segment's last frame.
        self.assertEqual(workflow["3227"]["inputs"]["images"], ["216", 0])
        self.assertEqual(workflow["4227"]["inputs"]["images"], ["3216", 0])
        # Uniform plan: every guide takes the previous segment's last-but-one window.
        self.assertEqual(workflow["227"]["inputs"]["start_index"], 237)  # frames(10)=243
        self.assertEqual(workflow["3227"]["inputs"]["start_index"], 237)
        self.assertEqual(workflow["3232"]["inputs"]["image"], ["3227", 0])
        # Shared model chain and loaders stay referenced.
        self.assertEqual(workflow["3215"]["inputs"]["model"], ["222", 0])
        self.assertEqual(workflow["4224"]["inputs"]["clip"], ["128", 0])
        # Merge chains grew to four segments.
        self.assertEqual(workflow["234"]["inputs"]["inputcount"], 4)
        self.assertEqual(workflow["234"]["inputs"]["image_4"], ["4216", 0])
        self.assertEqual(workflow["3235"]["inputs"]["audio1"], ["235", 0])
        self.assertEqual(workflow["4235"]["inputs"]["audio1"], ["3235", 0])
        self.assertEqual(workflow["236"]["inputs"]["audio"], ["4235", 0])
        # Without a durations plan every segment shares the framework-bound length.
        self.assertEqual(workflow["224"]["inputs"]["length"], ["131", 1])
        self.assertEqual(workflow["3224"]["inputs"]["length"], ["131", 1])

    def test_segment_count_is_clamped(self):
        workflow = compiled({"segments": 9})
        self.assertIn("5224", workflow)  # clamped up to the 5-segment cap
        self.assertEqual(workflow["234"]["inputs"]["inputcount"], 5)
        self.assertNotIn("3224", compiled({"segments": "bad"}))

    def test_single_segment_bypasses_merge_chain(self):
        # ImageBatchMulti needs inputcount>=2 and AudioConcat requires audio2,
        # so a single clip rewires the combine straight onto segment 1's decoders
        # and the merge chain is pruned as unreachable.
        workflow = compiled({"segments": 1, "durations": "10"})
        self.assertEqual(workflow["132"]["inputs"]["value"], 10.0)
        self.assertEqual(workflow["237"]["inputs"]["images"], ["122", 0])
        self.assertEqual(workflow["236"]["inputs"]["audio"], ["121", 0])
        self.assertNotIn("234", workflow)
        self.assertNotIn("235", workflow)
        self.assertEqual(dangling(workflow), [])
        self.assertIn("237", workflow)
        # Segment 2's subgraph is unreachable and pruned away.
        self.assertNotIn("224", workflow)

    def test_compiler_overwrites_total_duration_binding(self):
        # The framework binds the whole-video total to node 132; the compiler must
        # never let a >15s total reach a single clip.
        workflow = compiled({"segments": 2})  # FakeRequest has no durations
        self.assertLessEqual(workflow["132"]["inputs"]["value"], 15.0)

    def test_uniform_plan_keeps_shared_length(self):
        workflow = compiled({"segments": 3, "prompt_2": "b", "prompt_3": "c"})
        self.assertEqual(workflow["224"]["inputs"]["length"], ["131", 1])
        self.assertEqual(workflow["3224"]["inputs"]["length"], ["131", 1])
        self.assertNotIn("2131", workflow)

    def test_per_segment_durations_get_own_length_pairs(self):
        workflow = compiled({"segments": 3, "prompt_2": "b", "prompt_3": "c", "durations": "12,8,10"})
        self.assertEqual(workflow["132"]["inputs"]["value"], 12.0)  # segment 1 keeps the bound node
        self.assertEqual(workflow["224"]["inputs"]["length"], ["2131", 1])
        self.assertEqual(workflow["2132"]["inputs"]["value"], 8.0)
        self.assertEqual(workflow["2131"]["inputs"]["values.a"], ["2132", 0])
        self.assertEqual(workflow["3224"]["inputs"]["length"], ["3131", 1])
        self.assertEqual(workflow["3132"]["inputs"]["value"], 10.0)
        self.assertEqual(dangling(workflow), [])
        self.assertIn("237", workflow)  # length pairs stay reachable after pruning

    def test_pruned_graph_reaches_final_output(self):
        workflow = compiled({"segments": 5})
        self.assertIn("237", workflow)
        self.assertIn("5216", workflow)  # every clone stays reachable through the merge chain


class TestCollaboration(unittest.TestCase):
    def test_finalize_clamps_and_fills_prompts(self):
        result = {"status": "ready", "optimized_prompt": "main english",
                  "optimized_prompt_zh": "【第一段】…",
                  "generation_payload": {"parameters": {"segments": 4, "prompt_2": "p2", "prompt_1": "x",
                                                           "durations": "2,2,2,2"},
                                         "settings": {"duration": 8, "ratio": "9:16", "resolution": "720P"}}}
        handler.finalize(result)
        parameters = result["generation_payload"]["parameters"]
        self.assertEqual(parameters["segments"], 4)
        self.assertNotIn("prompt_1", parameters)
        self.assertEqual(parameters["prompt_2"], "p2")
        self.assertEqual(parameters["prompt_3"], "main english")  # missing continuation falls back
        self.assertEqual(parameters["prompt_4"], "main english")
        self.assertNotIn("prompt_5", parameters)
        # The user owns ratio/resolution; the director payload keeps only duration.
        self.assertEqual(result["generation_payload"]["settings"], {"duration": 8})

    def test_finalize_accepts_only_complete_durations_matching_total(self):
        # Wire format is the comma-separated string; lists (in-process) normalize to it.
        result = {"status": "ready", "optimized_prompt": "m",
                  "generation_payload": {"parameters": {"segments": 3, "durations": [12, 8, 10]},
                                         "settings": {"duration": 30}}}
        handler.finalize(result)
        self.assertEqual(result["generation_payload"]["parameters"]["durations"], "12,8,10")
        result = {"status": "ready", "optimized_prompt": "m",
                  "generation_payload": {"parameters": {"segments": 3, "durations": "12.5,8,10"},
                                         "settings": {"duration": 30.5}}}
        handler.finalize(result)
        self.assertEqual(result["generation_payload"]["parameters"]["durations"], "12.5,8,10")
        bad = {"status": "ready", "optimized_prompt": "m",
               "generation_payload": {"parameters": {"segments": 3, "durations": "12,8,9"},
                                      "settings": {"duration": 30}}}
        with self.assertRaisesRegex(ValueError, "合计必须等于"):
            handler.finalize(bad)
        bad["generation_payload"]["parameters"]["durations"] = "12,20, -2"
        with self.assertRaisesRegex(ValueError, "有效的各段时长"):
            handler.finalize(bad)

    def test_confirmation_patch_filters_to_declared_parameters(self):
        patch = confirmation.prepare({"settings": {"duration": 20}}, {"generation_payload": {
            "parameters": {"segments": 2, "prompt_2": " p2 ", "prompt_3": "beyond", "unknown": "x",
                           "durations": [10, 10]},
            "settings": {"duration": 20, "ratio": "9:16", "resolution": "4K", "extra": 1}}}, None)
        self.assertEqual(patch["parameters"], {"segments": 2, "prompt_2": "p2", "durations": "10,10",
                                               "director_plan": "confirmed"})
        # The selected total duration is preserved; ratio and resolution
        # belong to the submit UI.
        self.assertEqual(patch["settings"], {"duration": 20})

    def test_confirmation_accepts_valid_durations_only(self):
        # Stored lists convert to the declared string wire format at confirmation.
        patch = confirmation.prepare({"settings": {"duration": 20}}, {"generation_payload": {
            "parameters": {"segments": 2, "prompt_2": "p2", "durations": [12, 8]},
            "settings": {"duration": 20}}}, None)
        self.assertEqual(patch["parameters"]["durations"], "12,8")
        patch = confirmation.prepare({"settings": {"duration": 20.5}}, {"generation_payload": {
            "parameters": {"segments": 2, "prompt_2": "p2", "durations": "12.5,8"},
            "settings": {"duration": 20.5}}}, None)
        self.assertEqual(patch["parameters"]["durations"], "12.5,8")
        for durations in ([12, 20], [12], "12,abc"):
            with self.assertRaisesRegex(ValueError, "有效的分段时长"):
                confirmation.prepare({"settings": {"duration": 20}}, {"generation_payload": {
                    "parameters": {"segments": 2, "prompt_2": "p2", "durations": durations},
                    "settings": {"duration": 20}}}, None)
        with self.assertRaisesRegex(ValueError, "合计与整片总时长不一致"):
            confirmation.prepare({"settings": {"duration": 25}}, {"generation_payload": {
                "parameters": {"segments": 2, "prompt_2": "p2", "durations": [12, 8]},
                "settings": {"duration": 20}}}, None)

    def test_confirmation_rejects_out_of_range_total_duration_and_frame_overrides(self):
        # duration is now the whole-video total: 20s is legal, 90s is not;
        # ratio/resolution stay user-owned and are always dropped.
        patch = confirmation.prepare({"settings": {"duration": 20}}, {"generation_payload": {
            "parameters": {"segments": 2, "prompt_2": "p2", "durations": [10, 10]},
            "settings": {"duration": 20, "ratio": "9:16", "resolution": "720P"}}}, None)
        self.assertEqual(patch["settings"], {"duration": 20})
        with self.assertRaisesRegex(ValueError, "有效的分段时长"):
            confirmation.prepare({"settings": {"duration": 90}}, {"generation_payload": {
                "parameters": {"segments": 2, "prompt_2": "p2", "durations": [45, 45]},
                "settings": {"duration": 90}}}, None)

    def test_confirmation_empty_payload_is_noop(self):
        self.assertEqual(confirmation.prepare({}, {}, None), {})

    def test_full_h3_format_is_enforced_per_segment(self):
        # Every segment draft must carry the complete ref2va six-section contract.
        complete = ("subject_definitions: x\nsummary: x\nretention_analysis: x\n"
                    "detailed_description: x\noverall_soundscape: x\nnon_diegetic_music: N/A")
        self.assertEqual(analysis.agent_prompt_issues(complete, "minimax-h3-action", "reference"), [])
        issues = analysis.agent_prompt_issues("just a plain paragraph", "minimax-h3-action", "reference")
        self.assertTrue(any("subject_definitions" in item for item in issues))
        self.assertTrue(any("sections are out of order" in item
                            for item in analysis.agent_prompt_issues(
                                "summary: x\nsubject_definitions: x\nretention_analysis: x\n"
                                "detailed_description: x\noverall_soundscape: x\nnon_diegetic_music: N/A",
                                "minimax-h3-action", "reference")))

    def test_segment_prompt_uses_deterministic_headings_and_relative_timestamps(self):
        full = (
            "subject_definitions: <Subject 1> a traveler\n"
            "summary: A traveler crosses the valley.\n"
            "retention_analysis: Preserve the traveler throughout.\n"
            "detailed_description:\nCinematic live action.\n"
            "[Shot 1] The traveler enters the valley.\n"
            "[Shot 2] At 00:08.000, the traveler reaches the bridge.\n"
            "[Shot 3] At 00:16.000, the traveler crosses it.\n"
            "overall_soundscape: Wind crosses the grass.\n"
            "non_diegetic_music: N/A")
        draft = pipeline.compile_segment_prompt(2, {
            "shots": "[Shot 2] At 00:08.000, the traveler reaches the bridge.\n"
                     "[Shot 3] At 00:16.000, the traveler crosses it.",
            "sound": "Wind rises.", "music": "N/A",
        }, full)
        sections = pipeline.draft_sections(draft)
        self.assertEqual(list(sections), list(pipeline.SECTION_LABELS))
        self.assertIn("[Shot 1] the traveler reaches the bridge.", sections["detailed_description"])
        self.assertIn("[Shot 2] At 00:08.000,", sections["detailed_description"])
        self.assertIn("Continue directly from the preceding segment's final frame.", sections["detailed_description"])
        self.assertIn(pipeline.NO_DUPLICATES_CLAUSE, sections["summary"])
        self.assertEqual(sections["overall_soundscape"], "Wind rises.")
        self.assertEqual(analysis.agent_prompt_issues(draft, "minimax-h3-action", "reference"), [])

    def test_retry_reuses_successful_stages_and_translations(self):
        full = (
            "subject_definitions: <Subject 1> a traveler\n"
            "summary: A traveler crosses the valley.\n"
            "retention_analysis: Preserve the traveler throughout.\n"
            "detailed_description:\nCinematic live action.\n"
            "[Shot 1] The traveler enters the valley.\n"
            "[Shot 2] At 00:10.000, the traveler reaches the bridge.\n"
            "overall_soundscape: Wind crosses the grass.\n"
            "non_diegetic_music: N/A")
        plan = {"status": "ready", "segments": 2, "segment_cuts": [
            {"index": 1, "duration": 10, "shots": "[Shot 1] The traveler enters the valley.",
             "end_state": "The traveler enters the valley.", "sound": "", "music": ""},
            {"index": 2, "duration": 10, "shots": "[Shot 2] At 00:10.000, the traveler reaches the bridge.",
             "end_state": "The traveler reaches the bridge.", "sound": "", "music": ""},
        ]}
        session = {"generation": {"mode": "reference", "duration_seconds": 20},
                   "user_requests": ["A journey"]}
        translated = {}

        def translate(draft, *_):
            translated[draft] = translated.get(draft, 0) + 1
            if "reaches the bridge" in draft and translated[draft] == 1:
                raise ValueError("temporary translation failure")
            return "旅人继续前行。"

        with (patch.object(pipeline, "run_director_skill_planner", return_value=([], [])) as skills,
              patch.object(pipeline, "compile_full_draft", return_value=full) as compile_full,
              patch.object(pipeline, "run_segment_splitter", return_value=plan) as split,
              patch.object(pipeline, "conform_segments", side_effect=lambda drafts, *_: (drafts, "")),
              patch.object(pipeline, "translate_segment", side_effect=translate)):
            with self.assertRaisesRegex(ValueError, "temporary translation failure"):
                pipeline.run_segmented_production(session, {}, None, lambda *_: "")
            result = pipeline.run_segmented_production(session, {}, None, lambda *_: "")

        self.assertEqual(result["status"], "ready")
        self.assertEqual(skills.call_count, 1)
        self.assertEqual(compile_full.call_count, 1)
        self.assertEqual(split.call_count, 1)
        self.assertEqual(sorted(translated.values()), [1, 2])
        self.assertNotIn("failed_stage", session["_minimax_h3_action_checkpoint"])

    def test_compiler_failure_replans_cuts_without_redrafting_full_story(self):
        full = (
            "subject_definitions: <Subject 1> a traveler\n"
            "summary: A traveler crosses the valley.\n"
            "retention_analysis: Preserve the traveler throughout.\n"
            "detailed_description:\nCinematic live action.\n"
            "[Shot 1] The traveler enters the valley.\n"
            "[Shot 2] At 00:10.000, the traveler reaches the bridge.\n"
            "overall_soundscape: Wind crosses the grass.\nnon_diegetic_music: N/A")
        plan = {"status": "ready", "segments": 2, "segment_cuts": [
            {"index": 1, "duration": 10, "shots": "[Shot 1] The traveler enters the valley.",
             "end_state": "The traveler enters the valley.", "sound": "", "music": ""},
            {"index": 2, "duration": 10, "shots": "[Shot 2] At 00:10.000, the traveler reaches the bridge.",
             "end_state": "The traveler reaches the bridge.", "sound": "", "music": ""},
        ]}
        session = {"generation": {"mode": "reference", "duration_seconds": 20},
                   "user_requests": ["A journey"]}
        original_compile = pipeline.compile_segment_prompt
        attempts = {"count": 0}

        def compile_with_one_transient_failure(*args):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ValueError("temporary segment mapping failure")
            return original_compile(*args)

        with (patch.object(pipeline, "run_director_skill_planner", return_value=([], [])),
              patch.object(pipeline, "compile_full_draft", return_value=full) as compile_full,
              patch.object(pipeline, "run_segment_splitter", return_value=plan) as split,
              patch.object(pipeline, "compile_segment_prompt", side_effect=compile_with_one_transient_failure),
              patch.object(pipeline, "conform_segments", side_effect=lambda drafts, *_: (drafts, "")),
              patch.object(pipeline, "translate_segment", return_value="旅人继续前行。")):
            with self.assertRaisesRegex(ValueError, "temporary segment mapping failure"):
                pipeline.run_segmented_production(session, {}, None, lambda *_: "")
            result = pipeline.run_segmented_production(session, {}, None, lambda *_: "")

        self.assertEqual(result["status"], "ready")
        self.assertEqual(compile_full.call_count, 1)
        self.assertEqual(split.call_count, 2)

    def test_resolve_production_structure_arithmetic(self):
        # The UI duration field is the whole-video total; <=15s stays one segment.
        explicit = pipeline.resolve_production_structure(
            ["史诗对决，分成5段，每段10秒。"], {"duration_seconds": 50})
        self.assertEqual({key: explicit[key] for key in ("segments", "total_duration", "per_segment_duration")},
                         {"segments": 5, "total_duration": 50.0, "per_segment_duration": 10.0})
        self.assertEqual(explicit["hardware_profile"]["status"], "unavailable")
        self.assertEqual(pipeline.resolve_production_structure(
            ["总时长大概50秒的追逐戏"], {"duration_seconds": 50})["segments"], 4)  # ceil(50/15)
        short = pipeline.resolve_production_structure(["打一架"], {"duration_seconds": 10})
        self.assertEqual({key: short[key] for key in ("segments", "total_duration", "per_segment_duration")},
                         {"segments": 1, "total_duration": 10.0, "per_segment_duration": 10.0})
        # UI total wins over a stale total in the prompt text.
        self.assertEqual(pipeline.resolve_production_structure(
            ["总时长大概50秒，分成5段"], {"duration_seconds": 30})["total_duration"], 30.0)
        # A short total never splits, even if the prompt asks for segments.
        self.assertEqual(pipeline.resolve_production_structure(
            ["分成5段"], {"duration_seconds": 10})["segments"], 1)
        # Segment count must keep every clip within 15 seconds.
        self.assertEqual(pipeline.resolve_production_structure(
            ["分成2段"], {"duration_seconds": 50})["segments"], 4)  # ceil(50/15)

    def test_comfyui_vram_profile_is_advisory_and_changes_default_segment_plan(self):
        snapshot = {"devices": [{"type": "cuda", "name": "GPU", "total_memory_bytes": 16,
                                 "free_memory_bytes": 2}]}
        constrained = pipeline.resolve_production_structure([], {"duration_seconds": 30,
                                                                   "hardware_snapshot": snapshot})
        self.assertEqual(constrained["segments"], 3)
        self.assertEqual(constrained["hardware_profile"]["planning_segment_seconds"], 10)
        self.assertIn("not a guarantee", constrained["hardware_profile"]["warning"])
        available = pipeline.comfyui_segment_profile({"devices": [
            {"type": "cuda", "total_memory_bytes": 16, "free_memory_bytes": 8}]})
        self.assertEqual(available["planning_segment_seconds"], 15)
        self.assertEqual(pipeline.comfyui_segment_profile(None)["status"], "unavailable")


    def test_retry_reuses_requirements_without_appending_internal_command(self):
        session = {
            "id": "agent-test",
            "generation": {"duration_seconds": 20},
            "user_requests": ["A traveler crosses the valley"],
            "requirements_messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "original request"},
            ],
            "requirements": {"status": "ready"},
            "last_failure": "temporary translation failure",
            "_minimax_h3_action_checkpoint": {"failed_stage": "translation", "failed_segment": 2},
        }

        class Runtime:
            def session(self, _session_id):
                return session

            def save_session(self, _session):
                pass

            def start_progress(self, *_args):
                pass

            def update_progress(self, *_args):
                pass

            def finish_progress(self, *_args):
                pass

            def fail_progress(self, *_args):
                pass

            def call_model(self, *_args):
                raise AssertionError("completed requirements must not call the model during retry")

        request = SimpleNamespace(
            session_id="agent-test", message=handler.RETRY_FAILED_STAGE_COMMAND,
            duration_seconds=20, progress_id="progress-test",
        )
        ready_result = {
            "status": "ready", "optimized_prompt": "valid execution prompt",
            "optimized_prompt_zh": "有效执行稿", "generation_payload": {
                "parameters": {"segments": 2, "durations": "10,10"},
                "settings": {"duration": 20},
            },
        }
        before_messages = list(session["requirements_messages"])
        before_requests = list(session["user_requests"])
        with patch.object(handler, "run_segmented_production", return_value=ready_result) as run_pipeline:
            result = asyncio.run(handler.director(request, Runtime()))

        self.assertEqual(result["status"], "ready")
        self.assertEqual(run_pipeline.call_count, 1)
        self.assertEqual(session["requirements_messages"], before_messages)
        self.assertEqual(session["user_requests"], before_requests)

    def test_internal_retry_command_requires_a_recorded_failure(self):
        session = {"id": "agent-test", "requirements_messages": [], "user_requests": []}

        class Runtime:
            def session(self, _session_id):
                return session

            def save_session(self, _session):
                pass

            def start_progress(self, *_args):
                pass

            def fail_progress(self, *_args):
                pass

        request = SimpleNamespace(
            session_id="agent-test", message=handler.RETRY_FAILED_STAGE_COMMAND,
            duration_seconds=10, progress_id="progress-test",
        )
        with patch.object(handler, "run_segmented_production") as run_pipeline:
            with self.assertRaisesRegex(Exception, "没有失败阶段可重试"):
                asyncio.run(handler.director(request, Runtime()))
        run_pipeline.assert_not_called()

    def test_explicit_segment_structure_extraction(self):
        structure = pipeline.explicit_segment_structure([
            "史诗级生死对决，总时长大概50秒，分成5段，每段10秒。云海之上的山顶石台上……"])
        self.assertEqual(structure, {"segments": 5, "per_segment_duration": 10.0, "total_duration": 50.0})
        self.assertEqual(pipeline.explicit_segment_structure(["一个雨夜对话场景"]), {})

    def test_split_plan_validation(self):
        full_draft = (
            "subject_definitions: two fighters\nsummary: one duel\nretention_analysis: kept\n"
            "detailed_description:\n[Shot 1] At 00:00.000, A charges and settles.\n"
            "[Shot 2] At 00:06.000, B swings and yells 万剑归一！ then roars.\n"
            "[Shot 3] At 00:12.000, the blades clash.\n"
            "[Shot 4] At 00:18.000, the frame freezes.\n"
            "overall_soundscape: rain\nnon_diegetic_music: epic")
        structure = {"segments": 2, "total_duration": 20.0, "per_segment_duration": 10.0}
        requirements = {"audio_plan": {"dialogue": {"lines": [{"text": "万剑归一！"}]}}}
        good = {"status": "ready", "segments": 2, "segment_cuts": [
            {"index": 1, "duration": 12, "sound": "", "music": "", "cut_reason": "roar settles",
             "shots": "[Shot 1] At 00:00.000, A charges and settles.\n"
                      "[Shot 2] At 00:06.000, B swings and yells 万剑归一！ then roars.",
             "end_state": "then roars."},
            {"index": 2, "duration": 8, "sound": "", "music": "", "cut_reason": "freeze",
             "shots": "[Shot 3] At 00:12.000, the blades clash.\n"
                      "[Shot 4] At 00:18.000, the frame freezes.",
             "end_state": "the frame freezes."}]}
        self.assertEqual(pipeline.split_plan_issues(good, full_draft, structure, requirements), [])
        shrunk = {"status": "ready", "segments": 3, "segment_cuts": []}
        issues = pipeline.split_plan_issues(shrunk, full_draft, structure, requirements)
        self.assertTrue(any("required count 2" in item for item in issues))
        dropped = json.loads(json.dumps(good))
        dropped["segment_cuts"][1]["shots"] = "[Shot 4] At 00:18.000, the frame freezes."
        issues = pipeline.split_plan_issues(dropped, full_draft, structure, requirements)
        self.assertTrue(any("partitioned in order" in item for item in issues))
        wrong_total = json.loads(json.dumps(good))
        wrong_total["segment_cuts"][1]["duration"] = 9
        self.assertTrue(any("durations must sum" in item
                            for item in pipeline.split_plan_issues(wrong_total, full_draft, structure, requirements)))
        rewritten = json.loads(json.dumps(good))
        rewritten["segment_cuts"][0]["shots"] = "[Shot 1] A charges. [Shot 2] B swings and yells 万剑归一！"
        issues = pipeline.split_plan_issues(rewritten, full_draft, structure, requirements)
        self.assertTrue(any("verbatim" in item for item in issues))
        invented = json.loads(json.dumps(good))
        invented["segment_cuts"][1]["end_state"] = "both fighters bow."
        issues = pipeline.split_plan_issues(invented, full_draft, structure, requirements)
        self.assertTrue(any("end_state" in item for item in issues))

    def test_segment_splitter_forces_structure_and_verbatim(self):
        full_draft = (
            "subject_definitions: x\nsummary: x\nretention_analysis: x\n"
            "detailed_description:\n[Shot 1] At 00:00.000, A settles.\n"
            "[Shot 2] At 00:08.000, B freezes.\n"
            "overall_soundscape: rain\nnon_diegetic_music: epic")
        structure = {"segments": 2, "total_duration": 16.0, "per_segment_duration": 8.0}
        good = {"status": "ready", "segments": 2, "segment_cuts": [
            {"index": 1, "duration": 8, "shots": "[Shot 1] At 00:00.000, A settles.",
             "sound": "", "music": "", "end_state": "A settles.", "cut_reason": "settled"},
            {"index": 2, "duration": 8, "shots": "[Shot 2] At 00:08.000, B freezes.",
             "sound": "", "music": "", "end_state": "B freezes.", "cut_reason": "freeze"}]}
        replies = iter([json.dumps({"status": "ready", "segments": 5, "segment_cuts": []}),
                        json.dumps(good)])
        seen = []

        def call_model(messages, max_tokens):
            seen.append(messages)
            return next(replies)

        plan = pipeline.run_segment_splitter(full_draft, structure, {}, call_model)
        self.assertEqual(plan["segments"], 2)
        self.assertIn("required_segments\": 2", seen[0][1]["content"])
        self.assertIn("segment count is fixed", seen[1][-1]["content"])

    def test_director_cancellation_is_not_treated_as_planner_failure(self):
        from backend.modules.shared.plugin_runtime import AgentCollaborationCancelled

        def cancelled(_messages, _tokens):
            raise AgentCollaborationCancelled()

        with self.assertRaises(AgentCollaborationCancelled):
            pipeline.run_director_skill_planner({}, {"capabilities": []}, [], cancelled)

    def test_empty_translation_retries_then_requires_a_result(self):
        replies = iter(['{"status":"ready"}', '{"optimized_prompt_zh":"中文执行稿"}'])
        translated = pipeline.translate_segment("English draft", {}, lambda *_: next(replies))
        self.assertEqual(translated, "中文执行稿")
        with self.assertRaisesRegex(ValueError, "连续两次"):
            pipeline.translate_segment("English draft", {}, lambda *_: '{"optimized_prompt_zh":" "}')

    def test_conformance_review_invalid_segment_index_is_reported(self):
        review = json.dumps({"conforms": False, "issues": [
            {"segment_index": 9, "problem": "missing continuation"},
        ]})
        drafts, warning = pipeline.conform_segments(
            ["draft one", "draft two"], [{}, {}], "full", {}, {}, [],
            lambda *_: review, "", "digest")
        self.assertEqual(drafts, ["draft one", "draft two"])
        self.assertIn("无效的 segment_index", warning)

    def test_guide_uses_five_frame_clip_skipping_last_frame(self):
        # Continuity guide: the 5 frames just before the final one (avoids flash/motion-blur
        # frames); MiniMaxH3AddGuide anchors batches of >=5 frames as a motion clip.
        # ComfyUI validates start_index >= -1, so the template default stays legal and
        # the compiler rewrites it to the previous segment's (frames - 6).
        self.assertGreaterEqual(WORKFLOW["227"]["inputs"]["start_index"], -1)
        self.assertEqual(WORKFLOW["227"]["inputs"]["num_frames"], 5)
        workflow = compiled({"segments": 2, "durations": "12.5,12.5"})
        # 12.5s -> 300 frames -> 311 after the 17k+5 rounding; guide starts at 311-6.
        self.assertEqual(workflow["227"]["inputs"]["start_index"], 305)

    def test_contracts_lock_subject_count(self):
        full = pipeline.full_draft_contract_text({"segments": 5, "total_duration": 50.0,
                                                  "per_segment_duration": 10.0})
        self.assertIn(pipeline.NO_DUPLICATES_CLAUSE, full)
        self.assertIn("[Shot N]", full)
        conversion = pipeline.conversion_contract_text(2, 5, 10.0, "previous end state")
        self.assertIn(pipeline.NO_DUPLICATES_CLAUSE, conversion)
        self.assertIn("verbatim", conversion)
        self.assertIn("previous segment's ending state", conversion)
        self.assertNotIn("previous segment's ending state", pipeline.conversion_contract_text(1, 5, 10.0, ""))

    def test_draft_sections_splits_six_section_draft(self):
        sections = pipeline.draft_sections(
            "subject_definitions: a\nsummary: b\nretention_analysis: c\n"
            "detailed_description: d body\noverall_soundscape: e\nnon_diegetic_music: f")
        self.assertEqual(sections["detailed_description"], "d body")
        self.assertEqual(sections["non_diegetic_music"], "f")

    def test_structured_full_draft_is_rendered_in_canonical_h3_format(self):
        raw = {"status": "ready", "sections": {
            "subject_definitions": "<Subject 1> a traveler",
            "summary": "One traveler crosses the valley. " + pipeline.NO_DUPLICATES_CLAUSE,
            "retention_analysis": "The route opens gradually.",
            "detailed_description": {"style": "Cinematic live action.", "shots": [
                {"start_seconds": 0, "description": "The traveler enters the valley."},
                {"start_seconds": 8.5, "description": "The traveler reaches the bridge."},
            ]},
            "overall_soundscape": "Wind crosses the grass.",
            "non_diegetic_music": "A restrained orchestral theme.",
        }}
        draft, issues = pipeline._compile_structured_draft(raw, 10)
        self.assertEqual(issues, [])
        self.assertEqual(list(pipeline.draft_sections(draft)), list(pipeline.SECTION_LABELS))
        self.assertIn("[Shot 1] The traveler enters", draft)
        self.assertIn("[Shot 2] At 00:08.500,", draft)
        self.assertEqual(pipeline._shot_timestamp(59.9996), "01:00.000")

    def test_full_draft_stage_retries_without_restarting_prior_stages(self):
        session = {"generation": {"mode": "reference", "duration_seconds": 10}, "user_requests": ["A journey"]}
        progress = []
        bad = json.dumps({"status": "ready", "optimized_prompt": "invalid free text"})
        good = {"status": "ready", "sections": {
            "subject_definitions": "<Subject 1> a traveler",
            "summary": "A traveler reaches a bridge. " + pipeline.NO_DUPLICATES_CLAUSE,
            "retention_analysis": "The route resolves.",
            "detailed_description": {"style": "Cinematic.", "shots": [
                {"start_seconds": 0, "description": "The traveler enters the valley."},
                {"start_seconds": 8, "description": "The traveler reaches the bridge."}]},
            "overall_soundscape": "Wind rises.", "non_diegetic_music": "Quiet strings."}}
        replies = iter(['{"selected_skills":[]}', bad, bad, bad, json.dumps(good),
                        '{"optimized_prompt_zh":"旅人抵达桥边。"}'])
        result = pipeline.run_segmented_production(
            session, {}, lambda *args: progress.append(args), lambda *_: next(replies))
        self.assertEqual(result["status"], "ready")
        self.assertGreaterEqual(sum(1 for item in progress if item[:2] == ("full_draft", "running")), 2)

    def test_duration_coverage_rejects_single_clip_scoping(self):
        # The v4 regression: a 50s production whose draft stopped at the 10s opening.
        short = "[Shot 1] At 00:00.000, A charges. [Shot 2] At 00:03.500, B strikes. [Shot 3] At 00:06.500, dodge."
        issues = pipeline.duration_coverage_issues(short, 50.0)
        self.assertTrue(any("begins at" in item for item in issues))
        full = "[Shot 1] At 00:00.000, A charges. [Shot 9] At 00:42.000, freeze silhouette."
        self.assertEqual(pipeline.duration_coverage_issues(full, 50.0), [])

    def test_production_structure_note_is_binding_for_requirements(self):
        note = pipeline.production_structure_note(
            {"segments": 5, "total_duration": 50.0, "per_segment_duration": 10.0})
        self.assertIn("binding", note)
        self.assertIn("50", note)
        self.assertIn("do NOT scope", note)

    def test_skill_files_exist_for_framework_loader(self):
        skills = PLUGIN / "collaboration" / "skills"
        for path in ("system.md",
                     "models/minimax-h3-action/model.md",
                     "models/minimax-h3-action/modes/reference.md",
                     "models/minimax-h3-action/modes/ref2va.md",
                     "models/minimax-h3-action/upstream/h3-prompt-writing/SKILL.md",
                     "models/minimax-h3-action/upstream/h3-prompt-writing/references/ref-en.txt",
                     "pipeline/requirements.md",
                     "pipeline/h3-full-draft.md",
                     "pipeline/segment-splitting.md",
                     "pipeline/h3-director-compiler.md",
                     "pipeline/h3-conformance-review.md",
                     "pipeline/h3-chinese-translation.md",
                     "pipeline/combat-exchange.md",
                     "pipeline/extensions/martial-arts-combat.md"):
            self.assertTrue((skills / path).is_file(), f"missing skill file {path}")
            self.assertTrue((skills / path).read_text(encoding="utf-8").strip())

    def test_director_prompts_assemble_from_copied_skills(self):
        prompts = load_package_module("prompts", PLUGIN / "collaboration" / "prompts.py")
        compiler_prompt = prompts.h3_director_prompt("reference", {"capabilities": ["combat_continuity"]})
        for marker in ("subject_definitions", "Selected Directing Capabilities"):
            self.assertIn(marker, compiler_prompt)
        self.assertIn("segment_cuts", prompts.segment_splitting_prompt())
        full_draft = prompts.h3_full_draft_prompt("reference", {"capabilities": ["combat_continuity"]})
        self.assertIn("total_duration", full_draft)


if __name__ == "__main__":
    unittest.main()
