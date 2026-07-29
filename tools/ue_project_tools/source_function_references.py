from __future__ import annotations

from pathlib import Path
from typing import Any

from .source_context import load_source_context, source_result
from .source_function_context import (
    _confirmed_type_names,
    _function_symbol_context,
    _qualified_type_facts,
    _visible_free_functions,
)
from .source_function_index import (
    _callable_parts,
    _public_callable,
    _public_relation,
    _relations,
)
from .source_function_symbols import (
    _bare_call_facts,
    _function_address_facts,
    _global_variable_facts,
    _member_call_facts,
    _public_external_symbols,
)
from .source_namespaces import observed_namespace_names


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
    "Symbol kinds are lexical candidate categories, not call, read, "
    "write, or ownership relations.",
    "Type names and receiver types are derived from locally visible "
    "declaration syntax; wrapped template types remain one expression.",
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
    "Called functions, inheritance, overloads, macros, and included "
    "source are not followed.",
]


def inspect_source_function(
    source_file: Path,
    function_name: str,
    *,
    engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = load_source_context(source_file, engine_override)
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
    ]
    if not candidates:
        return source_result(
            "ue-itps.cxx-function.v1",
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
        symbol_types, type_facts, local_names = (
            _function_symbol_context(candidate, loaded)
        )
        confirmed_type_names = _confirmed_type_names(
            loaded,
            type_facts,
        )
        observed_namespaces = {
            namespace
            for _, parsed in loaded["parsed_files"]
            for namespace in observed_namespace_names(
                parsed.get("namespace_scopes", [])
            )
        }
        callable_names = {
            item["name"] for item in loaded["parts"]
        }
        callable_qualified_names = {
            item["qualified_name"] for item in loaded["parts"]
        }
        free_function_names = {
            item["qualified_name"]
            for item in loaded["parts"]
            if item["kind"] == "free_function"
        }
        visible_free_functions = _visible_free_functions(
            candidate,
            loaded["parts"],
        )
        member_calls, member_call_indices = _member_call_facts(
            candidate,
            loaded,
            symbol_types,
            confirmed_type_names,
            observed_namespaces,
            free_function_names,
        )
        external_symbols = _public_external_symbols(
            [
                *type_facts,
                *_qualified_type_facts(
                    candidate,
                    loaded,
                    confirmed_type_names,
                ),
                *_global_variable_facts(
                    candidate,
                    loaded,
                    local_names,
                    confirmed_type_names,
                    observed_namespaces,
                ),
                *_bare_call_facts(
                    candidate,
                    loaded,
                    member_call_indices,
                    confirmed_type_names,
                    local_names,
                    visible_free_functions,
                ),
                *member_calls,
                *_function_address_facts(
                    candidate,
                    loaded,
                    callable_names,
                    callable_qualified_names,
                    local_names,
                    confirmed_type_names,
                    observed_namespaces,
                ),
            ]
        )
        matches.append(
            {
                "function_id": candidate["function_id"],
                "function": _public_callable(candidate),
                "relation": _public_relation(
                    relations[candidate["_identity"]]
                ),
                "external_symbols": external_symbols,
            }
        )
    return source_result(
        "ue-itps.cxx-function.v1",
        loaded,
        {
            "selection": {"name": function_name},
            "match_count": len(matches),
            "matches": matches,
        },
        responsibility=_RESPONSIBILITY,
        boundaries=_BOUNDARIES,
    )
