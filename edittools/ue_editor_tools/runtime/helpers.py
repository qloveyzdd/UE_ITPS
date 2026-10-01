from __future__ import annotations

from typing import Any


def editor_property(value: Any, name: str, default: Any = None) -> Any:
    """Read an Unreal editor property while tolerating unavailable fields."""
    if value is None:
        return default
    try:
        return value.get_editor_property(name)
    except Exception:
        return default


def object_path(value: Any, *, fallback_to_string: bool = True) -> str | None:
    """Return a stable Unreal object path, if one can be observed."""
    if value is None:
        return None
    getter = getattr(value, "get_path_name", None)
    if getter is not None:
        try:
            path = str(getter())
        except Exception:
            path = ""
        if path and path != "None":
            return path
    if not fallback_to_string:
        return None
    text = str(value)
    return text if text and text != "None" else None


def class_path(value: Any) -> str | None:
    """Return the observed class path for an Unreal object."""
    try:
        return object_path(value.get_class())
    except Exception:
        return None


def scalar(value: Any) -> Any:
    """Convert common Unreal values into JSON-compatible scalar structures."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [scalar(item) for item in value]
    if hasattr(value, "x") and hasattr(value, "y") and hasattr(value, "z"):
        result = {"x": float(value.x), "y": float(value.y), "z": float(value.z)}
        if hasattr(value, "w"):
            result["w"] = float(value.w)
        return result
    path = object_path(value)
    if path:
        return path
    return str(value)
