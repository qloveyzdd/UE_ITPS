from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .source_context import load_source_context, source_result
from .source_includes import rooted_path


def _function_id(item: dict[str, Any]) -> str:
    return "|".join(
        (
            str(item["kind"]),
            str(item.get("namespace") or ""),
            str(item.get("owner") or ""),
            str(item["name"]),
            str(item["signature"]),
        )
    )


def _public_evidence(item: dict[str, Any], loaded: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(item["file"]))
    result = rooted_path(path, loaded["project_root"], loaded["engine_root"])
    result["line"] = int(item["line"])
    if int(item.get("end_line", item["line"])) != int(item["line"]):
        result["end_line"] = int(item["end_line"])
    return result


def _public_callable(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": item["kind"],
        "namespace": item["namespace"],
        "qualified_name": item["qualified_name"],
        "owner": item["owner"],
        "name": item["name"],
        "parameters": item["parameters"],
        "signature": item["signature"],
        "qualifiers": item["qualifiers"],
        "role": item["role"],
    }


def _relations(
    items: list[dict[str, Any]], loaded: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item["usr"]), []).append(item)
    results = []
    for usr, group in sorted(grouped.items()):
        declarations = [item for item in group if item["role"] == "declaration"]
        definitions = [item for item in group if item["role"] == "definition"]
        if len(declarations) > 1 or len(definitions) > 1:
            status = "ambiguous"
        elif declarations and definitions:
            status = "matched"
        elif definitions:
            status = (
                "inline_definition"
                if definitions[0]["file"].endswith((".h", ".hpp"))
                else "source_only"
            )
        else:
            status = "declaration_only"

        def evidence(item: dict[str, Any]) -> dict[str, Any]:
            if loaded is not None:
                return _public_evidence(item, loaded)
            return {"path": item["file"], "line": item["line"]}

        results.append(
            {
                "usr": usr,
                "status": status,
                "declarations": [evidence(item) for item in declarations],
                "definitions": [evidence(item) for item in definitions],
            }
        )
    return results


def _public_relation(relation: dict[str, Any]) -> dict[str, Any]:
    return {key: relation[key] for key in ("status", "declarations", "definitions")}


def _callable_parts(loaded: dict[str, Any]) -> list[dict[str, Any]]:
    unit_files = {
        str(path.resolve()).replace("\\", "/").casefold()
        for path, _ in loaded["parsed_files"]
    }
    return [
        item
        for item in loaded["cpp_model"]["functions"]
        if item["file"] in unit_files
    ]


def list_source_functions(
    source_files: Path | Sequence[Path],
    engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = load_source_context(source_files, engine_override)
    parts = _callable_parts(loaded)
    relations = {item["usr"]: item for item in _relations(parts, loaded)}
    functions = []
    definition_usrs = {item["usr"] for item in parts if item["role"] == "definition"}
    for item in parts:
        if item["role"] != "definition" and item["usr"] in definition_usrs:
            continue
        relation = relations[item["usr"]]
        functions.append(
            {
                **_public_callable(item),
                "function_id": _function_id(item),
                "relation": relation["status"],
                "declarations": [
                    {"signature": item["signature"], "evidence": evidence}
                    for evidence in relation["declarations"]
                ],
                "definitions": [
                    {"signature": item["signature"], "evidence": evidence}
                    for evidence in relation["definitions"]
                ],
            }
        )
    return source_result(
        "ue_list_cxx_functions",
        loaded,
        {"functions": functions, "unresolved_declarations": [], "function_macros": []},
        responsibility="Index Tree-sitter C++ functions.",
        boundaries=[
            "Function identities are stable syntax keys; overload and declaration-definition relations are not compiler-bound."
        ],
    )
