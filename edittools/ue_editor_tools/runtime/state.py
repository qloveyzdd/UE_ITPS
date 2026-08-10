from __future__ import annotations

from typing import Any

import unreal


def _package_names(values: Any) -> list[str]:
    names: list[str] = []
    for value in values or []:
        if hasattr(value, "get_path_name"):
            names.append(str(value.get_path_name()))
        else:
            names.append(str(value))
    return sorted(set(names), key=str.casefold)


def dirty_packages() -> list[str]:
    values: list[Any] = []
    for method_name in ("get_dirty_content_packages", "get_dirty_map_packages"):
        method = getattr(unreal.EditorLoadingAndSavingUtils, method_name, None)
        if method is not None:
            try:
                values.extend(method())
            except Exception:
                pass
    return _package_names(values)


def editor_state() -> dict[str, Any]:
    return {
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "project_dir": unreal.Paths.convert_relative_path_to_full(
            unreal.Paths.project_dir()
        ).replace("\\", "/"),
        "dirty_packages": dirty_packages(),
        "capabilities": {
            "toolset_registry": hasattr(unreal, "ToolsetRegistry"),
            "gameplay_tags_toolset": hasattr(unreal, "GameplayTagsToolset"),
            "blueprint_graph_editor": hasattr(unreal, "BlueprintGraphEditor"),
        },
    }
