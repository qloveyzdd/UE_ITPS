from __future__ import annotations

from collections.abc import Mapping
import enum
import math
from typing import Any

from .value_refs import unique_references


def _type_name(value: Any) -> str:
    return type(value).__name__


def _editor_property(value: Any, name: str) -> Any:
    return value.get_editor_property(name)


def _semantic_field(value: Any, name: str) -> Any:
    try:
        return _editor_property(value, name)
    except Exception:
        return getattr(value, name)


def editor_properties(
    value: Any, requested_names: list[str] | None = None
) -> tuple[list[tuple[str, Any]], list[str]]:
    if not hasattr(value, "get_editor_property"):
        return [], list(requested_names or [])
    explicit = requested_names is not None
    names = (
        sorted(set(requested_names or []), key=str.casefold)
        if explicit
        else sorted(
            {name for name in dir(value) if not name.startswith("_")},
            key=str.casefold,
        )
    )
    properties: list[tuple[str, Any]] = []
    missing: list[str] = []
    for name in names:
        try:
            properties.append((name, _editor_property(value, name)))
        except Exception:
            if explicit:
                missing.append(name)
    return properties, missing


def _object_reference(value: Any) -> dict[str, Any] | None:
    if not hasattr(value, "get_path_name"):
        return None
    try:
        path = str(value.get_path_name() or "")
    except Exception:
        return None
    if not path:
        return None
    class_path = None
    try:
        class_value = value.get_class()
        if class_value is not None and hasattr(class_value, "get_path_name"):
            class_path = str(class_value.get_path_name() or "") or None
    except Exception:
        pass
    return {
        "kind": "object",
        "type": _type_name(value),
        "path": path,
        "class": class_path,
    }


def _known_semantic_value(value: Any) -> dict[str, Any] | None:
    type_name = _type_name(value)
    folded = type_name.casefold()
    if folded == "gameplaytag":
        try:
            tag = str(_semantic_field(value, "tag_name") or "")
        except Exception:
            tag = str(value or "")
        return {"kind": "gameplay_tag", "type": type_name, "tag": tag}
    if folded == "gameplaytagcontainer":
        try:
            values = _semantic_field(value, "gameplay_tags") or []
        except Exception:
            values = []
        tags = sorted({str(item) for item in values if str(item)}, key=str.casefold)
        return {"kind": "gameplay_tag_container", "type": type_name, "tags": tags}
    if folded == "primaryassetid":
        try:
            asset_type_value = _semantic_field(value, "primary_asset_type")
            asset_type = str(getattr(asset_type_value, "name", asset_type_value) or "")
            asset_name = str(_semantic_field(value, "primary_asset_name") or "")
        except Exception:
            return None
        return {
            "kind": "primary_asset_id",
            "type": asset_type,
            "name": asset_name,
            "id": f"{asset_type}:{asset_name}" if asset_type or asset_name else "",
        }
    return None


