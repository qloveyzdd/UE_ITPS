from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from ue_itps_information_pool.graph_model import Graph
from ue_itps_information_pool.identity import project_id
from ue_itps_information_pool.knowledge_adapter import (
    bridge_gameplay_message_dispatches,
    merge_knowledge_graph,
)


class KnowledgeAdapterTests(unittest.TestCase):
    def test_gameplay_message_bridge_ignores_unshared_and_unresolved_channels(
        self,
    ) -> None:
        key = "Sample|Sample.uproject"
        graph = Graph(key, project_id(key))
        document = {
            "schema_version": "ue_build_knowledge_graph",
            "validation": {"status": "ok"},
            "graph": {
                "counts": {"nodes": 4, "relations": 3, "evidence": 0},
                "nodes": [
                    {
                        "node_id": "orphan-subscriber",
                        "kind": "blueprint_node",
                        "name": "Orphan Subscriber",
                    },
                    {
                        "node_id": "orphan-tag",
                        "kind": "gameplay_tag",
                        "name": "Game.Orphan",
                    },
                    {
                        "node_id": "dynamic-publisher",
                        "kind": "blueprint_node",
                        "name": "Dynamic Publisher",
                    },
                    {
                        "node_id": "dynamic-channel",
                        "kind": "message_channel_expression",
                        "name": "Dynamic Channel",
                    },
                ],
                "relations": [
                    {
                        "relation_id": "orphan-subscription",
                        "source_id": "orphan-subscriber",
                        "kind": "SUBSCRIBES_EVENT",
                        "target_id": "orphan-tag",
                        "certainty": "confirmed",
                    },
                    {
                        "relation_id": "dynamic-publish",
                        "source_id": "dynamic-publisher",
                        "kind": "PUBLISHES_EVENT",
                        "target_id": "dynamic-channel",
                        "certainty": "unresolved",
                    },
                    {
                        "relation_id": "dynamic-subscribe",
                        "source_id": "orphan-subscriber",
                        "kind": "SUBSCRIBES_EVENT",
                        "target_id": "dynamic-channel",
                        "certainty": "unresolved",
                    },
                ],
                "evidence": [],
            },
        }

        with tempfile.TemporaryDirectory() as temporary:
            merge_knowledge_graph(graph, document, Path(temporary) / "graph.json")

        self.assertEqual(bridge_gameplay_message_dispatches(graph), 0)
        self.assertNotIn(
            "DISPATCHES_TO",
            {relation["kind"] for relation in graph.relations.values()},
        )

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
        relation = next(iter(graph.relations.values()))
        self.assertEqual(relation["certainty"], "observed")
        self.assertEqual(relation["resolution_status"], "resolved")
        self.assertEqual(relation["confidence"], 1.0)

    def test_maps_unresolved_logical_relations_to_information_pool_semantics(
        self,
    ) -> None:
        key = "Sample|Sample.uproject"
        graph = Graph(key, project_id(key))
        document = {
            "schema_version": "ue_build_knowledge_graph",
            "validation": {"status": "ok"},
            "graph": {
                "counts": {"nodes": 2, "relations": 1, "evidence": 0},
                "nodes": [
                    {"node_id": "a", "kind": "cxx_function", "name": "A"},
                    {
                        "node_id": "b",
                        "kind": "message_channel_expression",
                        "name": "Dynamic",
                    },
                ],
                "relations": [
                    {
                        "relation_id": "r",
                        "source_id": "a",
                        "kind": "PUBLISHES_EVENT",
                        "target_id": "b",
                        "certainty": "unresolved",
                    }
                ],
                "evidence": [],
            },
        }

        with tempfile.TemporaryDirectory() as temporary:
            merge_knowledge_graph(graph, document, Path(temporary) / "graph.json")

        relation = next(iter(graph.relations.values()))
        self.assertEqual(relation["certainty"], "inferred")
        self.assertEqual(relation["resolution_status"], "unresolved")
        self.assertEqual(relation["confidence"], 0.5)

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
