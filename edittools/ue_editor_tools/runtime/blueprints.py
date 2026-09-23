from __future__ import annotations

import json
from typing import Any

import unreal

from editor_toolset.toolsets.blueprint import BlueprintTools, _get_node_type_id

from ue_editor_tools.identifiers import stable_fact_id
from ue_editor_tools.value_refs import normalize_object_path


EXCLUDED_ROOTS = {"/Engine", "/Script", "/Temp", "/Memory", "/Transient"}


def _direction(value: Any) -> str:
    text = str(value)
    folded = text.casefold()
    return "input" if "input" in folded else "output" if "output" in folded else text


def _type_schema(pin: Any) -> dict[str, Any] | None:
    try:
        value = json.loads(str(pin.get_pin_type_as_json_schema()))
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _pin_value(pin: Any) -> str:
    try:
        return str(pin.get_pin_value())
    except Exception:
        return ""


def _property(value: Any, name: str) -> Any:
    try:
        return value.get_editor_property(name)
    except Exception:
        return None


def _path(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "get_path_name"):
        try:
            return str(value.get_path_name())
        except Exception:
            pass
    text = str(value)
    return text if text and text != "None" else None


def _reference_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_reference_value(item) for item in value]
    if hasattr(value, "get_editor_property") and not hasattr(value, "get_path_name"):
        fields: dict[str, Any] = {}
        for field in (
            "member_name",
            "member_parent",
            "member_guid",
            "member_scope",
            "self_context",
        ):
            field_value = _property(value, field)
            if field_value is not None:
                normalized = _reference_value(field_value)
                if normalized not in (None, "", "None"):
                    fields[field] = normalized
        if fields:
            return fields
    path = _path(value)
    if path:
        return path
    return str(value)


def _node_symbol(node: Any) -> dict[str, Any] | None:
    """Read the common UE node reference fields without assuming one wrapper version."""

    fields = (
        "function_reference",
        "member_reference",
        "variable_reference",
        "event_reference",
        "delegate_reference",
        "interface",
        "function_name",
        "member_name",
        "variable_name",
    )
    values: dict[str, Any] = {}
    for name in fields:
        value = _property(node, name)
        if value is None:
            continue
        normalized = _reference_value(value)
        if normalized not in (None, "", "None", {}):
            values[name] = normalized
    if not values:
        return None
    reference_field = next(
        (
            field
            for field in (
                "function_reference",
                "member_reference",
                "variable_reference",
                "event_reference",
                "delegate_reference",
                "interface",
            )
            if field in values
        ),
        None,
    )
    if reference_field is not None:
        raw_path = values[reference_field]
        if isinstance(raw_path, dict):
            member_name = str(raw_path.get("member_name") or "")
            parent = str(raw_path.get("member_parent") or "")
            raw_path = f"{parent}::{member_name}" if parent and member_name else member_name
        if isinstance(raw_path, str):
            path = normalize_object_path(raw_path)
            if path:
                values["symbol_kind"] = reference_field.removesuffix("_reference")
                values["symbol_path"] = path
                values["symbol_id"] = stable_fact_id(
                    "ue_symbol", values["symbol_kind"], path
                )
    if "symbol_path" not in values:
        for field, kind in (
            ("function_name", "function"),
            ("member_name", "member"),
            ("variable_name", "variable"),
        ):
            raw_path = values.get(field)
            if isinstance(raw_path, str) and raw_path:
                path = normalize_object_path(raw_path)
                values["symbol_kind"] = kind
                values["symbol_path"] = path
                values["symbol_id"] = stable_fact_id("ue_symbol", kind, path)
                break
    return values


def serialize_pin(pin: Any, index: int, *, node_path: str = "") -> dict[str, Any]:
    connections = []
    for connected in pin.list_connected_pins():
        owner = connected.get_owning_node()
        connections.append(
            {
                "node": owner.get_path_name(),
                "pin": str(connected.get_pin_name()),
                "pin_id": stable_fact_id(
                    "pin",
                    owner.get_path_name(),
                    str(connected.get_pin_name()),
                ),
                "direction": _direction(connected.get_pin_direction()),
            }
        )
    connections.sort(key=lambda item: (item["node"].casefold(), item["pin"].casefold()))
    name = str(pin.get_pin_name())
    return {
        "pin_id": stable_fact_id("pin", node_path, name),
        "index": index,
        "name": name,
        "direction": _direction(pin.get_pin_direction()),
        "type_display": str(pin.get_pin_type_display_string()),
        "type_schema": _type_schema(pin),
        "value": _pin_value(pin),
        "connections": connections,
    }


