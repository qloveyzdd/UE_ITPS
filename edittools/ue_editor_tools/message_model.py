from __future__ import annotations

import re
from typing import Any


TAG_VALUE = re.compile(r'TagName\s*=\s*"([^"]+)"')


def pin_map(
    node: dict[str, Any], direction: str = "input"
) -> dict[str, dict[str, Any]]:
    return {
        str(pin["name"]): pin
        for pin in node.get("pins", [])
        if pin.get("direction") == direction
    }


def classify_message_node(node: dict[str, Any]) -> str | None:
    node_class = str(node.get("class", ""))
    inputs = pin_map(node)
    if (
        node_class.startswith("K2Node_AsyncAction_ListenForGameplayMessage")
        and "Channel" in inputs
    ):
        return "subscribe"
    if node_class == "K2Node_CallFunction" and {"self", "Channel", "Message"}.issubset(
        inputs
    ):
        self_schema = inputs["self"].get("type_schema") or {}
        self_title = str(self_schema.get("title", ""))
        type_leaf = re.sub(
            r"[^a-z0-9]", "", str(node.get("type_id", "")).split("|")[-1].casefold()
        )
        if self_title == "GameplayMessageSubsystem" and type_leaf.startswith(
            "broadcastmessage"
        ):
            return "publish"
    return None


def channel_fact(pin: dict[str, Any]) -> dict[str, Any]:
    connections = list(pin.get("connections", []))
    value = str(pin.get("value", ""))
    match = TAG_VALUE.search(value)
    if connections:
        return {
            "status": "dynamic",
            "tag": None,
            "value": value,
            "connections": connections,
        }
    if match:
        return {
            "status": "static",
            "tag": match.group(1),
            "value": value,
            "connections": [],
        }
    return {"status": "unresolved", "tag": None, "value": value, "connections": []}


def payload_type(operation: str, inputs: dict[str, dict[str, Any]]) -> str | None:
    pin = inputs.get("PayloadType" if operation == "subscribe" else "Message")
    if not pin:
        return None
    if pin.get("value"):
        return str(pin["value"])
    schema = pin.get("type_schema") or {}
    return str(schema.get("title")) if schema.get("title") else None


def message_operation(
    asset: str, graph: dict[str, Any], node: dict[str, Any]
) -> dict[str, Any] | None:
    operation = classify_message_node(node)
    if operation is None:
        return None
    inputs = pin_map(node)
    channel_pin = inputs["Channel"]
    match_pin = inputs.get("MatchType")
    return {
        "asset": asset,
        "graph": str(graph["name"]),
        "graph_path": str(graph["object_path"]),
        "node": str(node["object_path"]),
        "node_class": str(node["class"]),
        "node_type": str(node["type_id"]),
        "operation": operation,
        "channel": channel_fact(channel_pin),
        "payload_type": payload_type(operation, inputs),
        "match_type": str(match_pin.get("value")) if match_pin else None,
        "evidence_pins": [
            pin
            for pin in node.get("pins", [])
            if pin.get("name")
            in {"self", "Channel", "Message", "PayloadType", "MatchType"}
        ],
    }
