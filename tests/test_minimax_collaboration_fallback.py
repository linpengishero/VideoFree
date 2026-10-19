import importlib.util
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


PACKAGE = "minimax_h3_test_collaboration"
COLLABORATION_DIR = ROOT / "plugins/minimax-h3/collaboration"
package = ModuleType(PACKAGE)
package.__path__ = [str(COLLABORATION_DIR)]
sys.modules[PACKAGE] = package


def load_plugin_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


load_plugin_module(f"{PACKAGE}.prompts", COLLABORATION_DIR / "prompts.py")
analysis = load_plugin_module(f"{PACKAGE}.analysis", COLLABORATION_DIR / "analysis.py")
confirmation = load_plugin_module(f"{PACKAGE}.confirmation", COLLABORATION_DIR / "confirmation.py")
from backend.modules.collaboration import modes as collaboration_modes


class MiniMaxCollaborationFallbackTests(unittest.TestCase):
    def test_missing_reference_offers_one_t2va_choice(self):
        result = {"status": "ready", "questions": []}
        normalized = analysis.normalize_reference_mode_questions(result, "reference", {"ordered_references": []})
        self.assertEqual(normalized["status"], "needs_input")
        self.assertEqual(normalized["questions"][0]["id"], "missing_reference_action")
        self.assertIn("T2VA", normalized["questions"][0]["options"][0])

    def test_explicit_text_choice_only_switches_empty_reference_session(self):
        empty_reference = {"mode": "reference", "ordered_references": []}
        self.assertTrue(analysis.selected_text_fallback("我的选择：切换为纯文字生成（T2VA）", empty_reference))
        self.assertFalse(analysis.selected_text_fallback("切换到纯文字生成", {
            "mode": "reference", "ordered_references": [{"label": "<Picture 1>"}],
        }))
        self.assertFalse(analysis.selected_text_fallback("一个男人大笑", empty_reference))

    def test_confirmation_routes_only_the_explicit_fallback(self):
        source = {"capability_id": "video.reference"}
        self.assertEqual(confirmation.prepare(source, {
            "generation_payload": {"capability_id": "video.text_to_video"},
        }, None), {"capability_id": "video.text_to_video"})
        self.assertEqual(confirmation.prepare(source, {"generation_payload": {}}, None), {})
        self.assertEqual(confirmation.prepare({"capability_id": "video.text_to_video"}, {
            "generation_payload": {"capability_id": "video.text_to_video"},
        }, None), {})

    def test_confirmation_capability_switch_is_limited_to_same_plugin(self):
        with tempfile.TemporaryDirectory() as directory:
            context = Mock()
            context.paths.plugins = Path(directory)
            catalog = Mock()
            catalog.confirmation.return_value = lambda *_: {"capability_id": "video.text_to_video"}
            catalog.scan.return_value = ([{"id": "minimax-h3", "capabilities": {
                "video.text_to_video": {"operation": "generate"},
            }}], [])
            with patch.object(collaboration_modes, "context", context), \
                    patch.object(collaboration_modes, "PluginCatalog", return_value=catalog), \
                    patch.object(collaboration_modes, "PluginSettings"), \
                    patch.object(collaboration_modes, "PluginRuntime"):
                patch_result = collaboration_modes.confirmation_overrides(
                    {"plugin_id": "minimax-h3"}, {}, {},
                )
            self.assertEqual(patch_result["capability_id"], "video.text_to_video")

            catalog.scan.return_value = ([{"id": "another-plugin", "capabilities": {
                "video.text_to_video": {"operation": "generate"},
            }}], [])
            with patch.object(collaboration_modes, "context", context), \
                    patch.object(collaboration_modes, "PluginCatalog", return_value=catalog), \
                    patch.object(collaboration_modes, "PluginSettings"), \
                    patch.object(collaboration_modes, "PluginRuntime"):
                with self.assertRaisesRegex(ValueError, "same plugin"):
                    collaboration_modes.confirmation_overrides(
                        {"plugin_id": "minimax-h3"}, {}, {},
                    )


if __name__ == "__main__":
    unittest.main()
