import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "qwen-image"


class QwenCharacterContractTests(unittest.TestCase):
    def test_character_capability_is_a_simple_three_view_sheet(self):
        manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
        capability = manifest["capabilities"]["image.qwen.character"]
        instruction = capability["task_instruction"]

        self.assertEqual(capability["name"], "Qwen 角色设定图")
        for required in ("半身主视图", "正面", "右侧严格90度侧面", "背面"):
            self.assertIn(required, instruction)
        for removed in ("六个头部", "四个关键细节", "两个剪影", "四色配色"):
            self.assertNotIn(removed, instruction)

    def test_director_skill_uses_the_same_three_view_contract(self):
        skill = (
            PLUGIN / "collaboration" / "skills" / "models" / "qwen" / "modes" / "character.md"
        ).read_text(encoding="utf-8")

        self.assertIn("large half-body hero view", skill)
        self.assertIn("exactly three", skill)
        self.assertIn("strict 90-degree right profile", skill)
        self.assertIn("back view", skill)
        self.assertNotIn("four-view", skill)


if __name__ == "__main__":
    unittest.main()
