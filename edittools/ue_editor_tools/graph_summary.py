from __future__ import annotations

"""Human-oriented projections of a ``ue_build_knowledge_graph`` document.

The build graph is deliberately lossless and therefore too large to read as a
single document.  This module adds small, deterministic projections on top of
that graph.  Every projected node, relation, and evidence record keeps its
original identifier so a UI can always expand a summary item back to the raw
graph.
"""

from collections import Counter, defaultdict, deque
from pathlib import Path
import json
import re
from typing import Any, Iterable


SCHEMA_VERSION = "ue_summarize_knowledge_graph"

# Relations that carry application meaning.  Large structural/resource edges
# remain in the source graph and are counted as folded edges in projections.
DISPLAY_RELATIONS = frozenset(
    {
        "APPLIES_TO",
        "BINDS",
        "CALLS",
        "CALLS_INTERFACE",
        "CANDIDATE_MATCH",
        "CONFIGURES",
        "DECLARES",
        "DECLARES_EVENT",
        "DECLARES_FUNCTION",
        "DECLARES_PROPERTY",
        "DECLARES_VARIABLE",
        "GENERATES_CLASS",
        "INHERITS",
        "INSTANCE_OF",
        "MAPS_TO",
        "OWNS_COMPONENT",
        "PRIMARY_ASSET_OF_TYPE",
        "PUBLISHES_EVENT",
        "READS",
        "REFERENCES_SYMBOL",
        "RESOLVES_TO",
        "SELECTS_CLASS",
        "SUBSCRIBES_EVENT",
        "UNSUBSCRIBES_EVENT",
        "USES_ROW_STRUCT",
        "USES_TYPE",
        "WRITES",
    }
)

SEMANTIC_RELATIONS = frozenset(
    {
        "CALLS",
        "CALLS_INTERFACE",
        "CANDIDATE_MATCH",
        "MAPS_TO",
        "PUBLISHES_EVENT",
        "READS",
        "REFERENCES_SYMBOL",
        "RESOLVES_TO",
        "SUBSCRIBES_EVENT",
        "UNSUBSCRIBES_EVENT",
        "WRITES",
    }
)

FOLDED_RELATIONS = frozenset(
    {
        "CONTAINS",
        "DATA_OR_EXEC_LINK",
        "DEPENDS_ON",
        "MANAGES",
        "REFERENCES",
        "SOFT_REFERENCES",
    }
)

RELATION_WEIGHTS: dict[str, float] = {
    "PUBLISHES_EVENT": 10.0,
    "SUBSCRIBES_EVENT": 10.0,
    "UNSUBSCRIBES_EVENT": 8.0,
    "CALLS": 8.0,
    "CALLS_INTERFACE": 7.0,
    "READS": 7.0,
    "WRITES": 7.0,
    "RESOLVES_TO": 8.0,
    "MAPS_TO": 8.0,
    "CANDIDATE_MATCH": 4.0,
    "REFERENCES_SYMBOL": 5.0,
    "SELECTS_CLASS": 6.0,
    "CONFIGURES": 5.0,
    "APPLIES_TO": 5.0,
    "GENERATES_CLASS": 4.0,
    "INHERITS": 4.0,
    "OWNS_COMPONENT": 4.0,
    "PRIMARY_ASSET_OF_TYPE": 4.0,
    "DECLARES": 3.0,
    "DECLARES_EVENT": 3.0,
    "DECLARES_FUNCTION": 3.0,
    "DECLARES_PROPERTY": 3.0,
    "DECLARES_VARIABLE": 3.0,
    "INSTANCE_OF": 2.0,
    "USES_ROW_STRUCT": 2.0,
    "USES_TYPE": 2.0,
    "CONTAINS": 0.2,
    "DATA_OR_EXEC_LINK": 0.3,
    "REFERENCES": 0.5,
    "SOFT_REFERENCES": 0.3,
    "DEPENDS_ON": 0.3,
    "MANAGES": 0.2,
}

NODE_WEIGHTS: dict[str, float] = {
    "primary_asset": 9.0,
    "primary_asset_type": 8.0,
    "cxx_class": 8.0,
    "cxx_struct": 8.0,
    "cxx_enum": 7.0,
    "cxx_function": 7.0,
    "payload_type": 7.0,
    "message_channel_expression": 7.0,
    "gameplay_tag": 6.0,
    "class": 6.0,
    "blueprint_function": 6.0,
    "blueprint_event": 6.0,
    "data_table": 5.0,
    "data_asset_property": 5.0,
    "level_actor": 5.0,
    "level_world": 5.0,
    "blueprint_variable": 4.0,
    "data_table_row": 4.0,
    # Symbols and Blueprint nodes are useful drill-down anchors, but their
    # occurrence count must not outrank C++ types, message channels, and
    # primary assets in the first screen.
    "blueprint_symbol": 2.0,
    "level_component": 3.0,
    "asset_class": 3.0,
    "blueprint_graph": 2.0,
    "asset": 1.5,
    "config_file": 1.5,
    "config_section": 1.0,
    "config_key": 1.0,
    "config_declaration": 1.0,
    "blueprint_node": 0.5,
    "object": 1.0,
}

