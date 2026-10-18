from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock

from backend.modules.settings.service import SettingsService


class SettingsOutputDirectoryTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
