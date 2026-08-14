from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .source_context import load_source_context, source_result
from .source_function_index import (
    _callable_parts,
    _function_id,
    _public_callable,
    _public_relation,
    _relations,
)


def _unit(path: str) -> str:
    return "header" if path.casefold().endswith((".h", ".hpp")) else "cpp"


def _delegate_operations(
    function: dict[str, Any], references: dict[str, Any]
) -> list[dict[str, Any]]:
    symbol_types = {
        str(item["name"]): re.sub(
            r"\s*[*&]+\s*$", "", str(item["type_expression"])
        ).split("::")[-1]
        for item in function.get("parameter_facts", [])
    }
    results = []
    for call in references.get("call_details", []):
        api = str(call.get("target_name") or "")
        if api in {"Broadcast", "Execute", "ExecuteIfBound"}:
            operation = "publish"
        elif re.match(r"^(?:Add|Bind|Create|Register|Subscribe|Listen)", api):
            operation = "subscribe"
        else:
            continue
        segments = [part for part in str(call["callee"]).split(".") if part]
        if len(segments) < 2:
            continue
        event_name = segments[-2]
        root = segments[-3] if len(segments) >= 3 else None
        owner_type = (
            symbol_types.get(root or "")
            or str(function.get("owner") or "").split("::")[-1]
        )
        if not owner_type:
            continue
        callback = None
        for argument in call.get("arguments", []):
            match = re.search(
                r"&(?P<owner>[A-Za-z_]\w*)::(?P<name>[A-Za-z_]\w*)", argument
            )
            if match:
                callback = {
                    "owner_type": match.group("owner"),
                    "name": match.group("name"),
                    "qualified_name": f"{match.group('owner')}::{match.group('name')}",
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
    source_file: Path,
    function_name: str,
    engine_override: Path | None = None,
    compilation_database: Path | None = None,
) -> dict[str, Any]:
    loaded = load_source_context(source_file, engine_override, compilation_database)
    parts = _callable_parts(loaded)
    relations = {item["usr"]: item for item in _relations(parts, loaded)}
    matches = []
    for item in parts:
        if item["role"] != "definition" or item["name"] != function_name:
            continue
        references = loaded["clang_model"]["references"].get(item["usr"], {})
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
        responsibility="Report Clang-confirmed external symbols for selected C++ functions.",
        boundaries=["Called function bodies are not followed."],
        additional_problems=additional,
    )
