from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