PROPERTY_KEYS = (
    "asset",
    "asset_class",
    "blueprint",
    "class",
    "class_path",
    "generated_class",
    "id",
    "object_path",
    "package",
    "path",
    "qualified_name",
    "resolution",
    "row_count",
    "row_struct",
    "source",
    "source_kind",
    "symbol_id",
    "symbol_kind",
    "symbol_name",
    "tag",
    "type",
    "type_id",
)

DOMAIN_ORDER = (
    "health",
    "message",
    "ability",
    "equipment",
    "pawn",
    "weapon",
    "experience",
    "ui",
    "config",
    "infrastructure",
    "other",
)

DOMAIN_NAMES = {
    "health": "生命、伤害与死亡",
    "message": "Gameplay Message 与事件",
    "ability": "能力系统",
    "equipment": "装备与物品",
    "pawn": "Pawn、角色与输入",
    "weapon": "武器与射击",
    "experience": "Experience 与 GameFeature",
    "ui": "UI 与 HUD",
    "config": "配置与运行参数",
    "infrastructure": "引擎与基础设施",
    "other": "其他实体",
}

DOMAIN_TERMS: dict[str, tuple[str, ...]] = {
    "health": (
        "health",
        "damage",
        "death",
        "outofhealth",
        "elimination",
        "eliminated",
        "revive",
        "downed",
    ),
    "message": (
        "gameplaymessage",
        "message",
        "verb",
        "channel",
        "publish",
        "subscribe",
        "broadcast",
        "lyra.elimination",
    ),
    "ability": (
        "ability",
        "gameplayability",
        "abilitysystem",
        "abilityset",
        "activatable",
        "gameplayeffect",
        "ga_",
    ),
    "equipment": (
        "equipment",
        "equip",
        "inventory",
        "item",
        "pickup",
        "abilityset",
    ),
    "pawn": (
        "pawn",
        "character",
        "hero",
        "player",
        "camera",
        "input",
        "controller",
    ),
    "weapon": (
        "weapon",
        "ranged",
        "fire",
        "firearm",
        "shooter",
        "ammo",
        "projectile",
        "targeting",
    ),
    "experience": (
        "experience",
        "gamefeature",
        "actionset",
        "experience_definition",
        "experiencerule",
    ),
    "ui": (
        "widget",
        "hud",
        "indicator",
        "nameplate",
        "userwidget",
        "/ui/",
    ),
    "config": (
        ".ini",
        "config",
        "cvar",
        "deviceprofile",
        "defaultengine",
        "defaultgame",
    ),
    "infrastructure": (
        "/engine/",
        "/script/engine",
        "defaultanim",
        "mannequin",
        "compression",
        "plugin",
        "editorutility",
    ),
}

