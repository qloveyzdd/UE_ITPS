from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ue_editor_tools.config_graph import scan_config_graph
from ue_editor_tools.graph_summary import summarize_graph
from ue_editor_tools.knowledge_graph import build_knowledge_graph, validate_graph


class OfflineEditorToolTests(unittest.TestCase):
    def test_knowledge_graph_summary_is_deterministic_and_keeps_evidence(self) -> None:
        nodes = [
            {
                "node_id": "n-death",
                "kind": "cxx_function",
                "name": "HandleOutOfHealth",
                "canonical_key": "Sample|cxx_function|ULyraHealthComponent::HandleOutOfHealth",
                "properties": {"qualified_name": "ULyraHealthComponent::HandleOutOfHealth"},
            },
            {
                "node_id": "n-message",
                "kind": "message_channel_expression",
                "name": "Lyra.Elimination.Message",
                "canonical_key": "Sample|message|Lyra.Elimination.Message",
                "properties": {"tag": "Lyra.Elimination.Message"},
            },
            {
                "node_id": "n-engine",
                "kind": "asset",
                "name": "SK_Mannequin",
                "canonical_key": "Sample|asset|/Engine/Characters/Mannequins/SK_Mannequin",
                "properties": {"package": "/Engine/Characters/Mannequins/SK_Mannequin"},
            },
        ]
        relations = [
            {
                "relation_id": "r-publish",
                "source_id": "n-death",
                "kind": "PUBLISHES_EVENT",
                "target_id": "n-message",
                "certainty": "confirmed",
                "properties": {},
            },
            {
                "relation_id": "r-dependency",
                "source_id": "n-death",
                "kind": "DEPENDS_ON",
                "target_id": "n-engine",
                "certainty": "confirmed",
                "properties": {},
            },
        ]
        document = {
            "schema_version": "ue_build_knowledge_graph",
            "graph": {
                "project": "D:/Sample/Sample.uproject",
                "nodes": nodes,
                "relations": relations,
                "evidence": [
                    {"evidence_id": "e-publish-1", "relation_id": "r-publish", "producer": "cpp.json"},
                    {"evidence_id": "e-publish-2", "relation_id": "r-publish", "producer": "message.json"},
                    {"evidence_id": "e-dependency", "relation_id": "r-dependency", "producer": "asset.json"},
                ],
                "counts": {"nodes": 3, "relations": 2, "evidence": 3},
            },
        }
        first = summarize_graph(document, view="all", max_nodes=20, max_relations=20)
        second = summarize_graph(document, view="all", max_nodes=20, max_relations=20)
        self.assertEqual(first, second)
        overview_relation = next(
            item for item in first["overview"]["featured_relations"] if item["relation_id"] == "r-publish"
        )
        self.assertEqual(overview_relation["evidence_ids"], ["e-publish-1", "e-publish-2"])
        self.assertIn("DEPENDS_ON", first["overview"]["coverage"]["folded_relation_counts"])
        self.assertIn("n-death", first["slices"]["death"]["node_ids"])

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
                                        "resolution": "exact",
                                        "source": "native_member_reference",
                                        "member_reference": {
                                            "member_parent_path": "/Script/Sample.SampleCharacter",
                                            "field_path": "/Script/Sample.SampleCharacter:ApplyDamage",
                                            "resolution": "exact",
                                        },
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
                                {
                                    "object_path": "/Game/BP_Sample.BP_Sample_C:EventGraph.Heal",
                                    "class": "K2Node_CallFunction",
                                    "type_id": "CallFunction",
                                    "title": "Heal",
                                    "symbol": {
                                        "symbol_kind": "function",
                                        "symbol_name": "Heal",
                                        "symbol_path": "Heal",
                                        "symbol_id": "ue_symbol:name-only",
                                        "resolution": "name_only",
                                        "source": "node_type_id_or_title",
                                    },
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
                },
                {
                    "qualified_name": "SampleCharacter::Heal",
                    "name": "Heal",
                    "kind": "method",
                    "evidence": {"unit": "header", "line": 13},
                },
            ],
        }
        graph, problems = build_knowledge_graph(
            [("blueprint.json", blueprint_document), ("cxx.json", cxx_document)]
        )
        self.assertEqual(problems, [])
        kinds = {item["kind"] for item in graph["relations"]}
        self.assertIn("CALLS", kinds)
        self.assertIn("MAPS_TO", kinds)
        self.assertIn("CANDIDATE_MATCH", kinds)
        self.assertIn("DATA_OR_EXEC_LINK", kinds)
        symbol = next(
            item
            for item in graph["nodes"]
            if item.get("properties", {}).get("symbol_id") == "ue_symbol:test"
        )
        self.assertEqual(
            symbol["properties"]["member_reference"]["field_path"],
            "/Script/Sample.SampleCharacter:ApplyDamage",
        )
        self.assertEqual(validate_graph(graph), [])

    def test_knowledge_graph_imports_project_cxx_dependencies(self) -> None:
        document = {
            "schema_version": "ue_analyze_cxx_dependencies",
            "project_root": "D:/Sample",
            "graph": {
                "nodes": [
                    {"name": "SampleActor", "kind": "class", "files": ["Source/SampleActor.h"], "base_types": ["AActor"], "incoming_count": 0, "outgoing_count": 1},
                    {"name": "SampleState", "kind": "struct", "files": ["Source/SampleState.h"], "base_types": [], "incoming_count": 1, "outgoing_count": 0},
                ],
                "edges": [
                    {"source": "SampleActor", "target": "SampleState", "kind": "field", "member": "State", "evidence": {"path": "Source/SampleActor.h", "line": 8}},
                ],
                "cycles": [],
            },
            "validation": {"status": "ok", "problem_count": 0, "problems": []},
            "limits": {"responsibility": "test", "boundaries": ["test"]},
        }
        graph, problems = build_knowledge_graph([("cxx-dependencies.json", document)])
        self.assertEqual(problems, [])
        self.assertIn("USES_TYPE", {item["kind"] for item in graph["relations"]})
        self.assertIn("cxx_class", {item["kind"] for item in graph["nodes"]})
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
