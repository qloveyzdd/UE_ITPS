"""Tiered, read-only queries over a built UE knowledge graph.

The builder keeps the graph lossless.  This module deliberately exposes a
small set of progressively more detailed projections so callers do not need
to query the raw fact documents or copy the whole graph into their response.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .graph_summary import DISPLAY_RELATIONS, GraphSummary


SCHEMA_VERSION = "ue_query_knowledge_graph"
QUERY_LEVELS = ("overview", "system", "entity", "evidence")


def _fold(value: Any) -> str:
    return str(value or "").casefold()


class KnowledgeGraphQuery:
    """Build deterministic projections from one validated graph document."""

    def __init__(
        self,
        document: dict[str, Any],
        *,
        max_nodes: int = 120,
        max_relations: int = 120,
    ) -> None:
        if document.get("schema_version") != "ue_build_knowledge_graph":
            raise ValueError("Input is not a ue_build_knowledge_graph document")
        if not isinstance(document.get("graph"), dict):
            raise ValueError("Input graph must be an object")
        self.document = document
        self.summary = GraphSummary(
            document,
            max_nodes=max(1, int(max_nodes)),
            max_relations=max(1, int(max_relations)),
        )

    @property
    def project(self) -> str:
        return self.summary.project

    def _node_matches(self, node_id: str, query: str) -> bool:
        if not query:
            return True
        node = self.summary.nodes[node_id]
        properties = node.get("properties") if isinstance(node.get("properties"), dict) else {}
        candidates = [
            node.get("name"),
            node.get("kind"),
            node.get("canonical_key"),
            properties.get("path"),
            properties.get("object_path"),
            properties.get("qualified_name"),
            properties.get("tag"),
            properties.get("symbol_name"),
        ]
        folded = _fold(query)
        return any(folded in _fold(candidate) for candidate in candidates)

    def _matching_nodes(self, query: str = "") -> list[str]:
        selected = [node_id for node_id in self.summary.nodes if self._node_matches(node_id, query)]
        return self.summary._sorted_node_ids(selected)

    def _resolve_entities(self, selectors: Iterable[str], query: str = "") -> list[str]:
        values = [str(item).strip() for item in selectors if str(item).strip()]
        if not values:
            values = [query.strip()] if query.strip() else []
        resolved: list[str] = []
        for value in values:
            if value in self.summary.nodes:
                resolved.append(value)
                continue
            exact = [
                node_id
                for node_id, node in self.summary.nodes.items()
                if _fold(node.get("name")) == _fold(value)
            ]
            if len(exact) == 1:
                resolved.extend(exact)
                continue
            matches = self._matching_nodes(value)
            if not matches:
                raise KeyError(f"Entity not found: {value}")
            resolved.append(matches[0])
        return list(dict.fromkeys(resolved))

    def _evidence_for_relations(self, relations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for relation in relations:
            relation_id = str(relation.get("relation_id"))
            evidence.extend(self.summary.evidence_by_relation.get(relation_id, []))
        return sorted(evidence, key=lambda item: str(item.get("evidence_id") or ""))

    def overview(self, query: str = "") -> dict[str, Any]:
        result = self.summary.overview()
        if query.strip():
            matches = self._matching_nodes(query)
            result["matches"] = [self.summary.compact_node(node_id) for node_id in matches[: self.summary.max_nodes]]
            result["match_count"] = len(matches)
        return result

    def systems(self, query: str = "", selectors: Iterable[str] = ()) -> dict[str, Any]:
        result = self.summary.systems()
        values = [str(item).strip() for item in selectors if str(item).strip()]
        folded_query = _fold(query.strip())
        if values or folded_query:
            requested = {_fold(value) for value in values}
            result["systems"] = [
                item
                for item in result["systems"]
                if (
                    _fold(item.get("system_id")) in requested
                    or _fold(item.get("name")) in requested
                    or (folded_query and (folded_query in _fold(item.get("system_id")) or folded_query in _fold(item.get("name"))))
                )
            ]
        return result

    def entities(self, selectors: Iterable[str], query: str = "") -> dict[str, Any]:
        node_ids = self._resolve_entities(selectors, query)
        result: dict[str, Any] = {}
        for node_id in node_ids[: self.summary.max_nodes]:
            result[node_id] = self.summary.entity(node_id)
        return result

    def evidence(self, selectors: Iterable[str], query: str = "") -> dict[str, Any]:
        values = [str(item).strip() for item in selectors if str(item).strip()]
        if not values and query.strip():
            values = [query.strip()]
        if not values:
            raise ValueError("evidence level requires --select or --query")

        relation_ids: list[str] = []
        entity_ids: list[str] = []
        for value in values:
            if value in self.summary.relations:
                relation_ids.append(value)
                continue
            entity_ids.extend(self._resolve_entities([value]))

        relations: list[dict[str, Any]] = []
        for relation_id in relation_ids:
            relations.append(self.summary.relations[relation_id])
        for node_id in entity_ids:
            relations.extend(
                relation
                for relation in self.summary.relations_by_node.get(node_id, [])
                if str(relation.get("kind")) in {"REFERENCES", "SOFT_REFERENCES"}
                or str(relation.get("kind")) in DISPLAY_RELATIONS
            )
        unique = {str(item.get("relation_id")): item for item in relations if item.get("relation_id")}
        ordered = self.summary._sorted_relations(unique.values())[: self.summary.max_relations]
        selected_nodes = {
            endpoint
            for relation in ordered
            for endpoint in (str(relation.get("source_id")), str(relation.get("target_id")))
            if endpoint in self.summary.nodes
        }
        selected_nodes.update(entity_ids)
        evidence = self._evidence_for_relations(ordered)
        return {
            "nodes": [self.summary.compact_node(node_id) for node_id in self.summary._sorted_node_ids(selected_nodes)],
            "relations": [self.summary.compact_relation(relation) for relation in ordered],
            "evidence": evidence,
            "evidence_count": len(evidence),
        }

    def query(
        self,
        level: str,
        *,
        selectors: Iterable[str] = (),
        query: str = "",
    ) -> dict[str, Any]:
        if level not in QUERY_LEVELS:
            raise ValueError(f"Unsupported query level: {level}")
        if level == "overview":
            return self.overview(query)
        if level == "system":
            return self.systems(query, selectors)
        if level == "entity":
            return {"entities": self.entities(selectors, query)}
        return self.evidence(selectors, query)
