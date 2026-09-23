from __future__ import annotations

import json
from typing import Any

from editor_toolset.toolsets.blueprint import BlueprintTools
import unreal

from .blueprints import _load_blueprint, serialize_node
from ue_editor_tools.identifiers import stable_fact_id
from ue_editor_tools.blueprint_reachability import (
    project_blueprint_nodes,
    semantic_node_references,
)
from ue_editor_tools.value_refs import unique_references


def _path(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "get_path_name"):
        return str(value.get_path_name())
    text = str(value)
    return text if text and text != "None" else None


def _property(value: Any, name: str) -> Any:
    try:
        return value.get_editor_property(name)
    except Exception:
        return None


def _interfaces(blueprint: Any) -> list[str]:
    values: set[str] = set()
    for item in _property(blueprint, "implemented_interfaces") or []:
        candidate = _property(item, "interface") or item
        if path := _path(candidate):
            values.add(path)
    return sorted(values, key=str.casefold)


def _variables(blueprint: Any) -> list[dict[str, Any]]:
    library = getattr(unreal, "BlueprintEditorLibrary", None)
    if library is not None and hasattr(library, "list_member_variable_names"):
        try:
            generated = (
                blueprint.generated_class()
                if hasattr(blueprint, "generated_class")
                else None
            )
            rows = []
            for value in library.list_member_variable_names(blueprint, False):
                name = str(value)
                type_schema = None
                try:
                    pin_type = library.get_member_variable_type(blueprint, name)
                    raw_schema = library.pin_type_to_json_schema(pin_type, generated)
                    parsed_schema = json.loads(str(raw_schema))
                    type_schema = (
                        parsed_schema if isinstance(parsed_schema, dict) else None
                    )
                except Exception:
                    pass
                row: dict[str, Any] = {
                        "variable_id": stable_fact_id(
                            "blueprint_variable", blueprint.get_path_name(), name
                        ),
                        "name": name,
                        "type_schema": type_schema,
                    }
                for field, methods in (
                    (
                        "default_value",
                        ("get_blueprint_variable_default_value", "get_member_variable_default_value"),
                    ),
                    ("category", ("get_blueprint_variable_category", "get_member_variable_category")),
                    (
                        "instance_editable",
                        ("is_blueprint_variable_instance_editable", "is_member_variable_instance_editable"),
                    ),
                    (
                        "exposed_on_spawn",
                        ("is_blueprint_variable_exposed_on_spawn", "is_member_variable_exposed_on_spawn"),
                    ),
                ):
                    for method_name in methods:
                        method = getattr(library, method_name, None)
                        if method is None:
                            continue
                        try:
                            value = method(blueprint, name)
                        except Exception:
                            continue
                        if value not in (None, ""):
                            row[field] = str(value) if field in {"default_value", "category"} else bool(value)
                            break
                rows.append(row)
            return sorted(rows, key=lambda item: str(item["name"]).casefold())
        except Exception:
            pass
    rows: list[dict[str, Any]] = []
    for item in _property(blueprint, "new_variables") or []:
        name = str(_property(item, "var_name") or "")
        type_value = _property(item, "var_type")
        rows.append(
            {
                "variable_id": stable_fact_id(
                    "blueprint_variable", blueprint.get_path_name(), name
                ),
                "name": name,
                "type": str(type_value) if type_value is not None else None,
                "default_value": str(_property(item, "default_value") or ""),
                "category": str(_property(item, "category") or ""),
                "instance_editable": bool(
                    _property(item, "b_instance_editable")
                    or _property(item, "instance_editable")
                ),
                "exposed": bool(
                    _property(item, "b_public")
                    or _property(item, "b_exposed_on_spawn")
                    or _property(item, "exposed_on_spawn")
                ),
            }
        )
    return sorted(rows, key=lambda item: str(item["name"]).casefold())


def _callable_info(blueprint: Any, operation: str) -> list[dict[str, Any]]:
    library = getattr(unreal, "BlueprintEditorLibrary", None)
    method = getattr(library, operation, None) if library is not None else None
    if method is None:
        return []
    rows: list[dict[str, Any]] = []
    try:
        values = method(blueprint)
    except Exception:
        return []
    for item in values or []:
        name = _property(item, "name")
        description = _property(item, "description")
        implemented = _property(item, "is_implemented")
        rows.append(
            {
                "callable_id": stable_fact_id(
                    "blueprint_callable", blueprint.get_path_name(), operation, str(name or "")
                ),
                "name": str(name or ""),
                "description": str(description or ""),
                "implemented": bool(implemented),
                "signature": str(_property(item, "signature") or ""),
            }
        )
    return sorted(rows, key=lambda item: str(item["name"]).casefold())


