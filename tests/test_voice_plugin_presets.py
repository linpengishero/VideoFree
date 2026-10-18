from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from backend.modules.presets.voices import VoicePresets, voice_presets
from backend.persistence.database import Database


ROOT = Path(__file__).resolve().parents[1]


class VoicePluginPresetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.db = Database(root / "test.db")
        self.db.initialize({"my_voice": {"display_name": "Personal", "instruction": "old"},
                            "warm_male": {"display_name": "Old edited name", "instruction": "old"}})
        self.context = SimpleNamespace(db=self.db, paths=SimpleNamespace(
            plugins=ROOT / "plugins"))
        self.service = VoicePresets(self.context)

    def test_definitions_come_from_plugin_not_database(self):
        definitions = voice_presets(ROOT / "plugins")
        self.assertNotIn("my_voice", definitions)
        self.assertIsNone(self.service.get("my_voice"))
        preset = self.service.get("warm_male")
        self.assertEqual(preset["plugin_id"], "cosyvoice3")
        self.assertNotEqual(preset["display_name"], "Old edited name")
        self.assertEqual(self.service.sample_path(preset), ROOT / "plugins/cosyvoice3/samples/warm_male.mp3")

    def test_all_bundled_samples_live_inside_owner_plugin(self):
        items = self.service.items()
        self.assertEqual(len(items), 18)
        for item in items:
            sample = self.service.sample_path(item)
            self.assertTrue(sample.is_relative_to(ROOT / 'plugins' / item['plugin_folder']))
            self.assertGreater(sample.stat().st_size, 1000)

    def test_generic_plugin_discovery_includes_voices_and_options(self):
        from backend.modules.presets.plugins import plugin_presets
        result = plugin_presets(self.context, 'cosyvoice3')
        self.assertEqual(len(result['voices']), 18)
        result = plugin_presets(self.context, 'krea2')
        self.assertTrue(result['fields'])
        with self.assertRaises(ValueError):
            plugin_presets(self.context, 'not-installed')


if __name__ == "__main__":
    unittest.main()
