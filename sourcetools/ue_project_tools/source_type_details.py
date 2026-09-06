from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .source_context import load_source_context, source_result
from .source_type_facts import _evidence


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
        "kind": item["kind"],
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


def inspect_source_type(
    source_files: Path | Sequence[Path],
    type_name: str,
    engine_override: Path | None = None,
) -> dict[str, Any]:
    if not type_name.strip():
        raise ValueError("Type qualified name must not be empty")
    loaded = load_source_context(source_files, engine_override)
    model = loaded["cpp_model"]
    types = [item for item in model["types"]
             if item["kind"] in {"class", "struct", "union"} and item["role"] == "definition"]
    known_names = {item["qualified_name"] for item in types}
    matches = []
    for item in types:
        if item["qualified_name"] != type_name:
            continue
        match = _compound(item)
        reasons = []
        if any(macro.startswith("UINTERFACE(") for macro in item.get("macros", [])):
            reasons.append("UINTERFACE macro")
        if "UInterface" in item["base_types"]:
            reasons.append("derives from UInterface")
        prefix = item["qualified_name"][:-len(item["name"])]
        if item["name"].startswith("I") and prefix + "U" + item["name"][1:] in known_names:
            reasons.append("paired I/U interface naming")
        match["interface_candidate_reasons"] = reasons
        match["member_functions"] = [
            _member_function(function) for function in model["functions"]
            if function["kind"] == "method" and function["role"] == "definition"
            and function["qualified_name"] == f"{type_name}::{function['name']}"
        ]
        matches.append(match)
    return source_result(
        "ue_inspect_cxx_type", loaded, {"matches": matches},
        responsibility="Inspect class or struct definitions matching one exact qualified name.",
        boundaries=[
            "Only direct members of the selected type are expanded; nested and base types are not followed.",
            "Member definitions are restricted to the explicitly selected files.",
            "Interface candidate reasons are local syntax evidence, not UHT conclusions.",
        ],
        additional_problems=[] if matches else [{
            "severity": "error", "code": "type-not-found",
            "message": f"No class or struct definition matches {type_name}",
        }],
    )
