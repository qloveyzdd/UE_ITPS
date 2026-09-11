from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .source_context import load_source_context, source_result
from .source_priority import definition_view, validate_view


def _unit(path: str) -> str:
    return "header" if path.casefold().endswith((".h", ".hpp")) else "cpp"


def _evidence(item: dict[str, Any]) -> dict[str, Any]:
    result = {"unit": _unit(str(item["file"])), "line": int(item.get("annotation_line", item["line"]))}
    if item.get("end_line") and int(item["end_line"]) != result["line"]:
        result["end_line"] = int(item["end_line"])
    return result


def _basic_type(item: dict[str, Any]) -> dict[str, Any]:
    return {
        **{key: item[key] for key in (
            "kind", "name", "namespace", "qualified_name", "owner", "role"
        )},
        "macros": list(item.get("macros", [])),
        "evidence": _evidence(item),
    }


def list_source_types(
    source_files: Path | Sequence[Path],
    engine_override: Path | None = None,
    *,
    view: str = "full",
    focus: Sequence[str] = (),
) -> dict[str, Any]:
    validate_view(view, focus)
    loaded = load_source_context(source_files, engine_override)
    return _list_types_from_context(loaded, view=view, focus=focus)


def _list_types_from_context(
    loaded: dict[str, Any], *, view: str = "full", focus: Sequence[str] = (),
) -> dict[str, Any]:
    model = loaded["cpp_model"]
    types = [item for item in model["types"] if item["role"] == "definition"]
    type_namespaces = {item["qualified_name"]: item["namespace"] for item in model["types"]}
    groups = {
        "classes": [_basic_type(item) for item in types if item["kind"] == "class"],
        "structs": [_basic_type(item) for item in types if item["kind"] in {"struct", "union"}],
        "enums": [_basic_type(item) for item in types if item["kind"] == "enum"],
        "global_variables": [
            {
                **{key: item[key] for key in (
                    "name", "qualified_name", "type_expression", "role", "linkage"
                )},
                "namespace": type_namespaces.get(
                    item["qualified_name"].rpartition("::")[0], item.get("namespace")
                ),
                "macros": list(item.get("macros", [])),
                "evidence": _evidence(item),
            }
            for item in model["variables"] if item["role"] == "definition"
        ],
        "free_functions": [
            {
                **{key: item[key] for key in (
                    "name", "namespace", "qualified_name", "signature", "role"
                )},
                "linkage": item.get("linkage", "external"),
                "evidence": _evidence(item),
            }
            for item in model["functions"]
            if item["kind"] == "free_function" and item["role"] == "definition"
        ],
        "macros": [
            {"name": item["name"], "parameters": item["parameters"], "evidence": _evidence(item)}
            for item in model["macro_definitions"]
        ],
    }
    for group in groups.values():
        group.sort(key=lambda item: (item["evidence"]["unit"], item["evidence"]["line"], item["name"]))
    if view != "full":
        groups = {"view": definition_view(groups, view, focus), **groups}
    return source_result(
        "ue_list_cxx_types", loaded, groups,
        responsibility="List basic definition information from the selected files.",
        boundaries=[
            "Forward declarations, extern declarations, function prototypes, and referenced entities are excluded.",
            "Type members, bases, enumerators, and interface inference require a separate inspection.",
            "Macros lists local #define directives without replacement bodies; attached UE annotations remain on types.",
            "Conditional branches are listed syntactically without preprocessing.",
            "Static member variable definitions retain their qualified identities in global_variables.",
            "Supported native GameplayTag definitions are projected as FNativeGameplayTag globals.",
        ],
    )
