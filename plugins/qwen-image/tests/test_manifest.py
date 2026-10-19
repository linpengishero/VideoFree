import json
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[1]


class QwenImageManifestTests(unittest.TestCase):
    def test_removed_unstable_capabilities_are_not_registered(self):
        manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
        removed = {"image.qwen.scene", "image.qwen.storyboard_6"}

        self.assertTrue(removed.isdisjoint(manifest["capabilities"]))
        functions = {
            item["capability_id"]
            for model in manifest["ui_models"]
            for item in model["functions"]
        }
        self.assertTrue(removed.isdisjoint(functions))


if __name__ == "__main__":
    unittest.main()
