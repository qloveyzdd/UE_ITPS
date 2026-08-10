from __future__ import annotations

import json
from typing import Any

from editor_toolset.toolsets.blueprint import BlueprintTools
import unreal

from .blueprints import _load_blueprint, serialize_node
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
                rows.append({"name": name, "type_schema": type_schema})
            return sorted(rows, key=lambda item: str(item["name"]).casefold())
        except Exception:
            pass
    rows: list[dict[str, Any]] = []
    for item in _property(blueprint, "new_variables") or []:
        name = str(_property(item, "var_name") or "")
        type_value = _property(item, "var_type")
        rows.append(
            {
                "name": name,
                "type": str(type_value) if type_value is not None else None,
                "default_value": str(_property(item, "default_value") or ""),
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
                "name": str(name or ""),
                "description": str(description or ""),
                "implemented": bool(implemented),
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
    for graph in sorted(
        BlueprintTools.list_graphs(blueprint),
        key=lambda item: item.get_name().casefold(),
    ):
        nodes = [serialize_node(node) for node in BlueprintTools.find_nodes(graph)]
        graphs.append(
            {
                "name": graph.get_name(),
                "object_path": graph.get_path_name(),
                "class": _path(graph.get_class())
                if hasattr(graph, "get_class")
                else None,
                "node_count": len(nodes),
                "nodes": [
                    {
                        "object_path": node["object_path"],
                        "class": node["class"],
                        "type_id": node["type_id"],
                        "title": node["title"],
                    }
                    for node in nodes
                ],
            }
        )
        references.extend(unique_references(nodes))
    unique = {
        (item["kind"], item["target"], item.get("field", "")): item
        for item in references
    }
    return {
        "asset": asset_path,
        "asset_object_path": blueprint.get_path_name(),
        "generated_class": _path(generated),
        "parent_class": _path(parent),
        "interfaces": _interfaces(blueprint),
        "variables": _variables(blueprint),
        "functions": _callable_info(blueprint, "list_functions"),
        "events": _callable_info(blueprint, "list_events"),
        "components": _components(blueprint),
        "graphs": graphs,
        "references": [unique[key] for key in sorted(unique)],
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
