from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .source_context import load_source_context, source_result
from .ue_cpp_conventions import ue_delegate_operation


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
        operation = ue_delegate_operation(api)
        if operation is None:
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
                "message": "No matching C++ function definition was found",
            }
        )
    return source_result(
        "ue_inspect_cxx_function",
        loaded,
        {
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
