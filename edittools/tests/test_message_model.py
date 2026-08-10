from __future__ import annotations

import unittest

from ue_editor_tools.message_model import (
    channel_fact,
    classify_message_node,
    message_operation,
)


def pin(
    name: str,
    *,
    value: str = "",
    title: str | None = None,
    connections: list[dict] | None = None,
) -> dict:
    return {
        "name": name,
        "direction": "input",
        "value": value,
        "type_schema": {"title": title} if title else {},
        "connections": connections or [],
    }


class MessageModelTests(unittest.TestCase):
    def test_listener_is_classified_without_title_text(self) -> None:
        node = {
            "class": "K2Node_AsyncAction_ListenForGameplayMessages",
            "type_id": "localized-title-is-irrelevant",
            "pins": [
                pin("Channel", value='(TagName="Game.Message")'),
                pin("PayloadType", value="/Script/Game.Payload"),
                pin("MatchType", value="ExactMatch"),
            ],
        }
        self.assertEqual(classify_message_node(node), "subscribe")

    def test_publisher_requires_subsystem_and_structural_pins(self) -> None:
        node = {
            "class": "K2Node_CallFunction",
            "type_id": "Messaging|BroadcastMessage",
            "pins": [
                pin("self", title="GameplayMessageSubsystem"),
                pin("Channel"),
                pin("Message", title="Payload"),
            ],
        }
        self.assertEqual(classify_message_node(node), "publish")
        node["pins"][0]["type_schema"]["title"] = "OtherSubsystem"
        self.assertIsNone(classify_message_node(node))

    def test_connected_channel_is_dynamic_even_with_a_default(self) -> None:
        result = channel_fact(
            pin(
                "Channel",
                value='(TagName="Fallback")',
                connections=[{"node": "N", "pin": "P"}],
            )
        )
        self.assertEqual(result["status"], "dynamic")
        self.assertIsNone(result["tag"])

    def test_operation_extracts_static_channel_payload_and_match(self) -> None:
        node = {
            "object_path": "/Game/BP.BP:EventGraph.Node_0",
            "class": "K2Node_AsyncAction_ListenForGameplayMessages",
            "type_id": "Messaging|ListenForGameplayMessages",
            "pins": [
                pin("Channel", value='(TagName="Game.Message")'),
                pin("PayloadType", value="/Script/Game.Payload"),
                pin("MatchType", value="PartialMatch"),
            ],
        }
        operation = message_operation(
            "/Game/BP",
            {"name": "EventGraph", "object_path": "/Game/BP.BP:EventGraph"},
            node,
        )
        self.assertIsNotNone(operation)
        self.assertEqual(operation["channel"]["tag"], "Game.Message")
        self.assertEqual(operation["payload_type"], "/Script/Game.Payload")
        self.assertEqual(operation["match_type"], "PartialMatch")


if __name__ == "__main__":
    unittest.main()
