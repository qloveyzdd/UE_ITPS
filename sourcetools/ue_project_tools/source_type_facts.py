from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .source_context import load_source_context, source_result


def _unit(path: str) -> str:
    return "header" if path.casefold().endswith((".h", ".hpp")) else "cpp"


def _evidence(item: dict[str, Any]) -> dict[str, Any]:
    result = {"unit": _unit(str(item["file"])), "line": int(item["line"])}
    if item.get("end_line") and int(item["end_line"]) != int(item["line"]):
        result["end_line"] = int(item["end_line"])
    return result


def _member_anchors(item: dict[str, Any]) -> list[dict[str, Any]]:
    members = []
    for field in item.get("fields", []):
        projection = {**field, "file": item["file"]}
        members.append(
            {
                "kind": "variable",
                "name": field["name"],
                "type_expression": field["type_expression"],
                "macros": list(field.get("macros", [])),
                "evidence": _evidence(projection),
            }
        )
    for method in item.get("methods", []):
        projection = {**method, "file": item["file"]}
        members.append(
            {
                "kind": "function",
                "name": method["name"],
                "signature": method["signature"],
                "macros": list(method.get("macros", [])),
                "evidence": _evidence(projection),
            }
        )
    return sorted(members, key=lambda member: member["evidence"]["line"])


def _compound(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item["name"],
        "namespace": item["namespace"],
        "qualified_name": item["qualified_name"],
        "owner": item["owner"],
        "role": item["role"],
        "base_types": item["base_types"],
        "macros": list(item.get("macros", [])),
        "member_anchors": _member_anchors(item),
        "evidence": _evidence(item),
    }


def _member_function(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item["name"],
        "namespace": item["namespace"],
        "qualified_name": item["qualified_name"],
        "owner": item["owner"],
        "signature": item["signature"],
        "macros": list(item.get("macros", [])),
        "evidence": _evidence(item),
    }


def list_source_types(
    source_files: Path | Sequence[Path],
    engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = load_source_context(source_files, engine_override)
    model = loaded["cpp_model"]
    unit_files = {
        str(path.resolve()).replace("\\", "/").casefold()
        for path, _ in loaded["parsed_files"]
    }
    types = [item for item in model["types"] if item["file"] in unit_files]
    classes = [
        _compound(item)
        for item in types
        if item["kind"] == "class" and item["role"] == "definition"
    ]
    structs = [
        _compound(item)
        for item in types
        if item["kind"] in {"struct", "union"} and item["role"] == "definition"
    ]
    enums = [
        {
            "kind": "enum",
            "name": item["name"],
            "namespace": item["namespace"],
            "qualified_name": item["qualified_name"],
            "owner": item["owner"],
            "role": item["role"],
            "scoped": item["scoped"],
            "macros": list(item.get("macros", [])),
            "evidence": _evidence(item),
        }
        for item in types
        if item["kind"] == "enum" and item["role"] == "definition"
    ]
    interface_candidates = []
    known_names = {item["name"] for item in [*classes, *structs]}
    for item in [*classes, *structs]:
        reasons = []
        if "UINTERFACE()" in item["macros"]:
            reasons.append("UINTERFACE macro")
        if "UInterface" in item["base_types"]:
            reasons.append("derives from UInterface")
        if item["name"].startswith("I") and f"U{item['name'][1:]}" in known_names:
            reasons.append("paired I/U interface naming")
        if not reasons:
            continue
        interface_candidates.append(
            {
                "name": item["name"],
                "qualified_name": item["qualified_name"],
                "owner": item["owner"],
                "declaration_kind": ("struct" if item in structs else "class"),
                "reasons": reasons,
                "evidence": item["evidence"],
            }
        )
    globals_ = [
        {
            "name": item["name"],
            "namespace": (
                item["qualified_name"].rsplit("::", 1)[0]
                if "::" in item["qualified_name"]
                else None
            ),
            "qualified_name": item["qualified_name"],
            "type_expression": item["type_expression"],
            "role": item["role"],
            "linkage": item["linkage"],
            "macros": list(item.get("macros", [])),
            "evidence": _evidence(item),
        }
        for item in model["variables"]
        if item["file"] in unit_files and item["role"] == "definition"
    ]
    free_functions = [
        {
            "name": item["name"],
            "namespace": item["namespace"],
            "qualified_name": item["qualified_name"],
            "signature": item["signature"],
            "role": item["role"],
            "linkage": item.get("linkage", "external"),
            "evidence": _evidence(item),
        }
        for item in model["functions"]
        if item["file"] in unit_files
        and item["kind"] == "free_function"
        and item["role"] == "definition"
    ]
    member_functions = [
        _member_function(item)
        for item in model["functions"]
        if item["file"] in unit_files
        and item["kind"] == "method"
        and item["role"] == "definition"
    ]

    def sort_key(item: dict[str, Any]) -> tuple[str, int, str]:
        return (
            str(item["evidence"]["unit"]),
            int(item["evidence"]["line"]),
            str(item["qualified_name"]),
        )

    for group in (
        classes,
        structs,
        enums,
        interface_candidates,
        globals_,
        free_functions,
        member_functions,
    ):
        group.sort(key=sort_key)
    return source_result(
        "ue_list_cxx_types",
        loaded,
        {
            "classes": classes,
            "structs": structs,
            "enums": enums,
            "interface_candidates": interface_candidates,
            "global_variables": globals_,
            "free_functions": free_functions,
            "member_functions": member_functions,
            "unresolved_declarations": [],
        },
        responsibility="Index Tree-sitter C++ definitions and members created by the selected files.",
        boundaries=[
            "Forward declarations, extern variable declarations, and function prototypes are excluded.",
            "Referenced types, variables, and functions are not emitted as entities created by the selected files.",
            "Definition identity, members, and linkage are syntax projections rather than compiler semantic facts.",
            "UE reflection macros are read from local source text and attached by source adjacency.",
        ],
    )