SLICE_RULES: dict[str, dict[str, Any]] = {
    "death": {
        "name": "死亡与淘汰",
        "terms": (
            "death",
            "elimination",
            "eliminated",
            "outofhealth",
            "gameplayevent.death",
            "lyra.elimination.message",
            "handleoutofhealth",
            "damage",
            "revive",
        ),
        "domains": ("health", "message", "ability"),
    },
    "equipment": {
        "name": "装备与能力授予",
        "terms": (
            "equipment",
            "equipmentmanager",
            "equipmentinstance",
            "inventorymanager",
            "inventorylist",
            "abilityset",
            "give_to_ability_system",
            "giveabilityset",
            "quickbar",
            "pickup",
        ),
        "domains": ("equipment", "ability", "pawn"),
    },
    "pawn": {
        "name": "Pawn 与角色配置",
        "terms": (
            "pawn",
            "pawndata",
            "character",
            "hero",
            "input",
            "camera",
        ),
        "domains": ("pawn", "ability", "equipment"),
    },
    "weapon": {
        "name": "武器与射击",
        "terms": (
            "weapon",
            "ranged",
            "fire",
            "projectile",
            "ammo",
            "targeting",
            "impact",
        ),
        "domains": ("weapon", "ability", "message"),
    },
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        return " ".join(f"{_text(k)} {_text(v)}" for k, v in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(_text(item) for item in value)
    return str(value)


def _fold_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9_./:-]+", "", _text(value).casefold())


def _node_text(node: dict[str, Any]) -> str:
    properties = node.get("properties")
    fields: list[Any] = [node.get("name"), node.get("kind"), node.get("canonical_key")]
    if isinstance(properties, dict):
        # Selected properties are enough to classify an entity and avoid
        # pulling Blueprint pin/default-value payloads into every summary.
        fields.extend(properties.get(key, "") for key in PROPERTY_KEYS)
    return _fold_text(" ".join(_text(item) for item in fields))


def _label(node: dict[str, Any]) -> str:
    properties = node.get("properties") if isinstance(node.get("properties"), dict) else {}
    kind = str(node.get("kind") or "")
    name = str(node.get("name") or "").strip()
    # The raw graph keeps canonical object paths separately.  For a human
    # projection the short entity name is easier to scan; compact_node still
    # includes canonical_key and whitelisted path properties for navigation.
    short_name_kinds = {
        "asset",
        "asset_class",
        "blueprint_event",
        "blueprint_function",
        "blueprint_graph",
        "blueprint_node",
        "blueprint_symbol",
        "blueprint_variable",
        "class",
        "config_declaration",
        "config_key",
        "config_section",
        "cxx_class",
        "cxx_enum",
        "cxx_function",
        "cxx_struct",
        "data_asset_property",
        "data_table",
        "data_table_row",
        "gameplay_tag",
        "level_actor",
        "level_component",
        "level_world",
        "message_channel_expression",
        "object",
        "payload_type",
        "primary_asset",
        "primary_asset_type",
    }
    if name and kind in short_name_kinds:
        return name
    for key in ("qualified_name", "object_path", "path", "package", "tag", "symbol_name"):
        value = properties.get(key)
        if value not in (None, ""):
            return str(value)
    value = node.get("name") or node.get("canonical_key") or node.get("node_id")
    return str(value)


def _node_confidence(node: dict[str, Any]) -> str:
    properties = node.get("properties") if isinstance(node.get("properties"), dict) else {}
    resolution = str(properties.get("resolution") or "").casefold()
    if resolution in {"name_only", "candidate"}:
        return "name_only"
    if resolution in {"unresolved", "missing"}:
        return "unresolved"
    if resolution == "exact":
        return "exact"
    return "observed"


def _domains(node: dict[str, Any]) -> list[str]:
    text = _node_text(node)
    matches = [
        domain
        for domain in DOMAIN_ORDER
        if domain != "other" and any(_fold_text(term) in text for term in DOMAIN_TERMS[domain])
    ]
    if not matches:
        return ["other"]
    # Health/message tags are more useful as their own slice than as a generic
    # ability or weapon dependency.  Keep all matches for cross-domain views.
    return matches


def _primary_domain(node: dict[str, Any]) -> str:
    matches = _domains(node)
    return matches[0] if matches else "other"


def _safe_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_json_value(item) for item in value[:10]]
    if isinstance(value, dict):
        return {
            str(key): _safe_json_value(item)
            for key, item in list(value.items())[:20]
            if item not in (None, "", [], {})
        }
    return str(value)


