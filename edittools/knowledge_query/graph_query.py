"""细粒度、只读的 UE 知识图谱查询。

查询层只消费已经构建并校验的 knowledge graph，不重新扫描原始项目文件。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from ue_editor_tools.graph_summary import DISPLAY_RELATIONS, SLICE_RULES, GraphSummary


SCHEMA_VERSION = "ue_query_knowledge_graph"
LEGACY_LEVELS = ("overview", "system", "entity", "evidence")
OPERATIONS = (
    "search",
    "inspect",
    "neighbors",
    "trace",
    "impact",
    "evidence",
    "uncertainty",
    "domain",
    "compare",
)
DIRECTIONS = ("both", "incoming", "outgoing")
CERTAINTIES = ("confirmed", "candidate", "unresolved", "name_only")


def _fold(value: Any) -> str:
    return str(value or "").casefold()


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{_text(key)} {_text(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(item) for item in value)
    return str(value)


class KnowledgeGraphQuery:
    """在一个 knowledge graph 文档上提供确定性的查询操作。"""

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

    def _node_matches(
        self,
        node_id: str,
        query: str = "",
        *,
        kinds: Iterable[str] = (),
        certainties: Iterable[str] = (),
    ) -> bool:
        node = self.summary.nodes[node_id]
        kind_filter = {_fold(item) for item in kinds if str(item).strip()}
        if kind_filter and _fold(node.get("kind")) not in kind_filter:
            return False
        certainty_filter = set(certainties)
        if certainty_filter:
            confidence = self.summary.compact_node(node_id)["confidence"]
            if confidence not in certainty_filter:
                return False
        if not query.strip():
            return True
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

    def _matching_nodes(
        self,
        query: str = "",
        *,
        kinds: Iterable[str] = (),
        certainties: Iterable[str] = (),
    ) -> list[str]:
        selected = [
            node_id
            for node_id in self.summary.nodes
            if self._node_matches(node_id, query, kinds=kinds, certainties=certainties)
        ]
        return self.summary._sorted_node_ids(selected)

    def _relation_matches(
        self,
        relation: dict[str, Any],
        query: str = "",
        *,
        kinds: Iterable[str] = (),
        certainties: Iterable[str] = (),
    ) -> bool:
        kind_filter = {_fold(item) for item in kinds if str(item).strip()}
        certainty_filter = {str(item) for item in certainties if str(item).strip()}
        if kind_filter and _fold(relation.get("kind")) not in kind_filter:
            return False
        if certainty_filter and str(relation.get("certainty") or "confirmed") not in certainty_filter:
            return False
        if not query.strip():
            return True
        source = self.summary.nodes.get(str(relation.get("source_id")), {})
        target = self.summary.nodes.get(str(relation.get("target_id")), {})
        haystack = " ".join(
            (
                _text(relation.get("relation_id")),
                _text(relation.get("kind")),
                _text(relation.get("properties")),
                _text(source.get("name")),
                _text(target.get("name")),
            )
        )
        return _fold(query) in _fold(haystack)

    def _matching_relations(
        self,
        query: str = "",
        *,
        kinds: Iterable[str] = (),
        certainties: Iterable[str] = (),
    ) -> list[dict[str, Any]]:
        matches = [
            relation
            for relation in self.summary.relations.values()
            if self._relation_matches(relation, query, kinds=kinds, certainties=certainties)
        ]
        return self.summary._sorted_relations(matches)

    def _resolve_entities(self, selectors: Iterable[str], query: str = "") -> list[str]:
        values = [str(item).strip() for item in selectors if str(item).strip()]
        if not values and query.strip():
            values = [query.strip()]
        if not values:
            raise ValueError("This operation requires --select or --query")
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
            matches = exact or self._matching_nodes(value)
            if not matches:
                raise KeyError(f"Entity not found: {value}")
            resolved.append(matches[0])
        return list(dict.fromkeys(resolved))

    def _relation_allowed(
        self,
        relation: dict[str, Any],
        relation_kinds: Iterable[str],
        certainties: Iterable[str],
    ) -> bool:
        return self._relation_matches(
            relation,
            kinds=relation_kinds,
            certainties=certainties,
        )

    def _incident_relations(
        self,
        node_id: str,
        *,
        direction: str = "both",
        relation_kinds: Iterable[str] = (),
        certainties: Iterable[str] = (),
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for relation in self.summary.relations_by_node.get(node_id, []):
            if not self._relation_allowed(relation, relation_kinds, certainties):
                continue
            source_id = str(relation.get("source_id"))
            target_id = str(relation.get("target_id"))
            if direction == "outgoing" and source_id != node_id:
                continue
            if direction == "incoming" and target_id != node_id:
                continue
            result.append(relation)
        return self.summary._sorted_relations(result)

    def _neighbor_id(self, relation: dict[str, Any], node_id: str, direction: str) -> str | None:
        source_id = str(relation.get("source_id"))
        target_id = str(relation.get("target_id"))
        if direction == "outgoing":
            return target_id if source_id == node_id else None
        if direction == "incoming":
            return source_id if target_id == node_id else None
        if source_id == node_id:
            return target_id
        if target_id == node_id:
            return source_id
        return None

    def _trace(
        self,
        selectors: Iterable[str],
        *,
        query: str = "",
        direction: str = "both",
        depth: int = 1,
        relation_kinds: Iterable[str] = (),
        certainties: Iterable[str] = (),
    ) -> dict[str, Any]:
        centers = self._resolve_entities(selectors, query)
        safe_depth = max(1, min(8, int(depth)))
        distances: dict[str, int] = {node_id: 0 for node_id in centers}
        relation_ids: set[str] = set()
        frontier = list(centers)
        truncated = False
        for _ in range(safe_depth):
            if not frontier:
                break
            next_frontier: list[str] = []
            for current in frontier:
                for relation in self._incident_relations(
                    current,
                    direction=direction,
                    relation_kinds=relation_kinds,
                    certainties=certainties,
                ):
                    relation_id = str(relation.get("relation_id"))
                    relation_ids.add(relation_id)
                    neighbor = self._neighbor_id(relation, current, direction)
                    if not neighbor or neighbor in distances:
                        continue
                    if len(distances) >= self.summary.max_nodes:
                        truncated = True
                        continue
                    distances[neighbor] = distances[current] + 1
                    next_frontier.append(neighbor)
            frontier = list(dict.fromkeys(next_frontier))
        relations = [
            self.summary.relations[relation_id]
            for relation_id in sorted(relation_ids)
            if relation_id in self.summary.relations
            and str(self.summary.relations[relation_id].get("source_id")) in distances
            and str(self.summary.relations[relation_id].get("target_id")) in distances
        ]
        relations = self.summary._sorted_relations(relations)[: self.summary.max_relations]
        nodes = [
            {**self.summary.compact_node(node_id), "distance": distances[node_id]}
            for node_id in self.summary._sorted_node_ids(distances)
        ]
        return {
            "center_ids": centers,
            "nodes": nodes,
            "relations": [self.summary.compact_relation(relation) for relation in relations],
            "truncated": truncated,
            "depth": safe_depth,
            "direction": direction,
        }

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
            result["matches"] = [
                self.summary.compact_node(node_id)
                for node_id in matches[: self.summary.max_nodes]
            ]
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
                    or (
                        folded_query
                        and (
                            folded_query in _fold(item.get("system_id"))
                            or folded_query in _fold(item.get("name"))
                        )
                    )
                )
            ]
        return result

    def search(
        self,
        *,
        query: str = "",
        node_kinds: Iterable[str] = (),
        relation_kinds: Iterable[str] = (),
        certainties: Iterable[str] = (),
    ) -> dict[str, Any]:
        node_ids = self._matching_nodes(query, kinds=node_kinds)
        relations = self._matching_relations(
            query,
            kinds=relation_kinds,
            certainties=certainties,
        )
        return {
            "nodes": [
                self.summary.compact_node(node_id)
                for node_id in node_ids[: self.summary.max_nodes]
            ],
            "relations": [
                self.summary.compact_relation(relation)
                for relation in relations[: self.summary.max_relations]
            ],
            "node_match_count": len(node_ids),
            "relation_match_count": len(relations),
        }

    def inspect(self, selectors: Iterable[str], query: str = "") -> dict[str, Any]:
        node_ids = self._resolve_entities(selectors, query)
        entities: dict[str, Any] = {}
        for node_id in node_ids[: self.summary.max_nodes]:
            incident = self.summary.relations_by_node.get(node_id, [])
            entities[node_id] = {
                **self.summary.entity(node_id),
                "degree": {
                    "incoming": sum(1 for item in incident if str(item.get("target_id")) == node_id),
                    "outgoing": sum(1 for item in incident if str(item.get("source_id")) == node_id),
                    "total": len(incident),
                },
            }
        return {"entities": entities}

    def neighbors(
        self,
        selectors: Iterable[str],
        *,
        query: str = "",
        direction: str = "both",
        relation_kinds: Iterable[str] = (),
        certainties: Iterable[str] = (),
    ) -> dict[str, Any]:
        return self._trace(
            selectors,
            query=query,
            direction=direction,
            depth=1,
            relation_kinds=relation_kinds,
            certainties=certainties,
        )

    def trace(
        self,
        selectors: Iterable[str],
        *,
        query: str = "",
        direction: str = "both",
        depth: int = 1,
        relation_kinds: Iterable[str] = (),
        certainties: Iterable[str] = (),
    ) -> dict[str, Any]:
        return self._trace(
            selectors,
            query=query,
            direction=direction,
            depth=depth,
            relation_kinds=relation_kinds,
            certainties=certainties,
        )

    def impact(
        self,
        selectors: Iterable[str],
        *,
        query: str = "",
        depth: int = 1,
        relation_kinds: Iterable[str] = (),
        certainties: Iterable[str] = (),
    ) -> dict[str, Any]:
        return self._trace(
            selectors,
            query=query,
            direction="incoming",
            depth=depth,
            relation_kinds=relation_kinds,
            certainties=certainties,
        )

    def evidence(
        self,
        selectors: Iterable[str],
        *,
        query: str = "",
        relation_kinds: Iterable[str] = (),
        certainties: Iterable[str] = (),
    ) -> dict[str, Any]:
        values = [str(item).strip() for item in selectors if str(item).strip()]
        if not values and query.strip():
            values = [query.strip()]
        if not values:
            raise ValueError("evidence operation requires --select or --query")
        relation_ids: list[str] = []
        entity_ids: list[str] = []
        for value in values:
            if value in self.summary.relations:
                relation_ids.append(value)
            else:
                entity_ids.extend(self._resolve_entities([value]))
        relations = [
            self.summary.relations[relation_id]
            for relation_id in relation_ids
            if self._relation_allowed(
                self.summary.relations[relation_id], relation_kinds, certainties
            )
        ]
        for node_id in entity_ids:
            relations.extend(
                relation
                for relation in self.summary.relations_by_node.get(node_id, [])
                if self._relation_allowed(relation, relation_kinds, certainties)
                and (
                    str(relation.get("kind")) in DISPLAY_RELATIONS
                    or str(relation.get("kind")) in {"REFERENCES", "SOFT_REFERENCES"}
                )
            )
        unique = {
            str(item.get("relation_id")): item
            for item in relations
            if item.get("relation_id")
        }
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
            "nodes": [
                self.summary.compact_node(node_id)
                for node_id in self.summary._sorted_node_ids(selected_nodes)
            ],
            "relations": [self.summary.compact_relation(relation) for relation in ordered],
            "evidence": evidence,
            "evidence_count": len(evidence),
        }

    def uncertainty(
        self,
        *,
        selectors: Iterable[str] = (),
        query: str = "",
        certainties: Iterable[str] = (),
    ) -> dict[str, Any]:
        selector_values = [str(item).strip() for item in selectors if str(item).strip()]
        selected_entities = self._resolve_entities(selector_values) if selector_values else []
        requested = set(certainties) or {"candidate", "unresolved", "name_only"}
        node_ids = self._matching_nodes(query, certainties=requested)
        relations = self._matching_relations(query, certainties=requested)
        if selected_entities:
            scope = set(selected_entities)
            relations = [
                relation
                for relation in relations
                if {
                    str(relation.get("source_id")),
                    str(relation.get("target_id")),
                }
                & scope
            ]
            node_ids = [
                node_id
                for node_id in node_ids
                if node_id in scope
                or any(
                    node_id in {
                        str(relation.get("source_id")),
                        str(relation.get("target_id")),
                    }
                    for relation in relations
                )
            ]
        return {
            "requested_certainties": sorted(requested),
            "nodes": [
                self.summary.compact_node(node_id)
                for node_id in node_ids[: self.summary.max_nodes]
            ],
            "relations": [
                self.summary.compact_relation(relation)
                for relation in relations[: self.summary.max_relations]
            ],
            "node_match_count": len(node_ids),
            "relation_match_count": len(relations),
        }

    def domain(self, *, query: str = "", selectors: Iterable[str] = ()) -> dict[str, Any]:
        values = [str(item).strip() for item in selectors if str(item).strip()]
        slice_ids = [value for value in values if value in SLICE_RULES]
        system_selectors = [value for value in values if value not in SLICE_RULES]
        systems = self.systems(query, system_selectors)
        slices = {slice_id: self.summary.slice(slice_id) for slice_id in slice_ids}
        if query.strip() and not system_selectors and not slice_ids:
            folded = _fold(query)
            for slice_id, rule in SLICE_RULES.items():
                if folded in _fold(slice_id) or folded in _fold(rule.get("name")):
                    slices[slice_id] = self.summary.slice(slice_id)
        return {
            "systems": systems["systems"],
            "cross_system_relations": systems["cross_system_relations"],
            "slices": slices,
        }

    def compare(self, selectors: Iterable[str]) -> dict[str, Any]:
        values = [str(item).strip() for item in selectors if str(item).strip()]
        if len(values) != 2:
            raise ValueError("compare operation requires exactly two --select values")
        left_id, right_id = self._resolve_entities(values)

        def neighbor_ids(node_id: str) -> set[str]:
            return {
                (
                    str(item.get("target_id"))
                    if str(item.get("source_id")) == node_id
                    else str(item.get("source_id"))
                )
                for item in self.summary.relations_by_node.get(node_id, [])
            } - {node_id}

        left_neighbors = neighbor_ids(left_id)
        right_neighbors = neighbor_ids(right_id)
        left_relations = self.summary.relations_by_node.get(left_id, [])
        right_relations = self.summary.relations_by_node.get(right_id, [])
        left_kinds = Counter(str(item.get("kind")) for item in left_relations)
        right_kinds = Counter(str(item.get("kind")) for item in right_relations)
        return {
            "left": self.summary.compact_node(left_id),
            "right": self.summary.compact_node(right_id),
            "shared_neighbor_ids": sorted(left_neighbors & right_neighbors),
            "only_left_neighbor_ids": sorted(left_neighbors - right_neighbors),
            "only_right_neighbor_ids": sorted(right_neighbors - left_neighbors),
            "relation_kind_counts": {
                "left": dict(sorted(left_kinds.items())),
                "right": dict(sorted(right_kinds.items())),
                "shared": sorted(set(left_kinds) & set(right_kinds)),
            },
        }

    def query(
        self,
        level: str | None = None,
        *,
        operation: str | None = None,
        selectors: Iterable[str] = (),
        query: str = "",
        node_kinds: Iterable[str] = (),
        relation_kinds: Iterable[str] = (),
        certainties: Iterable[str] = (),
        direction: str = "both",
        depth: int = 1,
    ) -> dict[str, Any]:
        if operation is None:
            if level not in LEGACY_LEVELS:
                raise ValueError(f"Unsupported query level: {level}")
            if level == "overview":
                return self.overview(query)
            if level == "system":
                return self.systems(query, selectors)
            if level == "entity":
                return self.inspect(selectors, query)
            return self.evidence(
                selectors,
                query=query,
                relation_kinds=relation_kinds,
                certainties=certainties,
            )
        if operation not in OPERATIONS:
            raise ValueError(f"Unsupported query operation: {operation}")
        if operation == "search":
            return self.search(
                query=query,
                node_kinds=node_kinds,
                relation_kinds=relation_kinds,
                certainties=certainties,
            )
        if operation == "inspect":
            return self.inspect(selectors, query)
        if operation == "neighbors":
            return self.neighbors(
                selectors,
                query=query,
                direction=direction,
                relation_kinds=relation_kinds,
                certainties=certainties,
            )
        if operation == "trace":
            return self.trace(
                selectors,
                query=query,
                direction=direction,
                depth=depth,
                relation_kinds=relation_kinds,
                certainties=certainties,
            )
        if operation == "impact":
            return self.impact(
                selectors,
                query=query,
                depth=depth,
                relation_kinds=relation_kinds,
                certainties=certainties,
            )
        if operation == "evidence":
            return self.evidence(
                selectors,
                query=query,
                relation_kinds=relation_kinds,
                certainties=certainties,
            )
        if operation == "uncertainty":
            return self.uncertainty(
                selectors=selectors,
                query=query,
                certainties=certainties,
            )
        if operation == "domain":
            return self.domain(query=query, selectors=selectors)
        return self.compare(selectors)
