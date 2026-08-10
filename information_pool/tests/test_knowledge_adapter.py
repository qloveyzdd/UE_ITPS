from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ue_itps_information_pool.graph_model import Graph
from ue_itps_information_pool.identity import project_id
from ue_itps_information_pool.knowledge_adapter import merge_knowledge_graph


class KnowledgeAdapterTests(unittest.TestCase):
    def test_merges_logical_nodes_relations_and_editor_evidence(self) -> None:
        key = "Sample|Sample.uproject"
        graph = Graph(key, project_id(key))
        document = {
            "schema_version": "ue_build_knowledge_graph",
            "validation": {"status": "ok"},
            "graph": {
                "counts": {"nodes": 2, "relations": 1, "evidence": 1},
                "nodes": [
                    {
                        "node_id": "a",
                        "kind": "asset",
                        "name": "A",
                        "canonical_key": "D:/Sample|asset|/Game/A",
                        "properties": {"package": "/Game/A"},
                    },
                    {
                        "node_id": "b",
                        "kind": "gameplay_tag",
                        "name": "Game.Test",
                        "canonical_key": "D:/Sample|gameplay_tag|Game.Test",
                        "properties": {"tag": "Game.Test"},
                    },
                ],
                "relations": [
                    {
                        "relation_id": "r",
                        "source_id": "a",
                        "kind": "REFERENCES",
                        "target_id": "b",
                        "certainty": "confirmed",
                        "properties": {},
                    }
                ],
                "evidence": [
                    {"evidence_id": "e", "relation_id": "r", "asset": "/Game/A"}
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            result = merge_knowledge_graph(
                graph, document, Path(temporary) / "graph.json"
            )
        self.assertEqual(len(graph.nodes), 2)
        self.assertEqual(len(graph.relations), 1)
        self.assertEqual(len(graph.evidence), 1)
        self.assertEqual(result["probe_kind"], "knowledge_graph")

    def test_persists_data_asset_property_values_and_editor_evidence(self) -> None:
        key = "Sample|Sample.uproject"
        graph = Graph(key, project_id(key))
        value = {"kind": "object", "path": "/Game/Pawns/PawnData.PawnData"}
        document = {
            "schema_version": "ue_build_knowledge_graph",
            "validation": {"status": "ok"},
            "graph": {
                "counts": {"nodes": 2, "relations": 1, "evidence": 1},
                "nodes": [
                    {
                        "node_id": "asset",
                        "kind": "asset",
                        "name": "Experience",
                        "canonical_key": "D:/Sample|asset|/Game/Experience",
                        "properties": {"package": "/Game/Experience"},
                    },
                    {
                        "node_id": "property",
                        "kind": "data_asset_property",
                        "name": "default_pawn_data",
                        "canonical_key": "D:/Sample|data_asset_property|/Game/Experience|default_pawn_data",
                        "properties": {
                            "path": "default_pawn_data",
                            "value": value,
                        },
                    },
                ],
                "relations": [
                    {
                        "relation_id": "declares",
                        "source_id": "asset",
                        "kind": "DECLARES_PROPERTY",
                        "target_id": "property",
                        "certainty": "confirmed",
                        "properties": {},
                    }
                ],
                "evidence": [
                    {
                        "evidence_id": "evidence",
                        "relation_id": "declares",
                        "asset": "/Game/Experience.Experience",
                        "property": "default_pawn_data",
                    }
                ],
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            merge_knowledge_graph(graph, document, Path(temporary) / "graph.json")
        property_node = next(
            item
            for item in graph.nodes.values()
            if item["kind"] == "data_asset_property"
        )
        self.assertEqual(json.loads(property_node["properties_json"])["value"], value)
        evidence = next(iter(graph.evidence.values()))
        self.assertEqual(evidence["root"], "editor")
        self.assertEqual(evidence["path"], "/Game/Experience.Experience")
        self.assertEqual(
            json.loads(evidence["detail_json"])["evidence"]["property"],
            "default_pawn_data",
        )


if __name__ == "__main__":
    unittest.main()