class GraphSummary:
    """Build deterministic human projections for a raw knowledge graph."""

    def __init__(self, document: dict[str, Any], *, max_nodes: int = 120, max_relations: int = 120) -> None:
        graph = document.get("graph")
        if not isinstance(graph, dict):
            raise ValueError("Input graph must be an object")
        for field in ("nodes", "relations", "evidence"):
            if field in graph and not isinstance(graph.get(field), list):
                raise ValueError(f"Graph field {field} must be an array")
        self.document = document
        self.graph = graph
        self.project = str(graph.get("project") or "unknown-project")
        self.max_nodes = max(1, int(max_nodes))
        self.max_relations = max(1, int(max_relations))
        self.nodes: dict[str, dict[str, Any]] = {
            str(item.get("node_id")): item
            for item in graph.get("nodes", [])
            if isinstance(item, dict) and item.get("node_id")
        }
        self.relations: dict[str, dict[str, Any]] = {
            str(item.get("relation_id")): item
            for item in graph.get("relations", [])
            if isinstance(item, dict) and item.get("relation_id")
        }
        self.evidence: dict[str, dict[str, Any]] = {
            str(item.get("evidence_id")): item
            for item in graph.get("evidence", [])
            if isinstance(item, dict) and item.get("evidence_id")
        }
        self.evidence_by_relation: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in self.evidence.values():
            self.evidence_by_relation[str(item.get("relation_id"))].append(item)
        for records in self.evidence_by_relation.values():
            records.sort(key=lambda item: str(item.get("evidence_id")))
        self.relations_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for relation in self.relations.values():
            self.relations_by_node[str(relation.get("source_id"))].append(relation)
            self.relations_by_node[str(relation.get("target_id"))].append(relation)
        for records in self.relations_by_node.values():
            records.sort(key=lambda item: str(item.get("relation_id")))
        self._importance_cache: dict[str, float] = {}

    def _relation_weight(self, relation: dict[str, Any]) -> float:
        kind = str(relation.get("kind") or "")
        weight = RELATION_WEIGHTS.get(kind, 0.1)
        certainty = str(relation.get("certainty") or "confirmed").casefold()
        if certainty in {"unresolved", "name_only"}:
            weight *= 0.45
        elif certainty == "candidate":
            weight *= 0.65
        return weight

    def _importance(self, node_id: str) -> float:
        if node_id in self._importance_cache:
            return self._importance_cache[node_id]
        node = self.nodes.get(node_id, {})
        score = NODE_WEIGHTS.get(str(node.get("kind") or ""), 1.0)
        text = _node_text(node)
        domain_matches = _domains(node)
        score += min(4.0, 0.7 * len(domain_matches))
        if any(term in text for term in ("/engine/", "/script/engine", "defaultanim", "mannequin", "compression")):
            score *= 0.2
        # Only semantic/structural edges contribute to importance.  Asset
        # registry hubs otherwise dominate simply because they have thousands
        # of MANAGES or REFERENCES edges.
        semantic_bonus = 0.0
        structural_bonus = 0.0
        for relation in self.relations_by_node.get(node_id, []):
            if str(relation.get("kind")) in SEMANTIC_RELATIONS:
                semantic_bonus += self._relation_weight(relation) * 0.12
            elif str(relation.get("kind")) in DISPLAY_RELATIONS:
                structural_bonus += self._relation_weight(relation) * 0.04
        score += min(10.0, semantic_bonus) + min(2.0, structural_bonus)
        self._importance_cache[node_id] = round(score, 3)
        return self._importance_cache[node_id]

    def _compact_properties(self, node: dict[str, Any]) -> dict[str, Any]:
        properties = node.get("properties")
        if not isinstance(properties, dict):
            return {}
        result: dict[str, Any] = {}
        for key in PROPERTY_KEYS:
            if key in properties and properties[key] not in (None, "", [], {}):
                result[key] = _safe_json_value(properties[key])
        return result

    def compact_node(self, node_id: str) -> dict[str, Any]:
        node = self.nodes[node_id]
        return {
            "node_id": node_id,
            "kind": str(node.get("kind") or ""),
            "name": str(node.get("name") or ""),
            "label": _label(node),
            "canonical_key": str(node.get("canonical_key") or ""),
            "domains": _domains(node),
            "confidence": _node_confidence(node),
            "importance": self._importance(node_id),
            "properties": self._compact_properties(node),
        }

    def compact_relation(self, relation: dict[str, Any]) -> dict[str, Any]:
        relation_id = str(relation.get("relation_id"))
        source_id = str(relation.get("source_id"))
        target_id = str(relation.get("target_id"))
        evidence = self.evidence_by_relation.get(relation_id, [])
        source = self.nodes.get(source_id, {})
        target = self.nodes.get(target_id, {})
        return {
            "relation_id": relation_id,
            "source_id": source_id,
            "source_name": _label(source) if source else source_id,
            "kind": str(relation.get("kind") or ""),
            "target_id": target_id,
            "target_name": _label(target) if target else target_id,
            "certainty": str(relation.get("certainty") or "confirmed"),
            "properties": _safe_json_value(relation.get("properties") or {}),
            "evidence_ids": [str(item.get("evidence_id")) for item in evidence],
            "evidence_producers": sorted(
                {str(item.get("producer")) for item in evidence if item.get("producer")}
            ),
            "evidence_count": len(evidence),
        }

    def _sorted_node_ids(self, node_ids: Iterable[str]) -> list[str]:
        return sorted(
            {node_id for node_id in node_ids if node_id in self.nodes},
            key=lambda node_id: (-self._importance(node_id), _label(self.nodes[node_id]).casefold(), node_id),
        )

    def _sorted_relations(self, relations: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            list(relations),
            key=lambda relation: (
                -self._relation_weight(relation),
                str(relation.get("kind") or ""),
                str(relation.get("relation_id") or ""),
            ),
        )

    def _relation_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(str(item.get("kind") or "") for item in self.relations.values()).items()))

    def _node_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(str(item.get("kind") or "") for item in self.nodes.values()).items()))

    def _confidence_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(str(item.get("certainty") or "confirmed") for item in self.relations.values()).items()))

    def _visible_relations(self, node_ids: set[str] | None = None) -> list[dict[str, Any]]:
        result = []
        for relation in self.relations.values():
            if str(relation.get("kind")) not in DISPLAY_RELATIONS:
                continue
            if node_ids is not None and not {
                str(relation.get("source_id")),
                str(relation.get("target_id")),
            } <= node_ids:
                continue
            result.append(relation)
        return self._sorted_relations(result)

    def _folded_counts(self, *, node_ids: set[str] | None = None) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for relation in self.relations.values():
            if str(relation.get("kind")) in DISPLAY_RELATIONS:
                continue
            if node_ids is not None and not {
                str(relation.get("source_id")),
                str(relation.get("target_id")),
            } <= node_ids:
                continue
            counts[str(relation.get("kind") or "")] += 1
        return dict(sorted(counts.items()))

    def _selected_node_projection(self, node_ids: Iterable[str], *, limit: int | None = None) -> list[dict[str, Any]]:
        selected = self._sorted_node_ids(node_ids)
        if limit is not None:
            selected = selected[: max(0, limit)]
        return [self.compact_node(node_id) for node_id in selected]

    def overview(self) -> dict[str, Any]:
        visible = self._visible_relations()
        featured_ids: set[str] = set()

        def relation_priority(relation: dict[str, Any]) -> tuple[float, str]:
            source = self.nodes.get(str(relation.get("source_id")), {})
            target = self.nodes.get(str(relation.get("target_id")), {})
            endpoint_kinds = {str(source.get("kind")), str(target.get("kind"))}
            endpoint_domains = set(_domains(source)) | set(_domains(target))
            score = self._relation_weight(relation) * 10.0
            if str(relation.get("kind")) in SEMANTIC_RELATIONS:
                score += 20.0
            if endpoint_kinds - {"blueprint_symbol", "blueprint_node", "asset", "blueprint_graph"}:
                score += 12.0
            if endpoint_domains - {"other", "infrastructure"}:
                score += 8.0
            score += self._importance(str(relation.get("source_id")))
            score += self._importance(str(relation.get("target_id")))
            return (-score, str(relation.get("relation_id") or ""))

        # Select complete high-signal edges first, so the overview always has
        # readable relationships instead of a list of disconnected hubs.
        relation_candidates = sorted(
            [item for item in visible if str(item.get("kind")) in SEMANTIC_RELATIONS],
            key=relation_priority,
        )
        for relation in relation_candidates:
            endpoints = {
                str(relation.get("source_id")),
                str(relation.get("target_id")),
            }
            if not endpoints <= set(self.nodes):
                continue
            new_count = len(endpoints - featured_ids)
            if len(featured_ids) + new_count > self.max_nodes:
                continue
            featured_ids.update(endpoints)
            if len(featured_ids) >= self.max_nodes:
                break
        if len(featured_ids) < self.max_nodes:
            featured_ids.update(
                self._sorted_node_ids(self.nodes.keys())[: self.max_nodes - len(featured_ids)]
            )
        featured_ids = set(self._sorted_node_ids(featured_ids)[: self.max_nodes])
        feature_relations = [
            relation
            for relation in visible
            if {
                str(relation.get("source_id")),
                str(relation.get("target_id")),
            }
            <= featured_ids
        ]
        feature_relations = self._sorted_relations(feature_relations)[: self.max_relations]
        selected_evidence = sorted(
            {
                evidence_id
                for relation in feature_relations
                for evidence_id in (
                    str(item.get("evidence_id"))
                    for item in self.evidence_by_relation.get(str(relation.get("relation_id")), [])
                )
            }
        )
        domain_counts: Counter[str] = Counter()
        node_confidence_counts: Counter[str] = Counter()
        for node in self.nodes.values():
            domain_counts[_primary_domain(node)] += 1
            node_confidence_counts[_node_confidence(node)] += 1
        return {
            "project": self.project,
            "source_schema": str(self.document.get("schema_version") or ""),
            "raw_counts": {
                "nodes": len(self.nodes),
                "relations": len(self.relations),
                "evidence": len(self.evidence),
            },
            "node_counts": self._node_counts(),
            "relation_counts": self._relation_counts(),
            "relation_confidence_counts": self._confidence_counts(),
            "node_confidence_counts": dict(sorted(node_confidence_counts.items())),
            "domain_counts": dict(sorted(domain_counts.items())),
            "coverage": {
                "featured_nodes": len(featured_ids),
                "featured_relations": len(feature_relations),
                "featured_evidence": len(selected_evidence),
                "folded_relations": len(self.relations) - len(feature_relations),
                "folded_relation_counts": self._folded_counts(),
            },
            "featured_nodes": self._selected_node_projection(featured_ids),
            "featured_relations": [self.compact_relation(item) for item in feature_relations],
            "evidence_ids": selected_evidence,
            "guidance": [
                "先按业务系统或切片阅读；蓝图节点、Pin 连线和资源依赖默认折叠。",
                "每个摘要实体都保留 node_id；展开详情时回查原始 knowledge-graph.json。",
                "name_only、candidate、unresolved 只表示当前证据边界，不等同于精确绑定。",
            ],
        }

    def systems(self) -> dict[str, Any]:
        by_domain: dict[str, list[str]] = defaultdict(list)
        for node_id, node in self.nodes.items():
            by_domain[_primary_domain(node)].append(node_id)
        domains: list[dict[str, Any]] = []
        for domain in DOMAIN_ORDER:
            node_ids = by_domain.get(domain, [])
            if not node_ids:
                continue
            selected = set(self._sorted_node_ids(node_ids)[: min(30, self.max_nodes)])
            relations = self._visible_relations(selected)
            relation_counts = Counter(str(item.get("kind") or "") for item in relations)
            domains.append(
                {
                    "system_id": domain,
                    "name": DOMAIN_NAMES[domain],
                    "node_count": len(node_ids),
                    "top_nodes": self._selected_node_projection(node_ids, limit=min(12, self.max_nodes)),
                    "relation_counts": dict(sorted(relation_counts.items())),
                    "key_relations": [
                        self.compact_relation(item) for item in relations[: min(24, self.max_relations)]
                    ],
                    "folded_relation_counts": self._folded_counts(node_ids=selected),
                }
            )
        cross: Counter[tuple[str, str, str]] = Counter()
        cross_relation_ids: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        for relation in self._visible_relations():
            source = self.nodes.get(str(relation.get("source_id")))
            target = self.nodes.get(str(relation.get("target_id")))
            if not source or not target:
                continue
            source_domain, target_domain = _primary_domain(source), _primary_domain(target)
            if source_domain == target_domain:
                continue
            key = (source_domain, str(relation.get("kind") or ""), target_domain)
            cross[key] += 1
            cross_relation_ids[key].append(str(relation.get("relation_id")))
        cross_edges = [
            {
                "source_system": key[0],
                "relation_kind": key[1],
                "target_system": key[2],
                "count": count,
                "relation_ids": sorted(cross_relation_ids[key])[:50],
            }
            for key, count in sorted(cross.items(), key=lambda item: (-item[1], item[0]))[:60]
        ]
        return {
            "project": self.project,
            "systems": domains,
            "cross_system_relations": cross_edges,
            "folded_relation_kinds": self._folded_counts(),
        }

    def _seed_ids(self, rule: dict[str, Any]) -> list[str]:
        terms = tuple(_fold_text(term) for term in rule.get("terms", ()))
        domains = set(str(item) for item in rule.get("domains", ()))
        scored: list[tuple[float, str]] = []
        for node_id, node in self.nodes.items():
            text = _node_text(node)
            matched_terms = sum(1 for term in terms if term and term in text)
            matched_domain = bool(domains.intersection(_domains(node)))
            # Slice rules are intentionally term-driven.  Domain membership
            # is used to rank a matching seed, but by itself would pull broad
            # UI/animation infrastructure into the equipment and pawn views.
            if matched_terms == 0:
                continue
            score = self._importance(node_id) + matched_terms * 8.0 + (3.0 if matched_domain else 0.0)
            scored.append((score, node_id))
        scored.sort(key=lambda item: (-item[0], _label(self.nodes[item[1]]).casefold(), item[1]))
        return [node_id for _, node_id in scored[: min(24, self.max_nodes)]]

    def _slice_neighborhood(self, seed_ids: list[str]) -> tuple[set[str], list[dict[str, Any]]]:
        selected: set[str] = set(seed_ids[: self.max_nodes])
        queue: deque[tuple[float, str, int]] = deque((0.0, node_id, 0) for node_id in seed_ids)
        candidate_edges: list[tuple[float, dict[str, Any], str]] = []
        visited: set[tuple[str, int]] = set()
        while queue and len(selected) < self.max_nodes:
            _, current, depth = queue.popleft()
            if (current, depth) in visited or depth >= 2:
                continue
            visited.add((current, depth))
            for relation in self.relations_by_node.get(current, []):
                kind = str(relation.get("kind") or "")
                if kind not in DISPLAY_RELATIONS and kind not in {"REFERENCES", "SOFT_REFERENCES", "SELECTS_CLASS", "CONFIGURES"}:
                    continue
                source_id, target_id = str(relation.get("source_id")), str(relation.get("target_id"))
                neighbor = target_id if source_id == current else source_id
                if neighbor not in self.nodes:
                    continue
                relation_score = self._relation_weight(relation)
                if kind in {"REFERENCES", "SOFT_REFERENCES"}:
                    relation_score *= 0.25
                if neighbor not in selected:
                    candidate_edges.append((relation_score + self._importance(neighbor) * 0.1, relation, neighbor))
                if kind in DISPLAY_RELATIONS and depth + 1 < 2:
                    queue.append((relation_score, neighbor, depth + 1))
            # Keep processing the strongest frontier first on the next round.
            if len(candidate_edges) > 2000:
                candidate_edges.sort(key=lambda item: (-item[0], str(item[1].get("relation_id"))))
                del candidate_edges[1000:]
        candidate_edges.sort(key=lambda item: (-item[0], str(item[1].get("relation_id"))))
        for _, relation, neighbor in candidate_edges:
            if len(selected) >= self.max_nodes:
                break
            selected.add(neighbor)
        relations = [
            relation
            for relation in self._visible_relations(selected)
            if str(relation.get("source_id")) in selected and str(relation.get("target_id")) in selected
        ]
        # Include a small number of useful cross-asset references when they
        # connect selected business entities; never expose all registry edges.
        extra = [
            relation
            for relation in self.relations.values()
            if str(relation.get("kind")) in {"REFERENCES", "SOFT_REFERENCES"}
            and {str(relation.get("source_id")), str(relation.get("target_id"))} <= selected
        ]
        relations.extend(extra[: max(0, self.max_relations - len(relations))])
        relations = self._sorted_relations({str(item.get("relation_id")): item for item in relations}.values())[: self.max_relations]
        return selected, relations

    def slice(self, slice_id: str) -> dict[str, Any]:
        rule = SLICE_RULES[slice_id]
        seed_ids = self._seed_ids(rule)
        selected, relations = self._slice_neighborhood(seed_ids)
        selected = set(self._sorted_node_ids(selected)[: self.max_nodes])
        relations = [
            relation
            for relation in relations
            if {str(relation.get("source_id")), str(relation.get("target_id"))} <= selected
        ][: self.max_relations]
        evidence_ids = sorted(
            {
                str(item.get("evidence_id"))
                for relation in relations
                for item in self.evidence_by_relation.get(str(relation.get("relation_id")), [])
            }
        )
        uncertain_nodes = [
            node_id
            for node_id in self._sorted_node_ids(selected)
            if _node_confidence(self.nodes[node_id]) in {"name_only", "unresolved"}
        ]
        uncertain_relations = [
            str(relation.get("relation_id"))
            for relation in relations
            if str(relation.get("certainty")) in {"candidate", "unresolved"}
        ]
        return {
            "slice_id": slice_id,
            "name": str(rule["name"]),
            "project": self.project,
            "seed_terms": list(rule.get("terms", ())),
            "seed_node_ids": seed_ids,
            "node_ids": self._sorted_node_ids(selected),
            "relation_ids": [str(item.get("relation_id")) for item in relations],
            "evidence_ids": evidence_ids,
            "nodes": self._selected_node_projection(selected),
            "relations": [self.compact_relation(item) for item in relations],
            "uncertainty": {
                "node_ids": uncertain_nodes,
                "relation_ids": uncertain_relations,
                "candidate_match_count": sum(
                    1 for relation in relations if str(relation.get("kind")) == "CANDIDATE_MATCH"
                ),
            },
            "folded_relation_counts": self._folded_counts(node_ids=selected),
            "limits": [
                "这是按名称、类型和高价值关系抽取的一跳到两跳视图，不是完整可达性证明。",
                "资源注册表依赖和 Blueprint Pin 级连线保留在原始图中，并在此处折叠计数。",
            ],
        }

    def entity(self, identifier: str) -> dict[str, Any]:
        value = str(identifier)
        node_id = value if value in self.nodes else ""
        if not node_id:
            candidates = [
                node_id
                for node_id, node in self.nodes.items()
                if value.casefold() in {str(node.get("name", "")).casefold(), _label(node).casefold()}
            ]
            if len(candidates) == 1:
                node_id = candidates[0]
            elif candidates:
                candidates.sort(key=lambda item: (-self._importance(item), item))
                node_id = candidates[0]
        if not node_id:
            raise KeyError(f"Entity not found: {identifier}")
        relations = self._sorted_relations(
            relation
            for relation in self.relations_by_node.get(node_id, [])
            if str(relation.get("kind")) in DISPLAY_RELATIONS
            or str(relation.get("kind")) in {"REFERENCES", "SOFT_REFERENCES"}
        )[: self.max_relations]
        selected = {node_id}
        selected.update(
            str(item.get("target_id")) if str(item.get("source_id")) == node_id else str(item.get("source_id"))
            for item in relations
        )
        selected = {item for item in selected if item in self.nodes}
        return {
            "project": self.project,
            "entity": self.compact_node(node_id),
            "node_ids": self._sorted_node_ids(selected),
            "relation_ids": [str(item.get("relation_id")) for item in relations],
            "evidence_ids": sorted(
                {
                    str(evidence.get("evidence_id"))
                    for relation in relations
                    for evidence in self.evidence_by_relation.get(str(relation.get("relation_id")), [])
                }
            ),
            "neighbors": self._selected_node_projection(selected),
            "relations": [self.compact_relation(item) for item in relations],
        }


