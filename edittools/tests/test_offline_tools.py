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

    def test_knowledge_graph_links_blueprint_nodes_to_native_symbols(self) -> None:
        project = "D:/Sample/Sample.uproject"
        blueprint_document = {
            "schema_version": "ue_editor_scan_blueprint_structure",
            "editor": {"project": project},
            "blueprints": [
                {
                    "asset": "/Game/BP_Sample",
                    "asset_object_path": "/Game/BP_Sample.BP_Sample",
                    "generated_class": "/Game/BP_Sample.BP_Sample_C",
                    "parent_class": "/Script/Sample.SampleCharacter",
                    "graphs": [
                        {
                            "name": "EventGraph",
                            "object_path": "/Game/BP_Sample.BP_Sample_C:EventGraph",
                            "nodes": [
                                {
                                    "object_path": "/Game/BP_Sample.BP_Sample_C:EventGraph.Call",
                                    "class": "K2Node_CallFunction",
                                    "type_id": "CallFunction",
                                    "title": "ApplyDamage",
                                    "symbol": {
                                        "symbol_kind": "function",
                                        "symbol_path": "/Script/Sample.SampleCharacter:ApplyDamage",
                                        "symbol_id": "ue_symbol:test",
                                    },
                                    "pins": [
                                        {
                                            "name": "Then",
                                            "direction": "output",
                                            "connections": [
                                                {
                                                    "node": "/Game/BP_Sample.BP_Sample_C:EventGraph.Return",
                                                    "pin": "Execute",
                                                }
                                            ],
                                        }
                                    ],
                                },
                                {
                                    "object_path": "/Game/BP_Sample.BP_Sample_C:EventGraph.Return",
                                    "class": "K2Node_Return",
                                    "type_id": "Return",
                                    "title": "Return",
                                    "pins": [],
                                },
                            ],
                        }
                    ],
                    "references": [],
                }
            ],
        }
        cxx_document = {
            "schema_version": "ue_list_cxx_functions",
            "editor": {"project": project},
            "functions": [
                {
                    "qualified_name": "SampleCharacter::ApplyDamage",
                    "name": "ApplyDamage",
                    "kind": "method",
                    "evidence": {"unit": "header", "line": 12},
                }
            ],
        }
        graph, problems = build_knowledge_graph(
            [("blueprint.json", blueprint_document), ("cxx.json", cxx_document)]
        )
        self.assertEqual(problems, [])
        kinds = {item["kind"] for item in graph["relations"]}
        self.assertIn("CALLS", kinds)
        self.assertIn("MAPS_TO", kinds)
        self.assertIn("DATA_OR_EXEC_LINK", kinds)
        self.assertEqual(validate_graph(graph), [])

    def test_knowledge_graph_keeps_level_instance_evidence(self) -> None:
        document = {
            "schema_version": "ue_editor_scan_level_actors",
            "editor": {"project": "D:/Sample/Sample.uproject"},
            "world": {"object_path": "/Game/Maps/Test.Test", "streaming_levels": []},
            "actors": [
                {
                    "object_path": "/Game/Maps/Test.PersistentLevel.BP_Enemy_1",
                    "label": "Enemy_1",
                    "class": "/Game/BP_Enemy.BP_Enemy_C",
                    "components": [
                        {
                            "object_path": "/Game/Maps/Test.PersistentLevel.BP_Enemy_1:Collision",
                            "name": "Collision",
                            "class": "/Script/Engine.CapsuleComponent",
                        }
                    ],
                }
            ],
        }
        graph, problems = build_knowledge_graph([("level.json", document)])
        self.assertEqual(problems, [])
        kinds = {item["kind"] for item in graph["relations"]}
        self.assertIn("CONTAINS", kinds)
        self.assertIn("OWNS_COMPONENT", kinds)
        self.assertIn("INSTANCE_OF", kinds)
        self.assertEqual(validate_graph(graph), [])


if __name__ == "__main__":
    unittest.main()
