from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock

from backend.modules.settings.service import SettingsService


class SettingsOutputDirectoryTests(unittest.TestCase):
    def test_locale_is_persistent_and_does_not_probe_or_mutate_other_settings(self):
        stored = {"ai_model": "keep-model"}
        self.context.config = SimpleNamespace(api_token="")
        self.context.db = Mock()
        self.context.db.settings.side_effect = lambda: dict(stored)
        self.context.db.save_settings.side_effect = lambda values: stored.update(values)
        self.assertEqual(self.service.read()["locale"], "zh-CN")
        self.assertEqual(self.service.apply({"locale": "en-US"})["locale"], "en-US")
        self.assertEqual(SettingsService(self.context, self.comfyui).read()["locale"], "en-US")
        self.assertEqual(stored, {"ai_model": "keep-model", "locale": "en-US"})
        self.comfyui.request.assert_not_called()
        for value in ("fr-FR", None, ""):
            with self.assertRaises(ValueError):
                self.service.apply({"locale": value})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        data = Path(self.temp.name)
        self.context = SimpleNamespace(
            paths=SimpleNamespace(data=data, legacy_settings=data / "settings.json"),
            comfyui_url="http://127.0.0.1:8189",
            comfyui_output_dir=data / "comfyui_output",
        )
        self.comfyui = Mock()
        self.service = SettingsService(self.context, self.comfyui)

    def test_startup_directory_resolution_does_not_probe_comfyui(self):
        result = self.service.effective_output_directory(
            {"comfyui_output_dir": str(self.context.comfyui_output_dir)},
            detect_comfyui=False,
        )
        self.assertEqual(result, self.context.comfyui_output_dir.resolve())
        self.comfyui.request.assert_not_called()

    def test_offline_comfyui_does_not_break_live_directory_detection(self):
        self.comfyui.request.side_effect = RuntimeError("connection refused")
        result = self.service.local_comfyui_output_directory(
            {"comfyui_url": "http://127.0.0.1:8189"}
        )
        self.assertIsNone(result)

    def test_relative_entry_resolves_against_comfyui_not_gateway(self):
        root = self.context.paths.data / 'ComfyUI'
        (root / 'output').mkdir(parents=True)
        (root / 'main.py').write_text('', encoding='utf-8')
        self.comfyui.request.side_effect = [
            {'system': {'argv': ['main.py']}}, {'custom_nodes': [str(root / 'custom_nodes')]}]
        self.assertEqual(self.service.local_comfyui_output_directory({}), root / 'output')

    def test_relative_entry_without_reliable_root_does_not_guess(self):
        self.comfyui.request.side_effect = [{'system': {'argv': ['main.py']}}, {}]
        self.assertIsNone(self.service.local_comfyui_output_directory({}))

    def test_unavailable_llm_provider_is_preserved_and_not_reported_configured(self):
        self.context.db = Mock()
        self.context.db.settings.return_value = {
            "ai_provider": "temporarily-missing", "ai_base_url": "https://llm.example/v1",
            "ai_model": "model", "ai_api_key": "secret",
        }
        self.context.config = SimpleNamespace(api_token="")
        self.context.system_services = Mock()
        self.context.system_services.contains.side_effect = lambda value: value == "custom"
        self.context.paths.legacy_settings = self.context.paths.data / "missing-settings.json"
        result = self.service.read()
        self.assertEqual(result["ai_provider"], "temporarily-missing")
        self.assertFalse(self.service.ai_is_configured(result))

    def test_unavailable_llm_provider_can_be_retained_but_not_replaced_with_unknown_id(self):
        self.context.db = Mock()
        self.context.db.settings.return_value = {"ai_provider": "temporarily-missing"}
        self.context.config = SimpleNamespace(api_token="")
        self.context.system_services = Mock()
        self.context.system_services.contains.side_effect = lambda value: value == "custom"
        self.context.paths.legacy_settings = self.context.paths.data / "missing-settings.json"
        self.context.comfyui_output_locations = {}
        self.context.library_cache = {}

        self.service.apply({"ai_provider": "temporarily-missing"})

        with self.assertRaisesRegex(ValueError, "未注册或不可用"):
            self.service.apply({"ai_provider": "unknown"})


if __name__ == "__main__":
    unittest.main()
