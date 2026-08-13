from __future__ import annotations

from pathlib import Path
from typing import Any

from .source_context import load_source_context, source_result
from .source_function_context import (
    _confirmed_type_names,
    _function_symbol_context,
)
from .source_function_index import (
    _callable_parts,
    _public_callable,
    _public_relation,
    _relations,
)
from .source_function_symbols import _delegate_operations


_RESPONSIBILITY = (
    "Report external symbols referenced by all definitions "
    "matching one function name."
)

_BOUNDARIES = [
    "Namespace is part of each function's local identity, qualified "
    "name, declaration-definition relation, and function_id within "
    "the selected source pair.",
    "Method owners retain the full lexical enclosing class chain "
    "without repeating the namespace.",
    "function_id is a compact source-pair identity and is not a "
    "project-level stable ID.",
    "External means outside the selected function semantic unit, "
    "including symbols declared in the selected file or its companion.",
    "Symbol identities, call targets, and receiver owners come from the "
    "active Clang translation unit; kinds remain navigation categories, "
    "not read, write, or ownership relations.",
    "A bare call is a member_call only for a matching current-class "
    "method, or a free_function only for a matching visible declaration "
    "in the selected source pair; otherwise it remains unknown.",
    "A scope-qualified call is a member_call when its receiver is a "
    "confirmed type, or a free_function when its qualifier is an "
    "observed Namespace with a matching declaration; otherwise it "
    "remains unknown.",
    "A namespace-qualified reference is a global_variable only when "
    "its fully qualified name matches a local variable declaration, "
    "or its name has conservative G* spelling evidence; type-qualified, "
    "member-shaped, unresolved, and other unmatched accesses remain "
    "unknown.",
    "Function addresses and callback targets are distinguished only "
    "when local callable declarations or recognized callback API syntax "
    "provide evidence; callable matching resolves owner spellings "
    "through the current lexical Namespace, and owner_type is present "
    "only for confirmed type qualifiers.",
    "Delegate operations preserve a resolved event owner and member for "
    "recognized publish or subscription APIs; unresolved receiver chains "
    "are not promoted to delegate semantics.",
    "Called functions, inheritance, overloads, macros, and included "
    "source are not followed.",
]


def _clang_definition(
    candidate: dict[str, Any],
    loaded: dict[str, Any],
) -> dict[str, Any] | None:
    path = str(candidate["_path"].resolve()).replace("\\", "/").casefold()
    return next(
        (
            item
            for item in loaded["clang_model"]["functions"]
            if item["role"] == "definition"
            and item["file"] == path
            and item["name"] == candidate["name"]
            and item["qualified_name"] == candidate["qualified_name"]
            and item["line"] == int(candidate["evidence"]["line"])
        ),
        None,
    )


def _clang_external_symbols(
    candidate: dict[str, Any],
    loaded: dict[str, Any],
) -> list[dict[str, Any]]:
    definition = _clang_definition(candidate, loaded)
    if definition is None:
        return []
    unit = (
        "header"
        if candidate["_path"].suffix.casefold() in {".h", ".hpp"}
        else "cpp"
    )
    return [
        {
            **{
                key: value
                for key, value in item.items()
                if key in {"kind", "spelling", "owner_type"}
            },
            "evidence": {"unit": unit, "line": int(item["line"])},
        }
        for item in loaded["clang_model"]["references"]
        .get(definition["usr"], {})
        .get("external_symbols", [])
    ]


def inspect_source_function(
    source_file: Path,
    function_name: str,
    *,
    engine_override: Path | None = None,
    compilation_database: Path | None = None,
) -> dict[str, Any]:
    loaded = load_source_context(
        source_file, engine_override, compilation_database
    )
    loaded["parts"] = _callable_parts(
        loaded["parsed_files"],
        loaded["project_root"],
        loaded["engine_root"],
    )
    candidates = [
        part
        for part in loaded["parts"]
        if part["role"] == "definition"
        and part["name"] == function_name
        and _clang_definition(part, loaded) is not None
    ]
    if not candidates:
        return source_result(
            "ue_inspect_cxx_function",
            loaded,
            {
                "selection": {"name": function_name},
                "match_count": 0,
                "matches": [],
            },
            responsibility=_RESPONSIBILITY,
            boundaries=_BOUNDARIES,
            additional_problems=[
                {
                    "severity": "error",
                    "code": "function-not-found",
                    "selection": function_name,
                    "message": (
                        "No matching function definition was found"
                    ),
                }
            ],
        )
    relations = {
        (
            item["callable"]["kind"],
            item["callable"]["namespace"] or "",
            item["callable"]["owner"] or "",
            item["callable"]["name"],
            tuple(
                tuple(group)
                for group in item["callable"]["parameter_signature"]
            ),
            tuple(item["callable"]["identity_qualifiers"]),
        ): item
        for item in _relations(loaded["parts"])
    }
    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        symbol_types, type_facts, _local_names = (
            _function_symbol_context(candidate, loaded)
        )
        confirmed_type_names = _confirmed_type_names(
            loaded,
            type_facts,
        )
        external_symbols = _clang_external_symbols(candidate, loaded)
        matches.append(
            {
                "function_id": candidate["function_id"],
                "function": _public_callable(candidate),
                "relation": _public_relation(
                    relations[candidate["_identity"]]
                ),
                "external_symbols": external_symbols,
                "delegate_operations": _delegate_operations(
                    candidate,
                    loaded,
                    symbol_types,
                    confirmed_type_names,
                ),
                "syntax_flow": _syntax_flow(candidate, loaded),
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
        responsibility=_RESPONSIBILITY,
        boundaries=_BOUNDARIES,
    )


def _syntax_flow(candidate: dict[str, Any], loaded: dict[str, Any]) -> dict[str, Any]:
    parsed = loaded["parsed_by_path"].get(candidate["_path"])
    if not parsed:
        return {"calls": [], "controls": []}
    syntax_functions = parsed.get("syntax_tree", {}).get("functions", [])
    line = int(candidate["evidence"]["line"])
    match = next(
        (
            item
            for item in syntax_functions
            if item["has_body"]
            and item["name"].split("::")[-1] == candidate["name"]
            and item["location"]["line"] == line
        ),
        None,
    )
    if match is None:
        return {"calls": [], "controls": []}
    return {"calls": list(match["calls"]), "controls": list(match["controls"])}
