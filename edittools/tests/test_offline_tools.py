from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ue_editor_tools.config_graph import scan_config_graph
from ue_editor_tools.knowledge_graph import build_knowledge_graph, validate_graph


class OfflineEditorToolTests(unittest.TestCase):
    def test_config_scanner_applies_array_operations_and_extracts_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "Sample.uproject"
            project.write_text(json.dumps({"FileVersion": 3}), encoding="utf-8")
            config = root / "Config" / "DefaultGame.ini"
            config.parent.mkdir()
            config.write_text(
                "[/Script/Engine.AssetManagerSettings]\n"
                "+Paths=/Game/One\n+Paths=/Game/Two\n-Paths=/Game/One\n"
                "GameMode=/Script/Sample.SampleMode\n"
                "GameplayTag=Game.Message.Ready\n",
                encoding="utf-8",
            )
            result = scan_config_graph(project)

        observed = {
            (item["section"], item["key"]): item["values"]
            for item in result["observed_values"]
        }
        self.assertEqual(
            observed[("/Script/Engine.AssetManagerSettings", "Paths")],
            ["/Game/Two"],
        )
        references = {
            (reference["kind"], reference["target"])
            for declaration in result["declarations"]
            for reference in declaration["references"]
        }
        self.assertIn(("class", "/Script/Sample.SampleMode"), references)
        self.assertIn(("gameplay_tag", "Game.Message.Ready"), references)

    def test_knowledge_graph_merges_asset_and_message_evidence(self) -> None:
        project = "D:/Sample/Sample.uproject"
        asset_document = {
            "schema_version": "ue_editor_export_asset_graph",
            "editor": {"project": project},
            "packages": [
                {
                    "package": "/Game/BP_Sample",
                    "root": "/Game",
                    "assets": [
                        {
                            "object_path": "/Game/BP_Sample.BP_Sample",
                            "class": "/Script/Engine.Blueprint",
                            "registry_tags": {},
                        }
                    ],
                    "dependencies": {},
                }
            ],
        }
        message_document = {
            "schema_version": "ue_editor_scan_gameplay_messages",
            "editor": {"project": project},
            "operations": [
                {
                    "asset": "/Game/BP_Sample",
                    "graph": "EventGraph",
                    "graph_path": "/Game/BP_Sample.BP_Sample:EventGraph",
                    "node": "/Game/BP_Sample.BP_Sample:EventGraph.Publish",
                    "node_class": "K2Node_CallFunction",
                    "node_type": "BroadcastMessage",
                    "operation": "publish",
                    "channel": {"status": "static", "tag": "Game.Message.Ready", "connections": []},
                    "payload_type": "/Script/Sample.Payload",
                    "match_type": None,
                }
            ],
            "tag_referencers": [],
        }
        graph, problems = build_knowledge_graph(
            [("assets.json", asset_document), ("messages.json", message_document)]
        )
        self.assertEqual(problems, [])
        self.assertEqual(validate_graph(graph), [])
        self.assertIn("PUBLISHES_EVENT", {item["kind"] for item in graph["relations"]})


if __name__ == "__main__":
    unittest.main()

