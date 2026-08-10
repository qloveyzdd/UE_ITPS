from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .graph_model import Graph
from .identity import stable_id
from .storage import json_value


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
                certainty=str(relation.get("certainty", "confirmed")),
                resolution_status="resolved",
                confidence=1.0
                if relation.get("certainty", "confirmed") == "confirmed"
                else 0.5,
                probe_schema=schema,
                location=location,
                properties={
                    **dict(relation.get("properties", {})),
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
