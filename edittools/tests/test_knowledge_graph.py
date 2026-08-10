from __future__ import annotations

import copy
import unittest

from ue_editor_tools.knowledge_graph import (
    build_knowledge_graph,
    diff_graphs,
    validate_graph,
)


PROJECT = "D:/Game/Game.uproject"


class KnowledgeGraphTests(unittest.TestCase):
    def test_merges_asset_and_message_evidence_by_canonical_identity(self) -> None:
        asset_document = {
            "schema_version": "ue_editor_export_asset_graph",
            "editor": {"project": PROJECT},
            "packages": [
                {
                    "package": "/Game/BP_Test",
                    "root": "/Game",
                    "assets": [
                        {
                            "object_path": "/Game/BP_Test.BP_Test",
                            "class": "/Script/Engine.Blueprint",
                            "registry_tags": {},
                        }
                    ],
                    "dependencies": {"hard_package": ["/Game/Data/DT_Test"]},
                }
            ],
        }
        message_document = {
            "schema_version": "ue_editor_scan_gameplay_messages",
            "editor": {"project": PROJECT},
            "operations": [
                {
                    "asset": "/Game/BP_Test",
                    "graph": "EventGraph",
                    "graph_path": "/Game/BP_Test.BP_Test:EventGraph",
                    "node": "/Game/BP_Test.BP_Test:EventGraph.Node",
                    "node_class": "K2Node_CallFunction",
                    "node_type": "BroadcastMessage",
                    "operation": "publish",
                    "channel": {
                        "status": "static",
                        "tag": "Game.Message.Test",
                        "connections": [],
                    },
                    "payload_type": "/Script/Game.Payload",
                    "match_type": None,
                }
            ],
            "tag_referencers": [],
        }
        graph, problems = build_knowledge_graph(
            [("assets.json", asset_document), ("messages.json", message_document)]
        )
        self.assertEqual(problems, [])
        assets = [
            item
            for item in graph["nodes"]
            if item["kind"] == "asset"
            and item["properties"].get("package") == "/Game/BP_Test"
        ]
        self.assertEqual(len(assets), 1)
        self.assertIn("PUBLISHES_EVENT", {item["kind"] for item in graph["relations"]})
        self.assertEqual(validate_graph(graph), [])

    def test_diff_uses_canonical_identity(self) -> None:
        document = {
            "schema_version": "ue_scan_config_graph",
            "project": PROJECT,
            "declarations": [],
        }
        previous, _ = build_knowledge_graph([("config.json", document)])
        current = copy.deepcopy(previous)
        current["nodes"].append(
            {
                "node_id": "node:new",
                "kind": "asset",
                "name": "New",
                "canonical_key": f"{PROJECT}|asset|/Game/New",
                "properties": {},
            }
        )
        current["counts"]["nodes"] += 1
        difference = diff_graphs(current, previous)
        self.assertEqual(len(difference["added_nodes"]), 1)

    def test_config_primary_asset_rules_become_logical_relations(self) -> None:
        evidence = {"root": "project", "path": "Config/DefaultGame.ini", "line": 10}
        document = {
            "schema_version": "ue_scan_config_graph",
            "project": PROJECT,
            "declarations": [],
            "primary_asset_types": [
                {
                    "primary_asset_type": "Experience",
                    "operator": "+",
                    "asset_base_class": "/Script/Game.Experience",
                    "has_blueprint_classes": True,
                    "is_editor_only": False,
                    "directories": ["/Game/Experiences"],
                    "specific_assets": ["/Game/Default.Default"],
                    "rules": {"CookRule": "AlwaysCook"},
                    "evidence": evidence,
                }
            ],
        }
        graph, problems = build_knowledge_graph([("config.json", document)])
        self.assertEqual(problems, [])
        relations = {item["kind"] for item in graph["relations"]}
        self.assertTrue({"SCANS_PATH", "MANAGES", "APPLIES_TO"}.issubset(relations))


if __name__ == "__main__":
    unittest.main()