def summarize_graph(
    document: dict[str, Any],
    *,
    view: str = "all",
    slice_ids: Iterable[str] = (),
    entity_ids: Iterable[str] = (),
    max_nodes: int = 120,
    max_relations: int = 120,
) -> dict[str, Any]:
    builder = GraphSummary(document, max_nodes=max_nodes, max_relations=max_relations)
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_schema": str(document.get("schema_version") or ""),
        "project": builder.project,
        "view": view,
    }
    if view in {"overview", "all"}:
        result["overview"] = builder.overview()
    if view in {"systems", "all"}:
        result["systems"] = builder.systems()
    if view in {"slice", "all"}:
        requested_slices = list(slice_ids)
        selected_slices = requested_slices if requested_slices else list(SLICE_RULES)
        result["slices"] = {slice_id: builder.slice(slice_id) for slice_id in selected_slices}
    if view == "entity":
        result["entities"] = {identifier: builder.entity(identifier) for identifier in entity_ids}
    elif entity_ids:
        result["entities"] = {identifier: builder.entity(identifier) for identifier in entity_ids}
    result["source_graph"] = {
        "schema_version": str(document.get("schema_version") or ""),
        "project": builder.project,
        "counts": {
            "nodes": len(builder.nodes),
            "relations": len(builder.relations),
            "evidence": len(builder.evidence),
        },
    }
    return result


