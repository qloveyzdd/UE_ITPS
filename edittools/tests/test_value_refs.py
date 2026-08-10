from __future__ import annotations

import unittest

from ue_editor_tools.value_refs import unique_references


class ValueReferenceTests(unittest.TestCase):
    def test_extracts_asset_class_and_tag_references(self) -> None:
        value = {
            "Asset": "Texture2D'/Game/UI/T_Icon.T_Icon'",
            "Class": "/Script/LyraGame.LyraGameMode",
            "Tag": '(TagName="Gameplay.Message.Test")',
        }
        found = {(item["kind"], item["target"]) for item in unique_references(value)}
        self.assertIn(("class", "/Script/LyraGame.LyraGameMode"), found)
        self.assertIn(("asset", "/Game/UI/T_Icon.T_Icon"), found)
        self.assertIn(("gameplay_tag", "Gameplay.Message.Test"), found)


if __name__ == "__main__":
    unittest.main()
