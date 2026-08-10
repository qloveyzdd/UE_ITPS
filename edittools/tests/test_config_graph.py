from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ue_editor_tools.config_graph import scan_config_graph


class ConfigGraphTests(unittest.TestCase):
    def test_reads_operations_references_and_observed_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Sample.uproject").write_text(
                json.dumps({"FileVersion": 3}), encoding="utf-8"
            )
            config = root / "Config" / "DefaultGame.ini"
            config.parent.mkdir()
            config.write_text(
                "[/Script/Engine.AssetManagerSettings]\n"
                "+Paths=/Game/One\n+Paths=/Game/Two\n-Paths=/Game/One\n"
                "GameMode=/Script/Game.SampleMode\nGameplayTag=Game.Message.Test\n"
                '+PrimaryAssetTypesToScan=(PrimaryAssetType="Experience",AssetBaseClass="/Script/Game.Experience",bHasBlueprintClasses=True,bIsEditorOnly=False,Directories=((Path="/Game/Experiences")),SpecificAssets=("/Game/Default.Default"),Rules=(Priority=1,ChunkId=2,bApplyRecursively=True,CookRule=AlwaysCook))\n',
                encoding="utf-8",
            )
            result = scan_config_graph(root / "Sample.uproject")
        self.assertEqual(result["declaration_count"], 6)
        references = {
            (item["kind"], item["target"])
            for declaration in result["declarations"]
            for item in declaration["references"]
        }
        self.assertIn(("class", "/Script/Game.SampleMode"), references)
        self.assertIn(("gameplay_tag", "Game.Message.Test"), references)
        values = {
            (item["section"], item["key"]): item["values"]
            for item in result["observed_values"]
        }
        self.assertEqual(
            values[("/Script/Engine.AssetManagerSettings", "Paths")],
            ["/Game/Two"],
        )
        primary = result["primary_asset_types"][0]
        self.assertEqual(primary["primary_asset_type"], "Experience")
        self.assertEqual(primary["directories"], ["/Game/Experiences"])
        self.assertEqual(primary["specific_assets"], ["/Game/Default.Default"])
        self.assertEqual(primary["rules"]["CookRule"], "AlwaysCook")


if __name__ == "__main__":
    unittest.main()
