from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any


def stable_id(namespace: str, *parts: object) -> str:
    payload = "\0".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{namespace}:{digest}"


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@dataclass(frozen=True)
class Node:
    node_id: str
    kind: str
    name: str
    path: str | None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    edge_id: str
    source_id: str
    target_id: str
    kind: str
    certainty: str
    resolution_status: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    edge_id: str
    path: str | None
    line: int | None
    extractor: str
    detail: dict[str, Any] = field(default_factory=dict)


class FileGraph:
    def __init__(self, project_path: str) -> None:
        self.project_path = project_path
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, Edge] = {}
        self.evidence: dict[str, Evidence] = {}
        self.warnings: list[dict[str, Any]] = []

    def add_node(
        self,
        *,
        kind: str,
        name: str,
        path: str | None,
        identity: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> str:
        canonical = identity or f"{kind}|{path or name}"
        node_id = stable_id("node", canonical)
        incoming = Node(node_id, kind, name, path, properties or {})
        existing = self.nodes.get(node_id)
        if existing is None:
            self.nodes[node_id] = incoming
        elif existing != incoming:
            merged = {**existing.properties, **incoming.properties}
            self.nodes[node_id] = Node(
                node_id,
                existing.kind,
                existing.name,
                existing.path,
                merged,
            )
        return node_id

    def add_edge(
        self,
        *,
        source_id: str,
        target_id: str,
        kind: str,
        certainty: str = "observed",
        resolution_status: str = "resolved",
        properties: dict[str, Any] | None = None,
        evidence_path: str | None = None,
        evidence_line: int | None = None,
        extractor: str,
        evidence_detail: dict[str, Any] | None = None,
    ) -> str:
        edge_properties = properties or {}
        edge_id = stable_id(
            "edge",
            source_id,
            kind,
            target_id,
            json_text(edge_properties),
        )
        self.edges[edge_id] = Edge(
            edge_id,
            source_id,
            target_id,
            kind,
            certainty,
            resolution_status,
            edge_properties,
        )
        evidence_id = stable_id(
            "evidence",
            edge_id,
            evidence_path or "",
            evidence_line or 0,
            extractor,
            json_text(evidence_detail or {}),
        )
        self.evidence[evidence_id] = Evidence(
            evidence_id,
            edge_id,
            evidence_path,
            evidence_line,
            extractor,
            evidence_detail or {},
        )
        return edge_id

    def add_validation(self, document: dict[str, Any], source: str) -> None:
        for problem in document.get("validation", {}).get("problems", []):
            self.warnings.append({"source": source, **problem})
