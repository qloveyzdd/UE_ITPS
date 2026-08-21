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


def _macro_expression(item: dict[str, Any]) -> str:
    return str(item.get("expression") or item["name"])


def _adjacent_macros(
    item: dict[str, Any],
    macros: list[dict[str, Any]],
    text_by_file: dict[str, str],
) -> list[str]:
    file_key = str(item["file"])
    line = int(item["line"])
    source_lines = text_by_file.get(file_key, "").splitlines()
    candidates = [
        macro
        for macro in macros
        if macro["file"] == file_key
        and int(macro["end_line"]) < line
        and macro["name"]
        in {
            "UCLASS",
            "USTRUCT",
            "UENUM",
            "UINTERFACE",
            "UFUNCTION",
            "UPROPERTY",
            "UDELEGATE",
        }
    ]
    results: list[dict[str, Any]] = []
    cursor_line = line
    for macro in reversed(candidates):
        end_line = int(macro["end_line"])
        if any(
            source_lines[index - 1].strip()
            for index in range(end_line + 1, cursor_line)
            if 0 < index <= len(source_lines)
        ):
            break
        results.append(macro)
        cursor_line = int(macro["line"])
    return [_macro_expression(item) for item in reversed(results)]


def _member_anchors(
    item: dict[str, Any],
    macros: list[dict[str, Any]],
    text_by_file: dict[str, str],
) -> list[dict[str, Any]]:
    members = []
    for field in item.get("fields", []):
        projection = {**field, "file": item["file"]}
        members.append(
            {
                "kind": "variable",
                "name": field["name"],
                "type_expression": field["type_expression"],
                "macros": _adjacent_macros(projection, macros, text_by_file),
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
                "macros": _adjacent_macros(projection, macros, text_by_file),
                "evidence": _evidence(projection),
            }
        )
    return sorted(members, key=lambda member: member["evidence"]["line"])


def _compound(
    item: dict[str, Any],
    macros: list[dict[str, Any]],
    text_by_file: dict[str, str],
) -> dict[str, Any]:
    return {
        "name": item["name"],
        "namespace": item["namespace"],
        "qualified_name": item["qualified_name"],
        "owner": item["owner"],
        "role": item["role"],
        "base_types": item["base_types"],
        "macros": _adjacent_macros(item, macros, text_by_file),
        "member_anchors": _member_anchors(item, macros, text_by_file),
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
    text_by_file = {
        str(path.resolve()).replace("\\", "/").casefold(): parsed["text"]
        for path, parsed in loaded["parsed_files"]
    }
    macros = [item for item in model["macros"] if item["file"] in unit_files]
    types = [item for item in model["types"] if item["file"] in unit_files]
    classes = [
        _compound(item, macros, text_by_file)
        for item in types
        if item["kind"] == "class"
    ]
    structs = [
        _compound(item, macros, text_by_file)
        for item in types
        if item["kind"] in {"struct", "union"}
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
            "macros": _adjacent_macros(item, macros, text_by_file),
            "evidence": _evidence(item),
        }
        for item in types
        if item["kind"] == "enum"
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
            "macros": _adjacent_macros(item, macros, text_by_file),
            "evidence": _evidence(item),
        }
        for item in model["variables"]
        if item["file"] in unit_files
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
        if item["file"] in unit_files and item["kind"] == "free_function"
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
            "unresolved_declarations": [],
        },
        responsibility="Index Tree-sitter C++ declarations and definitions.",
        boundaries=[
            "Declaration identity, roles, members, and linkage are syntax projections rather than compiler semantic facts.",
            "UE reflection macros are read from local source text and attached by source adjacency.",
        ],
    )
