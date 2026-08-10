from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .graph_model import Graph
from .identity import stable_id
from .storage import json_value


GAMEPLAY_MESSAGE_BRIDGE_SCHEMA = (
    "ue-itps.information-pool.gameplay-message-bridge"
)


def read_knowledge_graph(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    value = json.loads(resolved.read_text(encoding="utf-8-sig"))
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != "ue_build_knowledge_graph"
    ):
        raise ValueError(f"Knowledge graph input has an unsupported schema: {resolved}")
    if value.get("validation", {}).get("status") == "error":
        raise ValueError(f"Knowledge graph input failed validation: {resolved}")
    graph = value.get("graph")
    if not isinstance(graph, dict):
        raise ValueError(f"Knowledge graph input has no graph object: {resolved}")
    return value


def _local_key(node: dict[str, Any]) -> str:
    canonical = str(
        node.get("canonical_key") or node.get("name") or node.get("node_id")
    )
    marker = f"|{node.get('kind')}|"
    return canonical.split(marker, 1)[-1] if marker in canonical else canonical


def _resolved_symbol(graph: Graph, node: dict[str, Any]) -> str | None:
    kind = str(node.get("kind", ""))
    properties = node.get("properties", {})
    if kind in {"class", "row_struct", "payload_type"}:
        spelling = str(
            properties.get("path") or properties.get("type") or node.get("name") or ""
        )
        leaf = spelling.rsplit("/", 1)[-1].rsplit(".", 1)[-1]
        resolution = graph.resolve("type", leaf)
        return resolution.node_id if resolution.status == "resolved" else None
    if kind == "cxx_function":
        qualified = str(properties.get("qualified_name") or node.get("name") or "")
        owner, _, name = qualified.rpartition("::")
        resolution = graph.resolve("member_call", name or qualified, owner or None)
        return resolution.node_id if resolution.status == "resolved" else None
    return None


def _relation_semantics(value: object) -> tuple[str, str, float]:
    certainty = str(value or "confirmed")
    if certainty == "confirmed":
        return "observed", "resolved", 1.0
    if certainty == "unresolved":
        return "inferred", "unresolved", 0.5
    raise ValueError(f"Knowledge graph relation has unsupported certainty: {certainty}")


def merge_knowledge_graph(
    graph: Graph, document: dict[str, Any], source_path: Path
) -> dict[str, Any]:
    payload = document["graph"]
    mapping: dict[str, str] = {}
    for node in payload.get("nodes", []):
        source_id = str(node["node_id"])
        resolved = _resolved_symbol(graph, node)
        if resolved is not None:
            mapping[source_id] = resolved
            continue
        kind = str(node["kind"])
        local_key = _local_key(node)
        target_id = stable_id("logical", graph.key, kind, local_key)
        graph.add_node(
            node_id=target_id,
            kind=kind,
            name=str(node.get("name") or local_key),
            qualified_name=local_key,
            canonical_key=f"{graph.key}|{kind}|{local_key}",
            properties=dict(node.get("properties", {})),
        )
        mapping[source_id] = target_id

    evidence_by_relation: dict[str, list[dict[str, Any]]] = {}
    for evidence in payload.get("evidence", []):
        evidence_by_relation.setdefault(str(evidence["relation_id"]), []).append(
            evidence
        )
    schema = str(document["schema_version"])
    for relation in payload.get("relations", []):
        source_id = mapping.get(str(relation["source_id"]))
        target_id = mapping.get(str(relation["target_id"]))
        if source_id is None or target_id is None:
            raise ValueError("Knowledge graph relation references an unknown node")
        source_certainty = str(relation.get("certainty", "confirmed"))
        certainty, resolution_status, confidence = _relation_semantics(source_certainty)
        evidence_items = evidence_by_relation.get(str(relation["relation_id"])) or [{}]
        for evidence in evidence_items:
            location = None
            if evidence.get("path") is not None:
                location = {
                    "root": str(evidence.get("root") or "project"),
                    "path": str(evidence["path"]).replace("\\", "/"),
                    "line": int(evidence.get("line") or 0),
                    "end_line": int(evidence["end_line"])
                    if evidence.get("end_line") is not None
                    else None,
                }
            elif evidence.get("asset") or evidence.get("node") or evidence.get("graph"):
                location = {
                    "root": "editor",
                    "path": str(
                        evidence.get("node")
                        or evidence.get("graph")
                        or evidence.get("asset")
                    ),
                    "line": 0,
                    "end_line": None,
                }
            graph.add_relation(
                source_id=source_id,
                kind=str(relation["kind"]),
                target_id=target_id,
                certainty=certainty,
                resolution_status=resolution_status,
                confidence=confidence,
                probe_schema=schema,
                location=location,
                properties={
                    **dict(relation.get("properties", {})),
                    "source_certainty": source_certainty,
                    "knowledge_graph_source": str(source_path.resolve()),
                    "evidence": {
                        key: value
                        for key, value in evidence.items()
                        if key not in {"evidence_id", "relation_id"}
                    },
                },
            )
    return {
        "probe_key": stable_id(
            "probe",
            "knowledge_graph",
            str(source_path.resolve()),
            document.get("graph", {}).get("counts", {}),
        ),
        "source_unit": str(source_path.resolve()),
        "probe_kind": "knowledge_graph",
        "selector": "",
        "input_hash": stable_id("input", json_value(document)),
        "schema_version": schema,
        "payload_json": json_value(document),
    }


