import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.modules.settings.plugins import PluginSettings, validate_settings_schema


class StubPluginSettings(PluginSettings):
    def _plugins(self):
        return [{
            "id": "cloud-image", "name": "Cloud Image",
            "_plugin_folder": "cloud-image",
            "settings": {"title": "Cloud Image", "fields": [
                {"key": "CLOUD_KEY", "label": "API Key", "type": "secret", "required": True,
                 "prefix": "sk-", "runtime_key": "api_key"},
                {"key": "CLOUD_URL", "label": "API URL", "type": "url",
                 "default": "https://example.test", "runtime_key": "base_url"},
            ]},
            "capabilities": {"image.cloud.create": {}},
        }]


class PluginSettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / "cloud-image").mkdir()
        self.service = StubPluginSettings(SimpleNamespace(paths=SimpleNamespace(plugins=root)))

    def test_plugin_env_is_atomic_masked_and_runtime_mapped(self):
        saved = self.service.save("cloud-image", {
            "CLOUD_KEY": "sk-private", "CLOUD_URL": "https://cloud.example/v1",
        })
        self.assertEqual(saved["CLOUD_KEY"], "********")
        self.assertEqual(self.service.runtime("cloud-image"), {
            "api_key": "sk-private", "base_url": "https://cloud.example/v1",
        })
        content = (self.service.context.paths.plugins / "cloud-image" / ".env").read_text(encoding="utf-8")
        self.assertIn('CLOUD_KEY="sk-private"', content)
        self.assertNotIn("********", content)

    def test_invalid_schema_and_values_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_settings_schema({"fields": [{"key": "bad", "label": "Bad"}]})
        with self.assertRaises(ValueError):
            self.service.save("cloud-image", {"CLOUD_KEY": "wrong"})
        with self.assertRaises(ValueError):
            self.service.save("cloud-image", {"UNKNOWN": "value"})


if __name__ == "__main__":
    unittest.main()
