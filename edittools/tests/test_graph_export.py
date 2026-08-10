from __future__ import annotations

import unittest

from ue_editor_tools.graph_export import export_message_graph


class GraphExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scan = {
            "editor": {"project": "D:/Game/Game.uproject"},
            "operations": [
                {
                    "asset": "/Game/BP_Consumer",
                    "graph": "EventGraph",
                    "graph_path": "/Game/BP_Consumer.BP_Consumer:EventGraph",
                    "node": "/Game/BP_Consumer.BP_Consumer:EventGraph.Listen_0",
                    "node_class": "K2Node_AsyncAction_ListenForGameplayMessages",
                    "node_type": "Messaging|ListenForGameplayMessages",
                    "operation": "subscribe",
                    "channel": {
                        "status": "static",
                        "tag": "Game.Message",
                        "connections": [],
                    },
                    "payload_type": "/Script/Game.Payload",
                    "match_type": "ExactMatch",
                }
            ],
            "tag_referencers": [
                {
                    "tag": "Game.Message",
                    "referencers": ["/Game/BP_Consumer", "/Game/DA_Config"],
                }
            ],
        }

    def test_export_contains_shared_tag_and_semantic_edges(self) -> None:
        graph = export_message_graph(self.scan)
        kinds = {item["kind"] for item in graph["nodes"]}
        relation_kinds = {item["kind"] for item in graph["relations"]}
        self.assertIn("gameplay_tag", kinds)
        self.assertIn("blueprint_node", kinds)
        self.assertIn("SUBSCRIBES_EVENT", relation_kinds)
        self.assertIn("REFERENCES", relation_kinds)
        self.assertIn("USES_TYPE", relation_kinds)

    def test_export_is_deterministic(self) -> None:
        self.assertEqual(
            export_message_graph(self.scan), export_message_graph(self.scan)
        )


if __name__ == "__main__":
    unittest.main()
