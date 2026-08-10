from __future__ import annotations

import unittest

from ue_editor_tools.blueprint_reachability import (
    project_blueprint_nodes,
    semantic_node_references,
)


def pin(
    name: str,
    direction: str,
    kind: str,
    connections: list[tuple[str, str]],
) -> dict:
    return {
        "name": name,
        "direction": direction,
        "type_display": kind,
        "connections": [
            {"node": node, "pin": target_pin, "direction": ""}
            for node, target_pin in connections
        ],
    }


class BlueprintReachabilityTests(unittest.TestCase):
    def test_semantic_references_drop_graph_internals_and_node_classes(self) -> None:
        references = semantic_node_references(
            [
                {
                    "object_path": "/Game/BP.BP:EventGraph.Call",
                    "class_path": "/Script/BlueprintGraph.K2Node_CallFunction",
                    "pins": [
                        {
                            "value": "/Game/Data/DA_Value.DA_Value",
                            "connections": [{"node": "/Game/BP.BP:EventGraph.Source"}],
                        }
                    ],
                }
            ]
        )
        self.assertEqual(
            {(item["kind"], item["target"]) for item in references},
            {("asset", "/Game/Data/DA_Value.DA_Value")},
        )

    def test_projects_connected_semantic_nodes_and_drops_structural_or_unused_nodes(
        self,
    ) -> None:
        event = "/Game/BP.BP:EventGraph.Event"
        call = "/Game/BP.BP:EventGraph.Call"
        getter = "/Game/BP.BP:EventGraph.Getter"
        unused = "/Game/BP.BP:EventGraph.Unused"
        nodes = [
            {
                "object_path": event,
                "class": "/Script/BlueprintGraph.K2Node_Event",
                "title": "Begin Play",
                "pins": [pin("then", "output", "exec", [(call, "execute")])],
            },
            {
                "object_path": call,
                "class": "/Script/BlueprintGraph.K2Node_CallFunction",
                "title": "Do Project Work",
                "pins": [
                    pin("execute", "input", "exec", [(event, "then")]),
                    pin("value", "input", "int", [(getter, "value")]),
                ],
            },
            {
                "object_path": getter,
                "class": "/Script/BlueprintGraph.K2Node_VariableGet",
                "title": "Get Project Value",
                "pins": [pin("value", "output", "int", [(call, "value")])],
            },
            {
                "object_path": unused,
                "class": "/Script/BlueprintGraph.K2Node_VariableGet",
                "title": "Unused Default",
                "pins": [pin("value", "output", "int", [])],
            },
        ]

        projection = project_blueprint_nodes(nodes)
        self.assertEqual(
            {item["object_path"] for item in projection["semantic_nodes"]},
            {call, getter},
        )
        self.assertEqual(set(projection["reachable_paths"]), {event, call, getter})


if __name__ == "__main__":
    unittest.main()