def bridge_gameplay_message_dispatches(graph: Graph) -> int:
    publishers_by_tag: dict[str, list[dict[str, Any]]] = {}
    subscribers_by_tag: dict[str, list[dict[str, Any]]] = {}
    existing = {
        (
            str(relation["source_id"]),
            str(relation["kind"]),
            str(relation["target_id"]),
        )
        for relation in graph.relations.values()
    }
    for relation in graph.relations.values():
        if relation["resolution_status"] != "resolved":
            continue
        target_id = str(relation["target_id"])
        target = graph.nodes.get(target_id)
        if target is None or target["kind"] != "gameplay_tag":
            continue
        if relation["kind"] == "PUBLISHES_EVENT":
            publishers_by_tag.setdefault(target_id, []).append(relation)
        elif relation["kind"] == "SUBSCRIBES_EVENT":
            subscribers_by_tag.setdefault(target_id, []).append(relation)

    added = 0
    for tag_id in sorted(set(publishers_by_tag) & set(subscribers_by_tag)):
        publishers = sorted(
            publishers_by_tag[tag_id],
            key=lambda item: str(item["relation_id"]),
        )
        publisher_ids = [str(item["relation_id"]) for item in publishers]
        publisher_confidence = max(
            float(item["confidence"]) for item in publishers
        )
        subscribers = sorted(
            subscribers_by_tag[tag_id],
            key=lambda item: (
                str(item["source_id"]),
                str(item["relation_id"]),
            ),
        )
        for subscriber in subscribers:
            subscriber_id = str(subscriber["source_id"])
            edge = (tag_id, "DISPATCHES_TO", subscriber_id)
            if edge in existing:
                continue
            graph.add_relation(
                source_id=tag_id,
                kind="DISPATCHES_TO",
                target_id=subscriber_id,
                certainty="inferred",
                resolution_status="resolved",
                confidence=min(
                    0.9,
                    publisher_confidence,
                    float(subscriber["confidence"]),
                ),
                probe_schema=GAMEPLAY_MESSAGE_BRIDGE_SCHEMA,
                properties={
                    "dispatch_semantics": "potential_runtime_delivery",
                    "publisher_relation_ids": publisher_ids,
                    "subscriber_relation_id": str(subscriber["relation_id"]),
                    "tag_node_id": tag_id,
                },
            )
            existing.add(edge)
            added += 1
    return added
