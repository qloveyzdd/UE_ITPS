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
    items: list[dict[str, Any]], loaded: dict[str, Any]
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
            return _public_evidence(item, loaded)

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


def _unit(path: str) -> str:
    return "header" if path.casefold().endswith((".h", ".hpp")) else "cpp"


def _delegate_operations(
    function: dict[str, Any], references: dict[str, Any]
) -> list[dict[str, Any]]:
    symbol_types = {
        str(item["name"]): str(item.get("type", {}).get("name") or "")
        for item in function.get("parameter_facts", [])
    }
    results = []
    for call in references.get("call_details", []):
        api = str(call.get("target_name") or "")
        if api in {"Broadcast", "Execute", "ExecuteIfBound"}:
            operation = "publish"
        elif api.startswith(("Add", "Bind", "Create")):
            operation = "subscribe"
        else:
            continue
        segments = [str(part) for part in call.get("callee_path", [])]
        if len(segments) < 2:
            continue
        event_name = segments[-2]
        root = segments[0] if len(segments) >= 2 else None
        owner_type = (
            symbol_types.get(root or "")
            or str(function.get("owner") or "").split("::")[-1]
        )
        if not owner_type:
            continue
        callback = None
        for address in call.get("function_addresses", []):
            if address.get("owner_type"):
                callback = {
                    "owner_type": address["owner_type"],
                    "name": address["name"],
                    "qualified_name": address["qualified_name"],
                }
                break
        results.append(
            {
                "operation": operation,
                "api": api,
                "event": {
                    "owner_type": owner_type,
                    "name": event_name,
                    "qualified_name": f"{owner_type}::{event_name}",
                },
                "callback": callback,
                "evidence": {
                    "unit": _unit(function["file"]),
                    "line": int(call["line"]),
                },
            }
        )
    return results


def inspect_source_function(
    source_files: Path | Sequence[Path],
    function_name: str,
    engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = load_source_context(source_files, engine_override)
    parts = _callable_parts(loaded)
    relations = {item["usr"]: item for item in _relations(parts, loaded)}
    matches = []
    for item in parts:
        if item["role"] != "definition" or item["name"] != function_name:
            continue
        references = loaded["cpp_model"]["references"].get(item["usr"], {})
        external_symbols = []
        for symbol in references.get("external_symbols", []):
            public = {
                key: value for key, value in symbol.items() if key not in {"line"}
            }
            public["evidence"] = {
                "unit": _unit(item["file"]),
                "line": int(symbol["line"]),
            }
            external_symbols.append(public)
        matches.append(
            {
                "function_id": _function_id(item),
                "function": _public_callable(item),
                "relation": _public_relation(relations[item["usr"]]),
                "external_symbols": external_symbols,
                "delegate_operations": _delegate_operations(item, references),
                "syntax_flow": {
                    "calls": references.get("calls", []),
                    "controls": references.get("controls", []),
                },
            }
        )
    matches.sort(key=lambda match: match["function_id"])
    additional = []
    if not matches:
        additional.append(
            {
                "severity": "error",
                "code": "function-not-found",
                "selection": function_name,
                "message": "No matching C++ function definition was found",
            }
        )
    return source_result(
        "ue_inspect_cxx_function",
        loaded,
        {
            "selection": {"name": function_name},
            "match_count": len(matches),
            "matches": matches,
        },
        responsibility="Report syntax-derived external symbol candidates for selected C++ functions.",
        boundaries=[
            "Call and symbol targets are local syntax candidates and are not compiler-resolved.",
            "Called function bodies are not followed.",
        ],
        additional_problems=additional,
    )