def _components(blueprint: Any) -> list[dict[str, Any]]:
    script = _property(blueprint, "simple_construction_script")
    if script is None or not hasattr(script, "get_all_nodes"):
        return []
    rows: list[dict[str, Any]] = []
    for node in script.get_all_nodes() or []:
        template = _property(node, "component_template")
        name = (
            str(node.get_variable_name())
            if hasattr(node, "get_variable_name")
            else str(_property(node, "variable_name") or "")
        )
        rows.append(
            {
                "component_id": stable_fact_id(
                    "blueprint_component", blueprint.get_path_name(), name, _path(node)
                ),
                "name": name,
                "node": _path(node),
                "template": _path(template),
                "class": _path(template.get_class())
                if template is not None and hasattr(template, "get_class")
                else None,
            }
        )
    return sorted(
        rows,
        key=lambda item: (
            str(item["name"]).casefold(),
            str(item.get("node", "")).casefold(),
        ),
    )


def inspect_blueprint_structure(asset_path: str) -> dict[str, Any]:
    blueprint = _load_blueprint(asset_path)
    parent = _property(blueprint, "parent_class")
    library = getattr(unreal, "BlueprintEditorLibrary", None)
    if parent is None and library is not None:
        method = getattr(library, "get_blueprint_parent_class", None)
        if method is not None:
            try:
                parent = method(blueprint)
            except Exception:
                pass
    generated = (
        blueprint.generated_class() if hasattr(blueprint, "generated_class") else None
    )
    graphs: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    observed_references: list[dict[str, Any]] = []
    for graph in sorted(
        BlueprintTools.list_graphs(blueprint),
        key=lambda item: item.get_name().casefold(),
    ):
        graph_path = graph.get_path_name()
        nodes = [
            serialize_node(node, graph_path=graph_path, asset_path=asset_path)
            for node in BlueprintTools.find_nodes(graph)
        ]
        projection = project_blueprint_nodes(nodes)
        semantic_paths = {
            str(item["object_path"])
            for item in projection["semantic_nodes"]
            if item.get("object_path")
        }
        graphs.append(
            {
                "graph_id": stable_fact_id("blueprint_graph", asset_path, graph_path),
                "name": graph.get_name(),
                "object_path": graph_path,
                "class": _path(graph.get_class())
                if hasattr(graph, "get_class")
                else None,
                "node_count": len(nodes),
                "reachable_node_count": len(projection["reachable_paths"]),
                "semantic_node_count": len(projection["semantic_nodes"]),
                "nodes": nodes,
                "semantic_nodes": projection["semantic_nodes"],
            }
        )
        for node in nodes:
            if str(node.get("object_path")) not in semantic_paths:
                continue
            for reference in semantic_node_references([node]):
                references.append(
                    {
                        **reference,
                        "asset": asset_path,
                        "graph": graph.get_name(),
                        "graph_path": graph_path,
                        "node": node.get("object_path"),
                        "node_id": node.get("node_id"),
                    }
                )
        for node in nodes:
            for reference in unique_references(node):
                observed_references.append(
                    {
                        **reference,
                        "asset": asset_path,
                        "graph": graph.get_name(),
                        "graph_path": graph_path,
                        "node": node.get("object_path"),
                        "node_id": node.get("node_id"),
                    }
                )
    unique = {
        (
            item["kind"],
            item["target"],
            item.get("field", ""),
            item.get("node_id", ""),
        ): item
        for item in references
    }
    observed_unique = {
        (
            item["kind"],
            item["target"],
            item.get("field", ""),
            item.get("node_id", ""),
        ): item
        for item in observed_references
    }
    observed_functions = _callable_info(blueprint, "list_functions")
    observed_events = _callable_info(blueprint, "list_events")
    return {
        "asset_id": stable_fact_id("blueprint_asset", asset_path),
        "asset": asset_path,
        "asset_object_path": blueprint.get_path_name(),
        "asset_class": _path(blueprint.get_class()),
        "generated_class": _path(generated),
        "parent_class": _path(parent),
        "interfaces": _interfaces(blueprint),
        "variables": _variables(blueprint),
        "functions": [item for item in observed_functions if item["implemented"]],
        "events": [item for item in observed_events if item["implemented"]],
        "observed_functions": observed_functions,
        "observed_events": observed_events,
        "components": _components(blueprint),
        "graphs": graphs,
        "references": [unique[key] for key in sorted(unique)],
        "observed_references": [
            observed_unique[key] for key in sorted(observed_unique)
        ],
    }


def scan_blueprint_structure_batch(asset_paths: list[str]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for asset_path in asset_paths:
        try:
            items.append(inspect_blueprint_structure(asset_path))
        except Exception as exc:
            problems.append(
                {
                    "severity": "warning",
                    "code": "blueprint-structure-scan-failed",
                    "asset": asset_path,
                    "message": str(exc),
                }
            )
    items.sort(key=lambda item: str(item["asset"]).casefold())
    return {"items": items, "problems": problems}