def serialize_value(
    value: Any,
    *,
    max_depth: int,
    max_items: int,
    _depth: int = 0,
    _seen: set[int] | None = None,
) -> dict[str, Any]:
    if value is None:
        return {"kind": "null", "value": None}
    if isinstance(value, bool):
        return {"kind": "boolean", "value": value}
    if isinstance(value, int):
        return {"kind": "integer", "value": value}
    if isinstance(value, float):
        return {
            "kind": "number" if math.isfinite(value) else "text",
            "value": value if math.isfinite(value) else str(value),
        }
    if isinstance(value, str):
        return {"kind": "string", "value": value}
    if isinstance(value, bytes):
        selected = value[:max_items]
        return {
            "kind": "bytes",
            "hex": selected.hex(),
            "truncated_count": max(0, len(value) - len(selected)),
        }
    if isinstance(value, enum.Enum):
        return {
            "kind": "enum",
            "type": _type_name(value),
            "value": str(value),
        }

    semantic = _known_semantic_value(value)
    if semantic is not None:
        return semantic
    reference = _object_reference(value)
    if reference is not None:
        return reference

    if _depth >= max_depth:
        return {"kind": "truncated", "type": _type_name(value)}
    seen = _seen if _seen is not None else set()
    identity = id(value)
    if identity in seen:
        return {"kind": "cycle", "type": _type_name(value)}
    seen.add(identity)
    try:
        if isinstance(value, Mapping) or callable(getattr(value, "items", None)):
            entries = list(value.items())
            entries.sort(key=lambda item: str(item[0]).casefold())
            selected = entries[:max_items]
            return {
                "kind": "map",
                "type": _type_name(value),
                "items": [
                    {
                        "key": serialize_value(
                            key,
                            max_depth=max_depth,
                            max_items=max_items,
                            _depth=_depth + 1,
                            _seen=seen,
                        ),
                        "value": serialize_value(
                            item,
                            max_depth=max_depth,
                            max_items=max_items,
                            _depth=_depth + 1,
                            _seen=seen,
                        ),
                    }
                    for key, item in selected
                ],
                "truncated_count": max(0, len(entries) - len(selected)),
            }

        is_builtin_collection = isinstance(value, (list, tuple, set, frozenset))
        is_sequence_wrapper = (
            not hasattr(value, "get_editor_property")
            and hasattr(value, "__iter__")
            and hasattr(value, "__len__")
            and not isinstance(value, (str, bytes, Mapping))
        )
        if is_builtin_collection or is_sequence_wrapper:
            items = list(value)
            if isinstance(value, (set, frozenset)):
                items.sort(key=lambda item: str(item).casefold())
            selected = items[:max_items]
            return {
                "kind": "array",
                "type": _type_name(value),
                "items": [
                    serialize_value(
                        item,
                        max_depth=max_depth,
                        max_items=max_items,
                        _depth=_depth + 1,
                        _seen=seen,
                    )
                    for item in selected
                ],
                "truncated_count": max(0, len(items) - len(selected)),
            }

        properties, _ = editor_properties(value)
        if properties:
            selected = properties[:max_items]
            return {
                "kind": "struct",
                "type": _type_name(value),
                "properties": {
                    name: serialize_value(
                        item,
                        max_depth=max_depth,
                        max_items=max_items,
                        _depth=_depth + 1,
                        _seen=seen,
                    )
                    for name, item in selected
                },
                "truncated_count": max(0, len(properties) - len(selected)),
            }
    finally:
        seen.remove(identity)

    return {"kind": "text", "type": _type_name(value), "value": str(value)}


def references_from_serialized(value: dict[str, Any]) -> list[dict[str, str]]:
    references = {
        (item["kind"], item["target"], item.get("field", "")): item
        for item in unique_references(value)
    }

    def visit(item: Any, field: str = "") -> None:
        if isinstance(item, dict):
            kind = str(item.get("kind", ""))
            if kind == "object" and item.get("path") and ":" in str(item["path"]):
                object_path = str(item["path"])
                path_field = f"{field}.path" if field else "path"
                references.pop(("asset", object_path, path_field), None)
                references[("object", object_path, path_field)] = {
                    "kind": "object",
                    "target": object_path,
                    "field": path_field,
                }
            elif kind == "gameplay_tag" and item.get("tag"):
                tag = str(item["tag"])
                references[("gameplay_tag", tag, field)] = {
                    "kind": "gameplay_tag",
                    "target": tag,
                    "field": field,
                }
            elif kind == "gameplay_tag_container":
                for index, tag_value in enumerate(item.get("tags", [])):
                    tag = str(tag_value)
                    child = f"{field}.tags[{index}]" if field else f"tags[{index}]"
                    references[("gameplay_tag", tag, child)] = {
                        "kind": "gameplay_tag",
                        "target": tag,
                        "field": child,
                    }
            elif kind == "primary_asset_id" and item.get("id"):
                identifier = str(item["id"])
                references[("primary_asset", identifier, field)] = {
                    "kind": "primary_asset",
                    "target": identifier,
                    "field": field,
                }
            for key in sorted(item, key=str.casefold):
                child = f"{field}.{key}" if field else str(key)
                visit(item[key], child)
        elif isinstance(item, list):
            for index, child_value in enumerate(item):
                child = f"{field}[{index}]" if field else f"[{index}]"
                visit(child_value, child)

    visit(value)
    return [references[key] for key in sorted(references)]
