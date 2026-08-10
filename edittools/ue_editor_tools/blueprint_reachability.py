from __future__ import annotations

import json
from collections import deque
from typing import Any

from .value_refs import unique_references


STRUCTURAL_NODE_MARKERS = (
    "k2node_event",
    "k2node_customevent",
    "k2node_componentboundevent",
    "k2node_functionentry",
    "k2node_functionresult",
    "k2node_knot",
    "k2node_tunnel",
    "animgraphnode_root",
)


def _is_exec_pin(pin: dict[str, Any]) -> bool:
    display = str(pin.get("type_display", "")).casefold()
    if display in {"exec", "execution"} or "exec" in display:
        return True
    schema = pin.get("type_schema")
    if schema is None:
        return False
    return "exec" in json.dumps(schema, ensure_ascii=False, sort_keys=True).casefold()


def _connections(pin: dict[str, Any]) -> list[str]:
    return [
        str(item.get("node")) for item in pin.get("connections", []) if item.get("node")
    ]


def _is_structural(node: dict[str, Any]) -> bool:
    class_name = " ".join(
        str(node.get(field, "")) for field in ("class", "class_path", "type_id")
    ).casefold()
    return any(marker in class_name for marker in STRUCTURAL_NODE_MARKERS)


def _summary(node: dict[str, Any]) -> dict[str, Any]:
    return {
        field: node[field]
        for field in ("object_path", "class", "class_path", "type_id", "title")
        if field in node
    }


def project_blueprint_nodes(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Project physical graph nodes into statically reachable semantic nodes."""
    by_path = {
        str(node["object_path"]): node for node in nodes if node.get("object_path")
    }
    roots: set[str] = set()
    for path, node in by_path.items():
        pins = list(node.get("pins", []))
        has_exec_input = any(
            str(pin.get("direction", "")).casefold() == "input" and _is_exec_pin(pin)
            for pin in pins
        )
        has_connected_exec_output = any(
            str(pin.get("direction", "")).casefold() == "output"
            and _is_exec_pin(pin)
            and _connections(pin)
            for pin in pins
        )
        class_name = " ".join(
            str(node.get(field, "")) for field in ("class", "class_path", "type_id")
        ).casefold()
        is_sink = any(marker in class_name for marker in ("result", "root", "tunnel"))
        has_connected_input = any(
            str(pin.get("direction", "")).casefold() == "input" and _connections(pin)
            for pin in pins
        )
        if (has_connected_exec_output and not has_exec_input) or (
            is_sink and has_connected_input
        ):
            roots.add(path)

    reachable: set[str] = set()
    pending = deque(sorted(roots, key=str.casefold))
    while pending:
        path = pending.popleft()
        if path in reachable or path not in by_path:
            continue
        reachable.add(path)
        node = by_path[path]
        for pin in node.get("pins", []):
            direction = str(pin.get("direction", "")).casefold()
            follow = direction == "input" or (
                direction == "output" and _is_exec_pin(pin)
            )
            if not follow:
                continue
            for target in _connections(pin):
                if target not in reachable:
                    pending.append(target)

    semantic = [
        _summary(by_path[path])
        for path in sorted(reachable, key=str.casefold)
        if not _is_structural(by_path[path])
    ]
    return {
        "reachable_paths": sorted(reachable, key=str.casefold),
        "semantic_nodes": semantic,
    }


def semantic_node_references(
    nodes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    references = unique_references(nodes)
    ignored_suffixes = (".object_path", ".class_path", ".connections")
    return [
        item
        for item in references
        if not str(item.get("field", "")).endswith(ignored_suffixes)
        and ".connections[" not in str(item.get("field", ""))
    ]
