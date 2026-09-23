from __future__ import annotations

from typing import Any

import unreal
from editor_toolset.toolsets.blueprint import BlueprintTools

from ue_editor_tools.identifiers import stable_fact_id
from .blueprints import serialize_node


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


def _property(value: Any, name: str) -> Any:
    try:
        return value.get_editor_property(name)
    except Exception:
        return None


def _scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_scalar(item) for item in value]
    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        result = {"x": float(value.x), "y": float(value.y), "z": float(value.z)}
        if hasattr(value, "w"):
            result["w"] = float(value.w)
        return result
    path = _path(value)
    if path:
        return path
    return str(value)


def _transform(actor: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, method_name in (
        ("location", "get_actor_location"),
        ("rotation", "get_actor_rotation"),
        ("scale", "get_actor_scale3d"),
    ):
        method = getattr(actor, method_name, None)
        if method is None:
            continue
        try:
            result[name] = _scalar(method())
        except Exception:
            continue
    return result


def _class_path(value: Any) -> str | None:
    try:
        klass = value.get_class()
        return _path(klass)
    except Exception:
        return None


def _call_path(value: Any, method_name: str) -> str | None:
    method = getattr(value, method_name, None)
    if method is None:
        return None
    try:
        return _path(method())
    except Exception:
        return None


def _common_properties(value: Any) -> dict[str, Any]:
    names = (
        "replicates",
        "always_relevant",
        "net_update_frequency",
        "net_priority",
        "tags",
        "actor_label",
        "folder_path",
        "mobility",
        "collision_profile_name",
        "hidden",
        "hidden_ed",
    )
    result: dict[str, Any] = {}
    for name in names:
        value_item = _property(value, name)
        if value_item is not None:
            result[name] = _scalar(value_item)
    getter = getattr(value, "get_actor_label", None)
    if getter is not None and "actor_label" not in result:
        try:
            result["actor_label"] = str(getter())
        except Exception:
            pass
    return result


def _component_rows(actor: Any, actor_path: str) -> list[dict[str, Any]]:
    getter = getattr(actor, "get_components_by_class", None)
    if getter is None:
        return []
    try:
        components = getter(unreal.ActorComponent)
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for component in components or []:
        component_path = _path(component) or ""
        if not component_path:
            continue
        parent = None
        attach = getattr(component, "get_attach_parent", None)
        if attach is not None:
            try:
                parent = _path(attach())
            except Exception:
                pass
        name = ""
        name_getter = getattr(component, "get_name", None)
        if name_getter is not None:
            try:
                name = str(name_getter())
            except Exception:
                pass
        rows.append(
            {
                "component_id": stable_fact_id("level_component", actor_path, component_path),
                "object_path": component_path,
                "name": name,
                "class": _class_path(component),
                "parent_component": parent,
                "properties": _common_properties(component),
            }
        )
    return sorted(rows, key=lambda item: str(item["object_path"]).casefold())


def _actor_row(actor: Any, *, world_path: str, include_components: bool) -> dict[str, Any]:
    object_path = _path(actor) or ""
    label = ""
    getter = getattr(actor, "get_actor_label", None)
    if getter is not None:
        try:
            label = str(getter())
        except Exception:
            pass
    outer_path = _call_path(actor, "get_outer")
    owner_path = _call_path(actor, "get_owner")
    parent_path = _call_path(actor, "get_attach_parent_actor")
    data_layers: list[str] = []
    layer_getter = getattr(actor, "get_data_layer_assets", None)
    if layer_getter is not None:
        try:
            data_layers = sorted(
                {value for value in (_path(item) for item in layer_getter() or []) if value},
                key=str.casefold,
            )
        except Exception:
            pass
    row = {
        "actor_id": stable_fact_id("level_actor", world_path, object_path),
        "object_path": object_path,
        "name": str(getattr(actor, "get_name", lambda: "")()),
        "label": label,
        "class": _class_path(actor),
        "world": world_path,
        "outer": outer_path,
        "owner": owner_path,
        "attach_parent": parent_path,
        "transform": _transform(actor),
        "tags": [str(item) for item in getattr(actor, "tags", []) or []],
        "data_layers": data_layers,
        "properties": _common_properties(actor),
    }
    if include_components:
        row["components"] = _component_rows(actor, object_path)
    return row


def _editor_world() -> Any:
    library = getattr(unreal, "EditorLevelLibrary", None)
    if library is not None:
        getter = getattr(library, "get_editor_world", None)
        if getter is not None:
            try:
                return getter()
            except Exception:
                pass
    subsystem_type = getattr(unreal, "EditorActorSubsystem", None)
    get_subsystem = getattr(unreal, "get_editor_subsystem", None)
    if subsystem_type is not None and get_subsystem is not None:
        try:
            subsystem = get_subsystem(subsystem_type)
            return subsystem.get_world() if subsystem is not None else None
        except Exception:
            pass
    return None


def scan_level_actors(
    *,
    actor_class: str = "",
    max_actors: int = 0,
    include_components: bool = True,
) -> dict[str, Any]:
    if max_actors < 0:
        raise ValueError("max_actors cannot be negative")
    world = _editor_world()
    if world is None:
        raise ValueError("No Editor world is currently loaded")
    world_path = _path(world) or ""
    world_class = _class_path(world)
    level_script = None
    level_script_graphs: list[dict[str, Any]] = []
    getter = getattr(world, "get_level_script_blueprint", None)
    if getter is not None:
        try:
            level_script_object = getter()
            level_script = _path(level_script_object)
            if level_script_object is not None:
                for graph in sorted(
                    BlueprintTools.list_graphs(level_script_object),
                    key=lambda value: value.get_name().casefold(),
                ):
                    graph_path = graph.get_path_name()
                    nodes = [
                        serialize_node(
                            node,
                            graph_path=graph_path,
                            asset_path=level_script or world_path,
                        )
                        for node in BlueprintTools.find_nodes(graph)
                    ]
                    level_script_graphs.append(
                        {
                            "graph_id": stable_fact_id(
                                "level_script_graph", level_script or world_path, graph_path
                            ),
                            "name": graph.get_name(),
                            "object_path": graph_path,
                            "node_count": len(nodes),
                            "nodes": nodes,
                        }
                    )
        except Exception:
            pass
    streaming_levels: list[str] = []
    level_getter = getattr(world, "get_levels", None)
    if level_getter is not None:
        try:
            streaming_levels = sorted(
                {value for value in (_path(item) for item in level_getter() or []) if value},
                key=str.casefold,
            )
        except Exception:
            pass
    library = getattr(unreal, "EditorLevelLibrary", None)
    actors: list[Any] = []
    if library is not None:
        getter = getattr(library, "get_all_level_actors", None)
        if getter is not None:
            try:
                actors = list(getter() or [])
            except Exception:
                actors = []
    selected = []
    wanted = actor_class.casefold().strip()
    for actor in actors:
        class_path = _class_path(actor) or ""
        if wanted and wanted not in class_path.casefold():
            continue
        selected.append(actor)
    selected.sort(key=lambda item: (_path(item) or "").casefold())
    available_actor_count = len(selected)
    truncated = max_actors > 0 and available_actor_count > max_actors
    if max_actors > 0:
        selected = selected[:max_actors]
    rows = [
        _actor_row(actor, world_path=world_path, include_components=include_components)
        for actor in selected
    ]
    return {
        "world": {
            "world_id": stable_fact_id("level_world", world_path),
            "object_path": world_path,
            "class": world_class,
            "level_script_blueprint": level_script,
            "level_script_graphs": level_script_graphs,
            "streaming_levels": streaming_levels,
        },
        "actor_class_filter": actor_class,
        "actor_count": len(rows),
        "available_actor_count": available_actor_count,
        "truncated": truncated,
        "actors": rows,
    }
