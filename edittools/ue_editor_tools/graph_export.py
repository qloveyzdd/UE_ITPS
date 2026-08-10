from __future__ import annotations

import hashlib
import json
from typing import Any


def _id(kind: str, *parts: Any) -> str:
    payload = json.dumps(
        [kind, *parts], ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return f"{kind}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def export_message_graph(scan: dict[str, Any]) -> dict[str, Any]:
    editor = scan.get("editor", {})
    project_key = str(
        editor.get("project") or editor.get("project_root") or "unknown-project"
    )
    nodes: dict[str, dict[str, Any]] = {}
    relations: dict[str, dict[str, Any]] = {}
    evidence: dict[str, dict[str, Any]] = {}

    def add_node(
        kind: str, key: str, name: str, properties: dict[str, Any] | None = None
    ) -> str:
        node_id = _id(kind, project_key, key)
        nodes.setdefault(
            node_id,
            {
                "node_id": node_id,
                "kind": kind,
                "name": name,
                "canonical_key": f"{project_key}|{kind}|{key}",
                "properties": properties or {},
            },
        )
        return node_id

    def add_relation(
        source_id: str,
        kind: str,
        target_id: str,
        *,
        certainty: str = "confirmed",
        properties: dict[str, Any] | None = None,
        asset: str | None = None,
        graph: str | None = None,
        node: str | None = None,
    ) -> None:
        relation_id = _id("relation", source_id, kind, target_id)
        relations.setdefault(
            relation_id,
            {
                "relation_id": relation_id,
                "source_id": source_id,
                "kind": kind,
                "target_id": target_id,
                "certainty": certainty,
                "properties": properties or {},
            },
        )
        evidence_id = _id("evidence", relation_id, asset, graph, node)
        evidence[evidence_id] = {
            "evidence_id": evidence_id,
            "relation_id": relation_id,
            "asset": asset,
            "graph": graph,
            "node": node,
            "detail": properties or {},
        }

    asset_ids: dict[str, str] = {}

    def ensure_asset(asset: str) -> str:
        if asset not in asset_ids:
            asset_ids[asset] = add_node(
                "asset", asset, asset.rsplit("/", 1)[-1], {"package": asset}
            )
        return asset_ids[asset]

    for operation in scan.get("operations", []):
        asset = str(operation["asset"])
        graph_path = str(operation["graph_path"])
        node_path = str(operation["node"])
        asset_id = ensure_asset(asset)
        graph_id = add_node(
            "blueprint_graph",
            graph_path,
            str(operation["graph"]),
            {"asset": asset, "object_path": graph_path},
        )
        node_id = add_node(
            "blueprint_node",
            node_path,
            str(operation["node_type"]),
            {
                "asset": asset,
                "graph": str(operation["graph"]),
                "object_path": node_path,
                "class": str(operation["node_class"]),
                "operation": str(operation["operation"]),
            },
        )
        add_relation(
            asset_id, "CONTAINS", graph_id, asset=asset, graph=str(operation["graph"])
        )
        add_relation(
            graph_id,
            "CONTAINS",
            node_id,
            asset=asset,
            graph=str(operation["graph"]),
            node=node_path,
        )

        channel = operation.get("channel", {})
        tag = channel.get("tag")
        if tag:
            target_id = add_node("gameplay_tag", str(tag), str(tag), {"tag": str(tag)})
            certainty = "confirmed"
        else:
            expression_key = f"{node_path}|Channel"
            target_id = add_node(
                "message_channel_expression",
                expression_key,
                "Dynamic Channel",
                {
                    "status": channel.get("status"),
                    "connections": channel.get("connections", []),
                },
            )
            certainty = "unresolved"
        relation_kind = (
            "PUBLISHES_EVENT"
            if operation["operation"] == "publish"
            else "SUBSCRIBES_EVENT"
        )
        add_relation(
            node_id,
            relation_kind,
            target_id,
            certainty=certainty,
            properties={
                "channel_status": channel.get("status"),
                "match_type": operation.get("match_type"),
            },
            asset=asset,
            graph=str(operation["graph"]),
            node=node_path,
        )
        payload = operation.get("payload_type")
        if payload:
            payload_id = add_node(
                "payload_type",
                str(payload),
                str(payload).rsplit(".", 1)[-1],
                {"type": payload},
            )
            add_relation(
                node_id,
                "USES_TYPE",
                payload_id,
                asset=asset,
                graph=str(operation["graph"]),
                node=node_path,
            )

    for item in scan.get("tag_referencers", []):
        tag = str(item["tag"])
        tag_id = add_node("gameplay_tag", tag, tag, {"tag": tag})
        for asset in item.get("referencers", []):
            asset = str(asset)
            asset_id = ensure_asset(asset)
            add_relation(
                asset_id,
                "REFERENCES",
                tag_id,
                asset=asset,
                properties={"reference_kind": "searchable_name"},
            )

    return {
        "project": project_key,
        "nodes": sorted(nodes.values(), key=lambda item: item["node_id"]),
        "relations": sorted(relations.values(), key=lambda item: item["relation_id"]),
        "evidence": sorted(evidence.values(), key=lambda item: item["evidence_id"]),
        "counts": {
            "nodes": len(nodes),
            "relations": len(relations),
            "evidence": len(evidence),
        },
    }