def render_markdown(summary: dict[str, Any]) -> str:
    """Render a compact Markdown view without copying raw Blueprint payloads."""

    lines = [
        "# UE 工程知识摘要",
        "",
        f"- 工程：`{summary.get('project', '')}`",
        f"- 视图：`{summary.get('view', '')}`",
        "",
    ]
    overview = summary.get("overview")
    if isinstance(overview, dict):
        counts = overview.get("raw_counts", {})
        coverage = overview.get("coverage", {})
        lines.extend(
            [
                "## 工程规模",
                "",
                f"节点 {counts.get('nodes', 0)}，关系 {counts.get('relations', 0)}，证据 {counts.get('evidence', 0)}。",
                f"摘要展示 {coverage.get('featured_nodes', 0)} 个节点和 {coverage.get('featured_relations', 0)} 条关系，其余关系按类型折叠。",
                "",
                "## 高价值实体",
                "",
                "| 类型 | 名称 | 领域 | 可信度 | 重要度 |",
                "| --- | --- | --- | --- | ---: |",
            ]
        )
        for node in overview.get("featured_nodes", [])[:40]:
            lines.append(
                f"| `{node.get('kind', '')}` | `{node.get('label', '')}` | {', '.join(node.get('domains', []))} | {node.get('confidence', '')} | {node.get('importance', 0)} |"
            )
        lines.extend(["", "## 关键关系", ""])
        for relation in overview.get("featured_relations", [])[:50]:
            lines.append(
                f"- `{relation.get('source_name', relation.get('source_id'))}` **{relation.get('kind')}** `{relation.get('target_name', relation.get('target_id'))}`（{relation.get('certainty')}，证据 {relation.get('evidence_count', 0)} 条）"
            )
        lines.append("")
    systems = summary.get("systems")
    if isinstance(systems, dict):
        lines.extend(["## 业务系统", ""])
        for system in systems.get("systems", []):
            lines.append(
                f"### {system.get('name')}（{system.get('node_count', 0)} 个实体）"
            )
            for node in system.get("top_nodes", [])[:8]:
                lines.append(f"- `{node.get('label')}`（{node.get('kind')}）")
            lines.append("")
    slices = summary.get("slices")
    single_slice = summary.get("slice")
    if isinstance(single_slice, dict):
        slices = {str(single_slice.get("slice_id") or "slice"): single_slice}
    if isinstance(slices, dict):
        for slice_id, item in slices.items():
            lines.extend(
                [
                    f"## 切片：{item.get('name', slice_id)}",
                    "",
                    f"种子 {len(item.get('seed_node_ids', []))} 个，节点 {len(item.get('node_ids', []))} 个，关键关系 {len(item.get('relation_ids', []))} 条，证据 {len(item.get('evidence_ids', []))} 条。",
                    "",
                ]
            )
            for relation in item.get("relations", [])[:35]:
                lines.append(
                    f"- `{relation.get('source_name')}` **{relation.get('kind')}** `{relation.get('target_name')}`（{relation.get('certainty')}）"
                )
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_projection_files(summary: dict[str, Any], output_dir: str | Path) -> list[str]:
    """Write JSON/Markdown projections and return paths relative to output_dir."""

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    def write_json_file(relative: str, value: dict[str, Any]) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        paths.append(relative.replace("\\", "/"))

    def write_md_file(relative: str, value: dict[str, Any]) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(value), encoding="utf-8")
        paths.append(relative.replace("\\", "/"))

    if isinstance(summary.get("overview"), dict):
        overview_payload = {
            "schema_version": SCHEMA_VERSION,
            "source_schema": summary.get("source_schema"),
            "project": summary.get("project"),
            "view": "overview",
            "overview": summary["overview"],
            "source_graph": summary.get("source_graph"),
        }
        write_json_file("overview.json", overview_payload)
        write_md_file("overview.md", overview_payload)
    if isinstance(summary.get("systems"), dict):
        systems_payload = {
            "schema_version": SCHEMA_VERSION,
            "source_schema": summary.get("source_schema"),
            "project": summary.get("project"),
            "view": "systems",
            "systems": summary["systems"],
            "source_graph": summary.get("source_graph"),
        }
        write_json_file("systems.json", systems_payload)
        write_md_file("systems.md", systems_payload)
    slices = summary.get("slices")
    if isinstance(slices, dict):
        for slice_id, item in sorted(slices.items()):
            payload = {
                "schema_version": SCHEMA_VERSION,
                "source_schema": summary.get("source_schema"),
                "project": summary.get("project"),
                "view": "slice",
                "slice": item,
                "source_graph": summary.get("source_graph"),
            }
            write_json_file(f"slices/{slice_id}.json", payload)
            write_md_file(f"slices/{slice_id}.md", payload)
    single_entity = summary.get("entity")
    entities = summary.get("entities")
    if isinstance(single_entity, dict):
        entity_name = str(single_entity.get("entity", {}).get("name") or "entity")
        entities = {entity_name: single_entity}
    if isinstance(entities, dict):
        for index, (identifier, item) in enumerate(sorted(entities.items()), start=1):
            label = str(item.get("entity", {}).get("name") or identifier)
            safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_") or f"entity_{index}"
            payload = {
                "schema_version": SCHEMA_VERSION,
                "source_schema": summary.get("source_schema"),
                "project": summary.get("project"),
                "view": "entity",
                "entity": item,
                "source_graph": summary.get("source_graph"),
            }
            write_json_file(f"entities/{safe}.json", payload)
            write_md_file(f"entities/{safe}.md", payload)
    return sorted(paths)
