from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from .graph_export import export_message_graph
from .value_refs import normalize_object_path


def stable_id(kind: str, *parts: Any) -> str:
    payload = json.dumps(
        parts, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return f"{kind}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]}"


def package_from_object_path(value: str) -> str:
    path = normalize_object_path(value)
    if "." in path:
        return path.split(".", 1)[0]
    return path


class KnowledgeGraph:
    def __init__(self, project: str) -> None:
        self.project = project.replace("\\", "/")
        self.nodes: dict[str, dict[str, Any]] = {}
        self.node_by_key: dict[tuple[str, str], str] = {}
        self.relations: dict[str, dict[str, Any]] = {}
        self.evidence: dict[str, dict[str, Any]] = {}

    def add_node(
        self, kind: str, key: str, name: str, properties: dict[str, Any] | None = None
    ) -> str:
        normalized_key = key.replace("\\", "/")
        lookup = (kind, normalized_key)
        node_id = self.node_by_key.get(lookup)
        if node_id is None:
            canonical = f"{self.project}|{kind}|{normalized_key}"
            node_id = stable_id("node", canonical)
            self.node_by_key[lookup] = node_id
            self.nodes[node_id] = {
                "node_id": node_id,
                "kind": kind,
                "name": name,
                "canonical_key": canonical,
                "properties": properties or {},
            }
        elif properties:
            target = self.nodes[node_id]["properties"]
            for field, value in properties.items():
                if value not in (None, "", [], {}):
                    target[field] = value
        return node_id

    def add_relation(
        self,
        source_id: str,
        kind: str,
        target_id: str,
        *,
        certainty: str = "confirmed",
        properties: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
        producer: str,
    ) -> str:
        relation_id = stable_id("relation", source_id, kind, target_id)
        self.relations.setdefault(
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
        detail = evidence or {}
        evidence_id = stable_id("evidence", relation_id, producer, detail)
        self.evidence[evidence_id] = {
            "evidence_id": evidence_id,
            "relation_id": relation_id,
            "producer": producer,
            **detail,
        }
        return relation_id

    def document(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "nodes": sorted(self.nodes.values(), key=lambda item: str(item["node_id"])),
            "relations": sorted(
                self.relations.values(), key=lambda item: str(item["relation_id"])
            ),
            "evidence": sorted(
                self.evidence.values(), key=lambda item: str(item["evidence_id"])
            ),
            "counts": {
                "nodes": len(self.nodes),
                "relations": len(self.relations),
                "evidence": len(self.evidence),
            },
        }


def _target_node(graph: KnowledgeGraph, kind: str, target: str) -> str:
    normalized = normalize_object_path(target)
    if kind == "gameplay_tag":
        return graph.add_node(
            "gameplay_tag", normalized, normalized, {"tag": normalized}
        )
    if kind == "primary_asset":
        return graph.add_node(
            "primary_asset",
            normalized,
            normalized.split(":", 1)[-1],
            {"id": normalized},
        )
    if kind == "object":
        return graph.add_node(
            "object",
            normalized,
            normalized.rsplit(":", 1)[-1],
            {"path": normalized},
        )
    if kind == "class":
        return graph.add_node(
            "class", normalized, normalized.rsplit(".", 1)[-1], {"path": normalized}
        )
    package = package_from_object_path(normalized)
    return graph.add_node(
        "asset", package, package.rsplit("/", 1)[-1], {"package": package}
    )


def _asset_graph(
    graph: KnowledgeGraph, document: dict[str, Any], producer: str
) -> None:
    relation_kinds = {
        "hard_package": "DEPENDS_ON",
        "soft_package": "SOFT_REFERENCES",
        "hard_manage": "MANAGES",
        "soft_manage": "MANAGES",
        "searchable_name": "REFERENCES",
    }
    for row in document.get("packages", []):
        package = str(row["package"])
        asset_id = graph.add_node(
            "asset",
            package,
            package.rsplit("/", 1)[-1],
            {"package": package, "root": row.get("root")},
        )
        for asset in row.get("assets", []):
            class_path = str(asset.get("class", ""))
            if class_path:
                class_id = graph.add_node(
                    "asset_class",
                    class_path,
                    class_path.rsplit(".", 1)[-1],
                    {"path": class_path},
                )
                graph.add_relation(
                    asset_id,
                    "INSTANCE_OF",
                    class_id,
                    producer=producer,
                    evidence={"asset": asset.get("object_path")},
                )
            tags = asset.get("registry_tags", {})
            generated = tags.get("GeneratedClass")
            if generated:
                generated_path = normalize_object_path(str(generated))
                generated_id = graph.add_node(
                    "class",
                    generated_path,
                    generated_path.rsplit(".", 1)[-1],
                    {"path": generated_path},
                )
                graph.add_relation(
                    asset_id,
                    "GENERATES_CLASS",
                    generated_id,
                    producer=producer,
                    evidence={
                        "asset": asset.get("object_path"),
                        "registry_tag": "GeneratedClass",
                    },
                )
                parent = tags.get("ParentClass") or tags.get("NativeParentClass")
                if parent:
                    parent_path = normalize_object_path(str(parent))
                    parent_id = graph.add_node(
                        "class",
                        parent_path,
                        parent_path.rsplit(".", 1)[-1],
                        {"path": parent_path},
                    )
                    graph.add_relation(
                        generated_id,
                        "INHERITS",
                        parent_id,
                        producer=producer,
                        evidence={
                            "asset": asset.get("object_path"),
                            "registry_tag": "ParentClass",
                        },
                    )
        for dependency_kind, targets in row.get("dependencies", {}).items():
            relation_kind = relation_kinds.get(str(dependency_kind), "REFERENCES")
            for target in targets:
                target_package = str(target)
                target_id = graph.add_node(
                    "asset",
                    target_package,
                    target_package.rsplit("/", 1)[-1],
                    {"package": target_package},
                )
                graph.add_relation(
                    asset_id,
                    relation_kind,
                    target_id,
                    producer=producer,
                    properties={"dependency_kind": dependency_kind},
                    evidence={"asset": package},
                )


def _blueprints(graph: KnowledgeGraph, document: dict[str, Any], producer: str) -> None:
    def symbol_relation(node: dict[str, Any], symbol: dict[str, Any]) -> str:
        kind = str(symbol.get("symbol_kind", "")).casefold()
        node_class = " ".join(
            str(node.get(field, ""))
            for field in ("class", "class_path", "type_id", "title")
        ).casefold()
        if kind in {"variable", "property"}:
            return "WRITES" if any(
                marker in node_class
                for marker in ("setvariable", "assign", "setmember", "setfield")
            ) else "READS"
        if kind in {"event", "delegate"}:
            return "BINDS" if "bind" in node_class else "CALLS"
        if kind == "interface":
            return "CALLS_INTERFACE"
        return "CALLS"

    for item in document.get("blueprints", []):
        package = str(item["asset"])
        asset_id = graph.add_node(
            "asset",
            package,
            package.rsplit("/", 1)[-1],
            {"package": package, "asset_id": item.get("asset_id")},
        )
        generated = item.get("generated_class")
        class_id = asset_id
        if generated:
            generated = normalize_object_path(str(generated))
            class_id = graph.add_node(
                "class",
                generated,
                generated.rsplit(".", 1)[-1],
                {"path": generated, "blueprint": package},
            )
            graph.add_relation(
                asset_id,
                "GENERATES_CLASS",
                class_id,
                producer=producer,
                evidence={"asset": item.get("asset_object_path")},
            )
        if item.get("parent_class"):
            parent = normalize_object_path(str(item["parent_class"]))
            parent_id = graph.add_node(
                "class", parent, parent.rsplit(".", 1)[-1], {"path": parent}
            )
            graph.add_relation(
                class_id,
                "INHERITS",
                parent_id,
                producer=producer,
                evidence={"asset": item.get("asset_object_path")},
            )
        for interface in item.get("interfaces", []):
            interface_path = normalize_object_path(str(interface))
            interface_id = graph.add_node(
                "interface",
                interface_path,
                interface_path.rsplit(".", 1)[-1],
                {"path": interface_path},
            )
            graph.add_relation(
                class_id,
                "IMPLEMENTS",
                interface_id,
                producer=producer,
                evidence={"asset": item.get("asset_object_path")},
            )
        for variable in item.get("variables", []):
            key = f"{generated or package}|{variable.get('name')}"
            variable_id = graph.add_node(
                "blueprint_variable", key, str(variable.get("name", "")), variable
            )
            graph.add_relation(
                class_id,
                "DECLARES_VARIABLE",
                variable_id,
                producer=producer,
                evidence={"asset": item.get("asset_object_path")},
            )
        for category, relation_kind in (
            ("functions", "DECLARES_FUNCTION"),
            ("events", "DECLARES_EVENT"),
        ):
            for callable_item in item.get(category, []):
                if callable_item.get("implemented") is False:
                    continue
                callable_key = (
                    f"{generated or package}|{category}|{callable_item.get('name')}"
                )
                callable_id = graph.add_node(
                    "blueprint_function"
                    if category == "functions"
                    else "blueprint_event",
                    callable_key,
                    str(callable_item.get("name", "")),
                    callable_item,
                )
                graph.add_relation(
                    class_id,
                    relation_kind,
                    callable_id,
                    producer=producer,
                    evidence={"asset": item.get("asset_object_path")},
                )
        for component in item.get("components", []):
            component_key = f"{generated or package}|{component.get('name')}|{component.get('node')}"
            component_id = graph.add_node(
                "blueprint_component",
                component_key,
                str(component.get("name", "")),
                component,
            )
            graph.add_relation(
                class_id,
                "OWNS_COMPONENT",
                component_id,
                producer=producer,
                evidence={
                    "asset": item.get("asset_object_path"),
                    "component": component.get("node"),
                },
            )
            if component.get("class"):
                component_class = normalize_object_path(str(component["class"]))
                component_class_id = graph.add_node(
                    "class",
                    component_class,
                    component_class.rsplit(".", 1)[-1],
                    {"path": component_class},
                )
                graph.add_relation(
                    component_id,
                    "INSTANCE_OF",
                    component_class_id,
                    producer=producer,
                    evidence={
                        "asset": item.get("asset_object_path"),
                        "component": component.get("node"),
                    },
                )
        for graph_row in item.get("graphs", []):
            path = str(graph_row["object_path"])
            graph_id = graph.add_node(
                "blueprint_graph",
                path,
                str(graph_row["name"]),
                {
                    "object_path": path,
                    "graph_id": graph_row.get("graph_id"),
                    "asset": package,
                },
            )
            graph.add_relation(
                asset_id,
                "CONTAINS",
                graph_id,
                producer=producer,
                evidence={"asset": item.get("asset_object_path"), "graph": path},
            )
            nodes = graph_row.get("nodes") or graph_row.get("semantic_nodes", [])
            for node in nodes:
                node_path = str(node["object_path"])
                node_id = graph.add_node(
                    "blueprint_node",
                    node_path,
                    str(node.get("title") or node.get("type_id")),
                    node,
                )
                graph.add_relation(
                    graph_id,
                    "CONTAINS",
                    node_id,
                    producer=producer,
                    evidence={
                        "asset": item.get("asset_object_path"),
                        "graph": path,
                        "node": node_path,
                    },
                )
                symbol = node.get("symbol")
                if isinstance(symbol, dict) and symbol.get("symbol_path"):
                    symbol_path = normalize_object_path(str(symbol["symbol_path"]))
                    symbol_kind = str(symbol.get("symbol_kind") or "symbol")
                    symbol_node_id = graph.add_node(
                        "cxx_symbol" if symbol_path.startswith("/Script/") else "symbol",
                        symbol_path,
                        symbol_path.rsplit(".", 1)[-1].rsplit("::", 1)[-1],
                        {
                            "path": symbol_path,
                            "symbol_kind": symbol_kind,
                            "symbol_id": symbol.get("symbol_id"),
                        },
                    )
                    graph.add_relation(
                        node_id,
                        symbol_relation(node, symbol),
                        symbol_node_id,
                        producer=producer,
                        evidence={
                            "asset": item.get("asset_object_path"),
                            "graph": path,
                            "node": node_path,
                            "field": "symbol.symbol_path",
                        },
                    )
                    if symbol_path.startswith("/Script/") and ":" in symbol_path:
                        native_name = symbol_path.rsplit("/", 1)[-1]
                        module_and_name, member_name = native_name.split(":", 1)
                        class_name = module_and_name.rsplit(".", 1)[-1]
                        if class_name and member_name:
                            native_id = _cxx_symbol(
                                graph,
                                "method" if symbol_kind in {"function", "member"} else symbol_kind,
                                f"{class_name}::{member_name}",
                                {"blueprint_symbol_path": symbol_path},
                            )
                            graph.add_relation(
                                symbol_node_id,
                                "MAPS_TO",
                                native_id,
                                producer=producer,
                                evidence={
                                    "asset": item.get("asset_object_path"),
                                    "graph": path,
                                    "node": node_path,
                                },
                            )
                for pin in node.get("pins", []):
                    if str(pin.get("direction", "")).casefold() != "output":
                        continue
                    for connection in pin.get("connections", []):
                        target_path = str(connection.get("node", ""))
                        if not target_path:
                            continue
                        target_node_id = graph.add_node(
                            "blueprint_node",
                            target_path,
                            target_path.rsplit(".", 1)[-1],
                            {"object_path": target_path},
                        )
                        graph.add_relation(
                            node_id,
                            "DATA_OR_EXEC_LINK",
                            target_node_id,
                            producer=producer,
                            properties={
                                "pin": pin.get("name"),
                                "direction": pin.get("direction"),
                                "connected_pin": connection.get("pin"),
                            },
                            evidence={
                                "asset": item.get("asset_object_path"),
                                "graph": path,
                                "node": node_path,
                            },
                        )
        for reference in item.get("references", []):
            target_id = _target_node(
                graph, str(reference["kind"]), str(reference["target"])
            )
            source_id = asset_id
            reference_node = reference.get("node")
            if reference_node:
                source_id = graph.add_node(
                    "blueprint_node",
                    str(reference_node),
                    str(reference_node).rsplit(".", 1)[-1],
                    {"object_path": reference_node},
                )
            graph.add_relation(
                source_id,
                "REFERENCES",
                target_id,
                producer=producer,
                evidence={
                    "asset": item.get("asset_object_path"),
                    "field": reference.get("field"),
                    "graph": reference.get("graph_path") or reference.get("graph"),
                    "node": reference_node,
                },
            )


def _data_tables(
    graph: KnowledgeGraph, document: dict[str, Any], producer: str
) -> None:
    for table in document.get("data_tables", []):
        package = str(table["asset"])
        table_id = graph.add_node(
            "data_table",
            package,
            package.rsplit("/", 1)[-1],
            {"package": package, "row_count": table.get("row_count")},
        )
        if table.get("row_struct"):
            struct_path = normalize_object_path(str(table["row_struct"]))
            struct_id = graph.add_node(
                "row_struct",
                struct_path,
                struct_path.rsplit(".", 1)[-1],
                {"path": struct_path},
            )
            graph.add_relation(
                table_id,
                "USES_ROW_STRUCT",
                struct_id,
                producer=producer,
                evidence={"asset": table.get("object_path")},
            )
        for row in table.get("rows", []):
            row_key = f"{package}|{row['name']}"
            row_id = graph.add_node(
                "data_table_row",
                row_key,
                str(row["name"]),
                {
                    "table": package,
                    **({"values": row["values"]} if "values" in row else {}),
                },
            )
            graph.add_relation(
                table_id,
                "CONTAINS_ROW",
                row_id,
                producer=producer,
                evidence={"asset": table.get("object_path"), "row": row.get("name")},
            )
            for reference in row.get("references", []):
                target_id = _target_node(
                    graph, str(reference["kind"]), str(reference["target"])
                )
                graph.add_relation(
                    row_id,
                    "REFERENCES",
                    target_id,
                    producer=producer,
                    evidence={
                        "asset": table.get("object_path"),
                        "row": row.get("name"),
                        "field": reference.get("field"),
                    },
                )


def _data_assets(
    graph: KnowledgeGraph, document: dict[str, Any], producer: str
) -> None:
    for item in document.get("data_assets", []):
        package = str(item["asset"])
        object_path = str(item.get("object_path") or package)
        source_object_path = item.get("source_object_path")
        asset_id = graph.add_node(
            "asset",
            package,
            package.rsplit("/", 1)[-1],
            {
                "package": package,
                "object_path": object_path,
                "data_asset": True,
                "source_kind": item.get("source_kind"),
                "source_object_path": source_object_path,
                "generated_class": item.get("generated_class"),
                "baseline_kind": item.get("baseline_kind"),
                "baseline_object_path": item.get("baseline_object_path"),
                "baseline_class": item.get("baseline_class"),
                "observed_property_count": item.get("observed_property_count"),
                "property_count": item.get("property_count"),
            },
        )
        if item.get("asset_class"):
            class_path = normalize_object_path(str(item["asset_class"]))
            class_id = graph.add_node(
                "class",
                class_path,
                class_path.rsplit(".", 1)[-1],
                {"path": class_path},
            )
            graph.add_relation(
                asset_id,
                "INSTANCE_OF",
                class_id,
                producer=producer,
                evidence={
                    "asset": object_path,
                    "source_object": source_object_path,
                },
            )
        for property_item in item.get("properties", []):
            if property_item.get("comparison") in {
                "matches_default",
                "baseline_unavailable",
            }:
                continue
            property_path = str(property_item["path"])
            property_key = f"{package}|{property_path}"
            property_id = graph.add_node(
                "data_asset_property",
                property_key,
                str(property_item.get("name") or property_path),
                {
                    "asset": package,
                    "path": property_path,
                    "value_kind": property_item.get("value_kind"),
                    "value": property_item.get("value"),
                    "comparison": property_item.get("comparison"),
                },
            )
            graph.add_relation(
                asset_id,
                "DECLARES_PROPERTY",
                property_id,
                producer=producer,
                evidence={
                    "asset": object_path,
                    "source_object": source_object_path,
                    "property": property_path,
                    "comparison": property_item.get("comparison"),
                    "baseline_kind": item.get("baseline_kind"),
                    "baseline_object": item.get("baseline_object_path"),
                },
            )
            for reference in property_item.get("references", []):
                target_id = _target_node(
                    graph, str(reference["kind"]), str(reference["target"])
                )
                graph.add_relation(
                    property_id,
                    "REFERENCES",
                    target_id,
                    producer=producer,
                    evidence={
                        "asset": object_path,
                        "source_object": source_object_path,
                        "property": property_path,
                        "field": reference.get("field"),
                    },
                )


def _primary_assets(
    graph: KnowledgeGraph, document: dict[str, Any], producer: str
) -> None:
    type_ids: dict[str, str] = {}
    for item in document.get("types", []):
        name = str(item.get("primary_asset_type", ""))
        if not name:
            continue
        type_id = graph.add_node("primary_asset_type", name, name, item)
        type_ids[name] = type_id
        if item.get("rules") not in (None, "", {}, []):
            rule_key = f"type|{name}|{json.dumps(item['rules'], ensure_ascii=False, sort_keys=True)}"
            rule_id = graph.add_node(
                "primary_asset_rule",
                rule_key,
                f"{name} Rules",
                {"rules": item["rules"]},
            )
            graph.add_relation(
                rule_id,
                "APPLIES_TO",
                type_id,
                producer=producer,
                evidence={"primary_asset_type": name},
            )
        for directory in (
            item.get("directories", [])
            if isinstance(item.get("directories"), list)
            else []
        ):
            path = (
                str(directory.get("path", directory))
                if isinstance(directory, dict)
                else str(directory)
            )
            path_id = graph.add_node("content_path", path, path, {"path": path})
            graph.add_relation(
                type_id,
                "SCANS_PATH",
                path_id,
                producer=producer,
                evidence={"primary_asset_type": name},
            )
    for item in document.get("primary_assets", []):
        identifier = item.get("id") or {}
        type_name = (
            str(identifier.get("type", "")) if isinstance(identifier, dict) else ""
        )
        name = (
            str(identifier.get("name", identifier))
            if isinstance(identifier, dict)
            else str(identifier)
        )
        key = f"{type_name}:{name}"
        primary_id = graph.add_node(
            "primary_asset",
            key,
            name,
            {"id": identifier, "object_path": item.get("object_path")},
        )
        if type_name:
            type_id = type_ids.get(type_name) or graph.add_node(
                "primary_asset_type", type_name, type_name
            )
            graph.add_relation(
                primary_id,
                "PRIMARY_ASSET_OF_TYPE",
                type_id,
                producer=producer,
                evidence={"primary_asset": key},
            )
        if item.get("object_path"):
            package = package_from_object_path(str(item["object_path"]))
            asset_id = graph.add_node(
                "asset", package, package.rsplit("/", 1)[-1], {"package": package}
            )
            graph.add_relation(
                primary_id,
                "RESOLVES_TO",
                asset_id,
                producer=producer,
                evidence={"primary_asset": key},
            )
        if item.get("rules") not in (None, "", {}, []):
            rule_key = f"asset|{key}|{json.dumps(item['rules'], ensure_ascii=False, sort_keys=True)}"
            rule_id = graph.add_node(
                "primary_asset_rule",
                rule_key,
                f"{name} Rules",
                {"rules": item["rules"]},
            )
            graph.add_relation(
                rule_id,
                "APPLIES_TO",
                primary_id,
                producer=producer,
                evidence={"primary_asset": key},
            )
        if item.get("bundle_data") not in (None, "", {}, []):
            bundle_key = f"{key}|{json.dumps(item['bundle_data'], ensure_ascii=False, sort_keys=True)}"
            bundle_id = graph.add_node(
                "asset_bundle",
                bundle_key,
                f"{name} Bundles",
                {"bundle_data": item["bundle_data"]},
            )
            graph.add_relation(
                primary_id,
                "DECLARES_BUNDLE",
                bundle_id,
                producer=producer,
                evidence={"primary_asset": key},
            )


def _config(graph: KnowledgeGraph, document: dict[str, Any], producer: str) -> None:
    file_ids: dict[str, str] = {}
    section_ids: dict[tuple[str, str], str] = {}
    key_ids: dict[tuple[str, str], str] = {}
    last_declaration: dict[tuple[str, str], str] = {}
    for item in document.get("declarations", []):
        evidence = dict(item.get("evidence", {}))
        path = str(evidence.get("path", ""))
        file_id = file_ids.get(path) or graph.add_node(
            "config_file", path, Path(path).name, {"path": path}
        )
        file_ids[path] = file_id
        section = str(item["section"])
        section_key = (path, section)
        section_id = section_ids.get(section_key) or graph.add_node(
            "config_section", f"{path}|{section}", section, {"file": path}
        )
        section_ids[section_key] = section_id
        graph.add_relation(
            file_id, "DECLARES", section_id, producer=producer, evidence=evidence
        )
        key_name = str(item["key"])
        logical_key = (section, key_name)
        key_id = key_ids.get(logical_key) or graph.add_node(
            "config_key", f"{section}|{key_name}", key_name, {"section": section}
        )
        key_ids[logical_key] = key_id
        declaration_key = f"{path}|{evidence.get('line')}|{section}|{key_name}"
        declaration_id = graph.add_node(
            "config_declaration",
            declaration_key,
            key_name,
            {
                "section": section,
                "operator": item.get("operator"),
                "value": item.get("value"),
            },
        )
        graph.add_relation(
            section_id, "DECLARES", declaration_id, producer=producer, evidence=evidence
        )
        graph.add_relation(
            declaration_id, "CONFIGURES", key_id, producer=producer, evidence=evidence
        )
        previous_id = last_declaration.get(logical_key)
        if previous_id is not None:
            graph.add_relation(
                declaration_id,
                "OVERRIDES",
                previous_id,
                producer=producer,
                evidence=evidence,
            )
        last_declaration[logical_key] = declaration_id
        for reference in item.get("references", []):
            target_id = _target_node(
                graph, str(reference["kind"]), str(reference["target"])
            )
            relation_kind = (
                "DECLARES_TAG"
                if reference["kind"] == "gameplay_tag"
                else "SELECTS_CLASS"
                if reference["kind"] == "class"
                else "REFERENCES"
            )
            graph.add_relation(
                declaration_id,
                relation_kind,
                target_id,
                producer=producer,
                evidence=evidence,
            )

    for item in document.get("primary_asset_types", []):
        type_name = str(item["primary_asset_type"])
        type_id = graph.add_node(
            "primary_asset_type",
            type_name,
            type_name,
            {
                "has_blueprint_classes": item.get("has_blueprint_classes"),
                "is_editor_only": item.get("is_editor_only"),
            },
        )
        evidence = dict(item.get("evidence", {}))
        declaration_key = (
            f"{evidence.get('path')}|{evidence.get('line')}|"
            "/Script/Engine.AssetManagerSettings|PrimaryAssetTypesToScan"
        )
        declaration_id = graph.add_node(
            "config_declaration",
            declaration_key,
            "PrimaryAssetTypesToScan",
            {"operator": item.get("operator")},
        )
        graph.add_relation(
            declaration_id,
            "CONFIGURES",
            type_id,
            producer=producer,
            evidence=evidence,
        )
        if item.get("asset_base_class"):
            class_path = normalize_object_path(str(item["asset_base_class"]))
            class_id = graph.add_node(
                "class",
                class_path,
                class_path.rsplit(".", 1)[-1],
                {"path": class_path},
            )
            graph.add_relation(
                type_id,
                "SELECTS_CLASS",
                class_id,
                producer=producer,
                evidence=evidence,
            )
        for directory in item.get("directories", []):
            path_id = graph.add_node(
                "content_path", str(directory), str(directory), {"path": directory}
            )
            graph.add_relation(
                type_id,
                "SCANS_PATH",
                path_id,
                producer=producer,
                evidence=evidence,
            )
        for asset in item.get("specific_assets", []):
            package = package_from_object_path(str(asset))
            asset_id = graph.add_node(
                "asset",
                package,
                package.rsplit("/", 1)[-1],
                {"package": package},
            )
            graph.add_relation(
                type_id,
                "MANAGES",
                asset_id,
                producer=producer,
                evidence=evidence,
            )
        if item.get("rules"):
            rule_key = (
                f"config|{type_name}|{evidence.get('path')}|{evidence.get('line')}"
            )
            rule_id = graph.add_node(
                "primary_asset_rule",
                rule_key,
                f"{type_name} Rules",
                {"rules": item["rules"], "operator": item.get("operator")},
            )
            graph.add_relation(
                rule_id,
                "APPLIES_TO",
                type_id,
                producer=producer,
                evidence=evidence,
            )


def _cxx_messages(
    graph: KnowledgeGraph, document: dict[str, Any], producer: str
) -> None:
    relation_kind = {
        "publish": "PUBLISHES_EVENT",
        "subscribe": "SUBSCRIBES_EVENT",
        "unsubscribe": "UNSUBSCRIBES_EVENT",
    }
    for item in document.get("operations", []):
        function = str(item["function"])
        evidence = dict(item.get("evidence", {}))
        function_id = graph.add_node(
            "cxx_function",
            f"{evidence.get('path')}|{function}",
            function.rsplit("::", 1)[-1],
            {"qualified_name": function, "signature": item.get("signature")},
        )
        channel = item.get("channel", {})
        if channel.get("tag"):
            tag = str(channel["tag"])
            target_id = graph.add_node("gameplay_tag", tag, tag, {"tag": tag})
            certainty = "confirmed"
        else:
            expression = str(channel.get("expression", ""))
            target_id = graph.add_node(
                "message_channel_expression",
                f"{evidence.get('path')}:{evidence.get('line')}|{expression}",
                expression or "Dynamic Channel",
                {"expression": expression},
            )
            certainty = "unresolved"
        graph.add_relation(
            function_id,
            relation_kind[str(item["operation"])],
            target_id,
            certainty=certainty,
            producer=producer,
            properties={"channel_status": channel.get("status")},
            evidence=evidence,
        )
        if item.get("payload_type"):
            payload = str(item["payload_type"])
            payload_id = graph.add_node(
                "payload_type", payload, payload.rsplit("::", 1)[-1], {"type": payload}
            )
            graph.add_relation(
                function_id,
                "USES_TYPE",
                payload_id,
                producer=producer,
                evidence=evidence,
            )


def _message_scan(
    graph: KnowledgeGraph, document: dict[str, Any], producer: str
) -> None:
    exported = export_message_graph(document)
    _import_graph(graph, exported, producer)


def _cxx_symbol(
    graph: KnowledgeGraph,
    kind: str,
    name: str,
    properties: dict[str, Any] | None = None,
) -> str:
    normalized = str(name).strip()
    node_kind = {
        "class": "cxx_class",
        "struct": "cxx_struct",
        "union": "cxx_struct",
        "enum": "cxx_enum",
        "variable": "cxx_variable",
        "global_variable": "cxx_variable",
        "function": "cxx_function",
        "free_function": "cxx_function",
        "method": "cxx_function",
        "type": "cxx_type",
        "member_call": "cxx_function",
    }.get(kind, "cxx_symbol")
    return graph.add_node(
        node_kind,
        normalized,
        normalized.rsplit("::", 1)[-1],
        {"qualified_name": normalized, **(properties or {})},
    )


def _cxx_document(graph: KnowledgeGraph, document: dict[str, Any], producer: str) -> None:
    """Adapt the existing sourcetools facts into the shared graph.

    Sourcetools intentionally reports syntax facts from explicitly selected
    files.  The adapter keeps that provenance and does not pretend that a
    compiler linker resolved an unknown symbol.
    """

    def evidence(item: dict[str, Any]) -> dict[str, Any]:
        detail = dict(item.get("evidence", {}))
        if item.get("file") and "path" not in detail:
            detail["path"] = item["file"]
        return detail

    for group_name, values in document.items():
        if group_name not in {
            "classes",
            "structs",
            "enums",
            "global_variables",
            "free_functions",
        } or not isinstance(values, list):
            continue
        kind = {
            "classes": "class",
            "structs": "struct",
            "enums": "enum",
            "global_variables": "global_variable",
            "free_functions": "free_function",
        }[group_name]
        for item in values:
            name = str(item.get("qualified_name") or item.get("name") or "")
            if not name:
                continue
            node_id = _cxx_symbol(graph, kind, name, item)
            item_evidence = evidence(item)
            for base in item.get("base_types", []) or []:
                base_id = _cxx_symbol(graph, "type", str(base))
                graph.add_relation(
                    node_id,
                    "INHERITS",
                    base_id,
                    producer=producer,
                    evidence=item_evidence,
                )

    for item in document.get("functions", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("qualified_name") or item.get("name") or "")
        if not name:
            continue
        function_id = _cxx_symbol(graph, str(item.get("kind", "function")), name, item)
        for base in item.get("base_types", []) or []:
            base_id = _cxx_symbol(graph, "type", str(base))
            graph.add_relation(
                function_id,
                "INHERITS",
                base_id,
                producer=producer,
                evidence=evidence(item),
            )

    matches = document.get("matches", [])
    if not isinstance(matches, list):
        matches = []
    for match in matches:
        if not isinstance(match, dict):
            continue
        owner_name = str(
            match.get("qualified_name")
            or match.get("name")
            or match.get("function_id")
            or ""
        )
        owner_kind = "class" if match.get("member_anchors") is not None else "function"
        if not owner_name:
            continue
        owner_id = _cxx_symbol(graph, owner_kind, owner_name, match)
        owner_evidence = evidence(match)
        for member in match.get("member_anchors", []) or []:
            member_name = str(member.get("qualified_name") or "")
            if not member_name:
                owner = owner_name
                member_name = f"{owner}::{member.get('name', '')}"
            member_id = _cxx_symbol(graph, str(member.get("kind", "symbol")), member_name, member)
            graph.add_relation(
                owner_id,
                "DECLARES",
                member_id,
                producer=producer,
                evidence={**owner_evidence, **evidence(member)},
            )
        for member in match.get("member_functions", []) or []:
            member_name = str(member.get("qualified_name") or member.get("name") or "")
            if member_name:
                member_id = _cxx_symbol(graph, "method", member_name, member)
                graph.add_relation(
                    owner_id,
                    "DECLARES",
                    member_id,
                    producer=producer,
                    evidence={**owner_evidence, **evidence(member)},
                )
        for symbol in match.get("external_symbols", []) or []:
            spelling = str(symbol.get("spelling") or "")
            if not spelling:
                continue
            symbol_id = _cxx_symbol(graph, str(symbol.get("kind", "symbol")), spelling, symbol)
            graph.add_relation(
                owner_id,
                "REFERENCES_SYMBOL",
                symbol_id,
                certainty="unresolved" if symbol.get("kind") == "unknown" else "confirmed",
                producer=producer,
                evidence={**owner_evidence, **evidence(symbol)},
            )


def _cxx_adapter(graph: KnowledgeGraph, document: dict[str, Any], producer: str) -> None:
    _cxx_document(graph, document, producer)


def _level_actors(graph: KnowledgeGraph, document: dict[str, Any], producer: str) -> None:
    world = document.get("world", {})
    world_path = str(world.get("object_path") or "")
    if not world_path:
        return
    world_id = graph.add_node(
        "level_world",
        world_path,
        world_path.rsplit("/", 1)[-1],
        world,
    )
    for graph_row in world.get("level_script_graphs", []) or []:
        graph_path = str(graph_row.get("object_path") or "")
        if not graph_path:
            continue
        graph_node_id = graph.add_node(
            "blueprint_graph",
            graph_path,
            str(graph_row.get("name") or graph_path),
            {"object_path": graph_path, "level_script": world_path},
        )
        graph.add_relation(
            world_id,
            "CONTAINS",
            graph_node_id,
            producer=producer,
            evidence={"world": world_path, "graph": graph_path},
        )
        for node in graph_row.get("nodes", []) or []:
            node_path = str(node.get("object_path") or "")
            if not node_path:
                continue
            node_id = graph.add_node(
                "blueprint_node",
                node_path,
                str(node.get("title") or node.get("type_id") or node_path),
                node,
            )
            graph.add_relation(
                graph_node_id,
                "CONTAINS",
                node_id,
                producer=producer,
                evidence={"world": world_path, "graph": graph_path, "node": node_path},
            )
            symbol = node.get("symbol")
            if isinstance(symbol, dict) and symbol.get("symbol_path"):
                symbol_path = normalize_object_path(str(symbol["symbol_path"]))
                symbol_node_id = graph.add_node(
                    "cxx_symbol" if symbol_path.startswith("/Script/") else "symbol",
                    symbol_path,
                    symbol_path.rsplit(".", 1)[-1].rsplit("::", 1)[-1],
                    {
                        "path": symbol_path,
                        "symbol_kind": symbol.get("symbol_kind"),
                        "symbol_id": symbol.get("symbol_id"),
                    },
                )
                graph.add_relation(
                    node_id,
                    "CALLS",
                    symbol_node_id,
                    producer=producer,
                    evidence={"world": world_path, "graph": graph_path, "node": node_path},
                )
    for level in world.get("streaming_levels", []) or []:
        level_path = str(level)
        level_id = graph.add_node(
            "level",
            level_path,
            level_path.rsplit("/", 1)[-1],
            {"object_path": level_path},
        )
        graph.add_relation(
            world_id,
            "STREAMS_LEVEL",
            level_id,
            producer=producer,
            evidence={"world": world_path},
        )
    for actor in document.get("actors", []) or []:
        actor_path = str(actor.get("object_path") or actor.get("actor_id") or "")
        if not actor_path:
            continue
        actor_id = graph.add_node("level_actor", actor_path, str(actor.get("label") or actor_path), actor)
        graph.add_relation(
            world_id,
            "CONTAINS",
            actor_id,
            producer=producer,
            evidence={"world": world_path, "actor": actor_path},
        )
        class_path = actor.get("class")
        if class_path:
            class_value = normalize_object_path(str(class_path))
            class_id = graph.add_node(
                "class",
                class_value,
                class_value.rsplit(".", 1)[-1],
                {"path": class_value},
            )
            graph.add_relation(
                actor_id,
                "INSTANCE_OF",
                class_id,
                producer=producer,
                evidence={"actor": actor_path},
            )
        for relation_name, relation_kind in (
            ("owner", "OWNED_BY"),
            ("attach_parent", "ATTACHED_TO"),
        ):
            target = actor.get(relation_name)
            if target:
                target_path = str(target)
                target_id = graph.add_node(
                    "level_actor",
                    target_path,
                    target_path.rsplit(".", 1)[-1],
                    {"object_path": target_path},
                )
                graph.add_relation(
                    actor_id,
                    relation_kind,
                    target_id,
                    producer=producer,
                    evidence={"actor": actor_path},
                )
        for layer in actor.get("data_layers", []) or []:
            layer_path = str(layer)
            layer_id = graph.add_node(
                "data_layer",
                layer_path,
                layer_path.rsplit("/", 1)[-1],
                {"path": layer_path},
            )
            graph.add_relation(
                actor_id,
                "IN_DATA_LAYER",
                layer_id,
                producer=producer,
                evidence={"actor": actor_path},
            )
        for component in actor.get("components", []) or []:
            component_path = str(component.get("object_path") or component.get("component_id") or "")
            if not component_path:
                continue
            component_id = graph.add_node(
                "level_component",
                component_path,
                str(component.get("name") or component_path),
                component,
            )
            graph.add_relation(
                actor_id,
                "OWNS_COMPONENT",
                component_id,
                producer=producer,
                evidence={"actor": actor_path, "component": component_path},
            )
            component_class = component.get("class")
            if component_class:
                component_class_path = normalize_object_path(str(component_class))
                component_class_id = graph.add_node(
                    "class",
                    component_class_path,
                    component_class_path.rsplit(".", 1)[-1],
                    {"path": component_class_path},
                )
                graph.add_relation(
                    component_id,
                    "INSTANCE_OF",
                    component_class_id,
                    producer=producer,
                    evidence={"actor": actor_path, "component": component_path},
                )


def _import_graph(graph: KnowledgeGraph, source: dict[str, Any], producer: str) -> None:
    mapping: dict[str, str] = {}
    for node in source.get("nodes", []):
        kind = str(node["kind"])
        properties = dict(node.get("properties", {}))
        canonical = str(
            properties.get("package")
            or properties.get("tag")
            or properties.get("object_path")
            or properties.get("type")
            or node.get("canonical_key")
            or node.get("name")
            or node.get("node_id")
        )
        mapping[str(node["node_id"])] = graph.add_node(
            kind, canonical, str(node.get("name", canonical)), properties
        )
    evidence_by_relation: dict[str, list[dict[str, Any]]] = {}
    for item in source.get("evidence", []):
        evidence_by_relation.setdefault(str(item["relation_id"]), []).append(
            {
                key: value
                for key, value in item.items()
                if key not in {"evidence_id", "relation_id"}
            }
        )
    for relation in source.get("relations", []):
        for evidence in evidence_by_relation.get(str(relation["relation_id"]), [{}]):
            graph.add_relation(
                mapping[str(relation["source_id"])],
                str(relation["kind"]),
                mapping[str(relation["target_id"])],
                certainty=str(relation.get("certainty", "confirmed")),
                properties=dict(relation.get("properties", {})),
                producer=producer,
                evidence=evidence,
            )


ADAPTERS: dict[str, Callable[[KnowledgeGraph, dict[str, Any], str], None]] = {
    "ue_editor_export_asset_graph": _asset_graph,
    "ue_editor_scan_blueprint_structure": _blueprints,
    "ue_editor_scan_data_tables": _data_tables,
    "ue_editor_scan_data_assets": _data_assets,
    "ue_editor_scan_primary_assets": _primary_assets,
    "ue_scan_config_graph": _config,
    "ue_scan_cxx_gameplay_messages": _cxx_messages,
    "ue_editor_scan_gameplay_messages": _message_scan,
    "ue_list_cxx_types": _cxx_adapter,
    "ue_list_cxx_functions": _cxx_adapter,
    "ue_inspect_cxx_type": _cxx_adapter,
    "ue_inspect_cxx_function": _cxx_adapter,
    "ue_editor_scan_level_actors": _level_actors,
}


def project_identity(document: dict[str, Any]) -> str:
    if isinstance(document.get("editor"), dict) and document["editor"].get("project"):
        return str(document["editor"]["project"]).replace("\\", "/")
    if document.get("project"):
        return str(document["project"]).replace("\\", "/")
    if isinstance(document.get("graph"), dict) and document["graph"].get("project"):
        return str(document["graph"]["project"]).replace("\\", "/")
    return ""


def has_dirty_packages(document: dict[str, Any]) -> bool:
    return bool(document.get("editor_state", {}).get("dirty_packages", []))


def build_knowledge_graph(
    documents: list[tuple[str, dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    identities = sorted(
        {
            project_identity(document).casefold()
            for _, document in documents
            if project_identity(document)
        }
    )
    problems: list[dict[str, Any]] = []
    if len(identities) > 1:
        problems.append(
            {
                "severity": "error",
                "code": "project-identity-mismatch",
                "message": "Input documents describe different projects.",
            }
        )
    project = project_identity(documents[0][1]) if documents else "unknown-project"
    graph = KnowledgeGraph(project or "unknown-project")
    for producer, document in documents:
        schema = str(document.get("schema_version", ""))
        if schema == "ue_editor_export_message_graph":
            _import_graph(graph, dict(document.get("graph", {})), producer)
            continue
        adapter = ADAPTERS.get(schema)
        if adapter is None:
            problems.append(
                {
                    "severity": "warning",
                    "code": "unsupported-input-schema",
                    "schema_version": schema,
                    "producer": producer,
                    "message": f"No knowledge graph adapter exists for {schema or 'missing schema'}.",
                }
            )
            continue
        adapter(graph, document, producer)
    return graph.document(), problems


def validate_graph(graph: dict[str, Any]) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    nodes = {str(item.get("node_id")): item for item in graph.get("nodes", [])}
    relations = {
        str(item.get("relation_id")): item for item in graph.get("relations", [])
    }
    if len(nodes) != len(graph.get("nodes", [])):
        problems.append(
            {
                "severity": "error",
                "code": "duplicate-node-id",
                "message": "Graph contains duplicate node identifiers.",
            }
        )
    if len(relations) != len(graph.get("relations", [])):
        problems.append(
            {
                "severity": "error",
                "code": "duplicate-relation-id",
                "message": "Graph contains duplicate relation identifiers.",
            }
        )
    for relation in relations.values():
        missing = [
            field
            for field in ("source_id", "target_id")
            if str(relation.get(field)) not in nodes
        ]
        if missing:
            problems.append(
                {
                    "severity": "error",
                    "code": "dangling-relation-endpoint",
                    "relation_id": relation.get("relation_id"),
                    "missing": missing,
                    "message": "Relation endpoint does not exist.",
                }
            )
    evidence_counts = {relation_id: 0 for relation_id in relations}
    for item in graph.get("evidence", []):
        relation_id = str(item.get("relation_id"))
        if relation_id not in relations:
            problems.append(
                {
                    "severity": "error",
                    "code": "dangling-evidence",
                    "evidence_id": item.get("evidence_id"),
                    "message": "Evidence references an unknown relation.",
                }
            )
        else:
            evidence_counts[relation_id] += 1
    for relation_id, count in evidence_counts.items():
        if count == 0:
            problems.append(
                {
                    "severity": "warning",
                    "code": "relation-evidence-missing",
                    "relation_id": relation_id,
                    "message": "Relation has no evidence record.",
                }
            )
    expected = graph.get("counts", {})
    actual = {
        "nodes": len(nodes),
        "relations": len(relations),
        "evidence": len(graph.get("evidence", [])),
    }
    if expected and expected != actual:
        problems.append(
            {
                "severity": "error",
                "code": "graph-count-mismatch",
                "expected": expected,
                "actual": actual,
                "message": "Graph counts do not match array contents.",
            }
        )
    return problems


def diff_graphs(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    def node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {str(item["canonical_key"]): item for item in graph.get("nodes", [])}

    def relation_map(
        graph: dict[str, Any],
    ) -> dict[tuple[str, str, str], dict[str, Any]]:
        nodes = {
            str(item["node_id"]): str(item["canonical_key"])
            for item in graph.get("nodes", [])
        }
        return {
            (
                nodes[str(item["source_id"])],
                str(item["kind"]),
                nodes[str(item["target_id"])],
            ): item
            for item in graph.get("relations", [])
            if str(item["source_id"]) in nodes and str(item["target_id"]) in nodes
        }

    current_nodes, previous_nodes = node_map(current), node_map(previous)
    current_relations, previous_relations = (
        relation_map(current),
        relation_map(previous),
    )
    changed_nodes = [
        current_nodes[key]
        for key in sorted(current_nodes.keys() & previous_nodes.keys())
        if current_nodes[key].get("properties") != previous_nodes[key].get("properties")
    ]
    return {
        "added_nodes": [
            current_nodes[key]
            for key in sorted(current_nodes.keys() - previous_nodes.keys())
        ],
        "removed_nodes": [
            previous_nodes[key]
            for key in sorted(previous_nodes.keys() - current_nodes.keys())
        ],
        "changed_nodes": changed_nodes,
        "added_relations": [
            current_relations[key]
            for key in sorted(current_relations.keys() - previous_relations.keys())
        ],
        "removed_relations": [
            previous_relations[key]
            for key in sorted(previous_relations.keys() - current_relations.keys())
        ],
    }