def serialize_node(node: Any, *, graph_path: str = "", asset_path: str = "") -> dict[str, Any]:
    object_path = node.get_path_name()
    position = node.get_node_pos()
    node_id = stable_fact_id("blueprint_node", asset_path, graph_path, object_path)
    pins = [
        serialize_pin(pin, index, node_path=object_path)
        for index, pin in enumerate(node.list_all_pins())
    ]
    return {
        "node_id": node_id,
        "object_path": object_path,
        "class": node.get_class().get_name(),
        "class_path": node.get_class().get_path_name(),
        "title": node.get_node_title(),
        "type_id": str(_get_node_type_id(node)),
        "position": {"x": int(position.x), "y": int(position.y)},
        "pins": pins,
        "symbol": _node_symbol(node),
    }


def _load_blueprint(asset_path: str) -> Any:
    asset = unreal.load_asset(asset_path)
    if asset is None:
        raise ValueError(
            f"Blueprint asset does not exist or could not be loaded: {asset_path}"
        )
    if not isinstance(asset, unreal.Blueprint):
        raise ValueError(
            f"Asset is not a Blueprint: {asset_path} ({asset.get_class().get_name()})"
        )
    return asset


def inspect_blueprint(
    asset_path: str,
    graph_name: str = "",
    title_filter: str = "",
    max_nodes: int = 0,
) -> dict[str, Any]:
    blueprint = _load_blueprint(asset_path)
    graphs = BlueprintTools.list_graphs(blueprint)
    if graph_name:
        graphs = [graph for graph in graphs if graph.get_name() == graph_name]
        if not graphs:
            raise ValueError(f"Blueprint {asset_path} has no graph named {graph_name}")
    graph_rows = []
    for graph in sorted(graphs, key=lambda value: value.get_name().casefold()):
        nodes = BlueprintTools.find_nodes(graph, title=title_filter)
        total = len(nodes)
        if max_nodes > 0:
            nodes = nodes[:max_nodes]
        graph_path = graph.get_path_name()
        graph_rows.append(
            {
                "graph_id": stable_fact_id("blueprint_graph", asset_path, graph_path),
                "name": graph.get_name(),
                "object_path": graph_path,
                "node_count": total,
                "returned_node_count": len(nodes),
                "truncated": len(nodes) < total,
                "nodes": [
                    serialize_node(
                        node,
                        graph_path=graph_path,
                        asset_path=asset_path,
                    )
                    for node in nodes
                ],
            }
        )
    return {
        "asset_id": stable_fact_id("blueprint_asset", asset_path),
        "asset": asset_path,
        "asset_object_path": blueprint.get_path_name(),
        "asset_class": blueprint.get_class().get_name(),
        "asset_class_path": blueprint.get_class().get_path_name(),
        "graphs": graph_rows,
    }


def _content_roots(registry: Any) -> list[str]:
    del registry
    roots = {"/Game"}
    project_dir = (
        unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
        .replace("\\", "/")
        .rstrip("/")
        .casefold()
    )
    plugin_library = getattr(unreal, "PluginBlueprintLibrary", None)
    if plugin_library is None:
        return ["/Game"]
    for plugin_name in plugin_library.get_enabled_plugin_names():
        try:
            base_dir = plugin_library.get_plugin_base_dir(plugin_name)
            full_base = (
                unreal.Paths.convert_relative_path_to_full(base_dir)
                .replace("\\", "/")
                .rstrip("/")
                .casefold()
            )
            if not (
                full_base == project_dir or full_base.startswith(project_dir + "/")
            ):
                continue
            mount = str(
                plugin_library.get_plugin_mounted_asset_path(plugin_name)
            ).rstrip("/")
            if mount and mount not in EXCLUDED_ROOTS:
                roots.add(mount)
        except Exception:
            continue
    return sorted(roots, key=str.casefold)


def list_blueprint_assets(roots: list[str] | None = None) -> dict[str, Any]:
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.wait_for_completion()
    selected_roots = sorted(set(roots or _content_roots(registry)), key=str.casefold)
    assets: dict[str, dict[str, str]] = {}
    for root in selected_roots:
        for asset in registry.get_assets_by_path(root, True, False):
            class_name = str(asset.asset_class_path.asset_name)
            if "Blueprint" not in class_name:
                continue
            package = str(asset.package_name)
            assets[package] = {
                "package": package,
                "asset_name": str(asset.asset_name),
                "asset_class": class_name,
                "root": root,
            }
    return {
        "roots": selected_roots,
        "assets": sorted(assets.values(), key=lambda item: item["package"].casefold()),
    }
