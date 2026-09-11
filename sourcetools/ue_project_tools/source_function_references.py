from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .source_context import load_source_context, source_result
from .source_priority import FunctionPriorityView, detailed_syntax_flow, validate_view, view_metadata
from .ue_cpp_conventions import UE_DELEGATE_CONTRACT_REVISION


def _function_id(item: dict[str, Any]) -> str:
    return "|".join(
        (
            str(item["kind"]),
            str(item.get("namespace") or ""),
            str(item.get("owner") or ""),
            str(item["name"]),
            str(item["signature"]),
            f"{_unit(item['file'])}:{item['line']}:{item['column']}",
        )
    )


def _matches_function_selector(item: dict[str, Any], selector: str) -> bool:
    if "::" in selector:
        return selector in {item["qualified_name"], item.get("source_qualified_name")}
    return item["name"] == selector


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


def list_source_functions(
    source_files: Path | Sequence[Path], engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = load_source_context(source_files, engine_override)
    return _list_functions_from_context(loaded)


def _list_functions_from_context(loaded: dict[str, Any]) -> dict[str, Any]:
    functions = [{
        "function_id": _function_id(item),
        **{key: item[key] for key in ("kind", "name", "namespace", "owner", "qualified_name", "signature")},
        "source_qualified_name": item.get("source_qualified_name", item["qualified_name"]),
        "evidence": {"unit": _unit(item["file"]), "line": item["line"],
                     "column": item["column"], "end_line": item["end_line"]},
    } for item in _callable_parts(loaded) if item["role"] == "definition"]
    return source_result(
        "ue_list_cxx_functions", loaded, {"functions": functions},
        responsibility="List every C++ function definition in the selected files for navigation.",
        boundaries=[
            "Owner type definitions need not be visible in the selected files.",
            "Overloads and conditional definitions remain separate occurrences.",
            "Source spellings are retained; injected class names need local declaration evidence to normalize.",
            "Function IDs are scoped to the selected file set and parser output, not persistent entity IDs.",
        ],
    )


def inspect_source_function(
    source_files: Path | Sequence[Path],
    function_name: str,
    engine_override: Path | None = None,
    *,
    include_syntax_flow: bool = False,
    view: str = "full",
    focus: Sequence[str] = (),
) -> dict[str, Any]:
    validate_view(view, focus)
    loaded = load_source_context(source_files, engine_override)
    return _inspect_function_from_context(
        loaded, function_name, include_syntax_flow=include_syntax_flow, view=view, focus=focus,
    )


def _inspect_function_from_context(
    loaded: dict[str, Any], function_name: str, *, include_syntax_flow: bool = False,
    view: str = "full", focus: Sequence[str] = (),
) -> dict[str, Any]:
    priority = FunctionPriorityView(loaded["cpp_model"], view, focus) if view != "full" else None
    parts = _callable_parts(loaded)
    matches = []
    for item in parts:
        if item["role"] != "definition" or not _matches_function_selector(
            item, function_name
        ):
            continue
        references = loaded["cpp_model"]["references"][item["occurrence_id"]]
        external_symbols = []
        for symbol in references.get("external_symbols", []):
            public = {
                key: value for key, value in symbol.items() if key not in {"line", "start_offset"}
            }
            public["evidence"] = {
                "unit": _unit(item["file"]),
                "line": int(symbol["line"]),
            }
            external_symbols.append(public)
        match = {
            "function_id": _function_id(item),
            "external_symbols": external_symbols,
            "delegate_operations": references["delegate_operations"],
        }
        if priority is not None:
            del match["external_symbols"]
            match.update(priority.project(item, references, _unit(item["file"])))
        if include_syntax_flow:
            match["syntax_flow"] = detailed_syntax_flow(references) if priority is not None else {
                "calls": references.get("calls", []),
                "controls": references.get("controls", []),
            }
        matches.append(match)
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
            **({"view": view_metadata(view, focus)} if priority is not None else {}),
            "delegate_contract_revision": UE_DELEGATE_CONTRACT_REVISION,
            "match_count": len(matches),
            "matches": matches,
        },
        responsibility=("Prioritize syntax candidates; display groups do not establish semantic relationships."
                        if priority is not None else
                        "Report syntax-derived external symbol candidates for selected C++ functions."),
        boundaries=[
            "Call and symbol targets are local syntax candidates and are not compiler-resolved.",
            "Called function bodies are not followed.",
        ],
        additional_problems=additional,
    )
