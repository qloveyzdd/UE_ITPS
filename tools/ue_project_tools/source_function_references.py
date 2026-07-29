from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .source_context import load_source_context, source_result
from .source_controls import _member_chain_start
from .source_declarations import _classify_declaration
from .source_fact_common import (
    _declaration_variables,
    _source_declaration_facts,
    _statement_start,
)
from .source_function_index import (
    _callable_parts,
    _public_callable,
    _public_relation,
    _relations,
)
from .source_tokens import (
    Token,
    _raw,
    _raw_from_values,
    _split_arguments,
    lex_source,
    token_pairs,
)


def _primary_type_name(type_expression: str) -> str | None:
    identifiers = [
        token.value
        for token in lex_source(type_expression)
        if token.kind == "identifier"
        and token.value
        not in {
            "auto",
            "class",
            "const",
            "enum",
            "struct",
            "typename",
            "volatile",
        }
    ]
    return identifiers[0] if identifiers else None


def _canonical_type_expression(type_expression: str) -> str:
    tokens = [
        token
        for token in lex_source(type_expression)
        if token.value
        not in {
            "class",
            "const",
            "struct",
            "typename",
            "volatile",
            "*",
            "&",
            "&&",
        }
    ]
    rendered = _raw_from_values(tokens)
    rendered = re.sub(r"\s*<\s*", "<", rendered)
    rendered = re.sub(r"\s*>\s*", ">", rendered)
    rendered = re.sub(r"\s*,\s*", ", ", rendered)
    return rendered


def _parameter_symbol_types(part: dict[str, Any]) -> dict[str, str]:
    tokens = lex_source(part["parameters"])
    forward, _ = token_pairs(tokens)
    symbols: dict[str, str] = {}
    for start, end in _split_arguments(tokens, 0, len(tokens)):
        classification = _classify_declaration(
            tokens, forward, start, end
        )
        if classification["kind"] != "variable":
            continue
        name_index = int(classification["name_index"])
        type_expression = _raw_from_values(tokens[start:name_index])
        canonical_type = _canonical_type_expression(type_expression)
        if canonical_type:
            symbols[str(classification["name"])] = canonical_type
    return symbols


def _function_symbol_types(
    part: dict[str, Any],
    loaded: dict[str, Any],
) -> tuple[dict[str, str], set[str]]:
    symbols = _parameter_symbol_types(part)
    type_names = set(symbols.values())
    variables, _ = _declaration_variables(
        loaded["parsed_by_path"][part["_path"]],
        part["_path"],
        part["_body_range"][0],
        part["_body_range"][1],
        scope="local",
        owner=part["owner"],
        project_root=loaded["project_root"],
        engine_root=loaded["engine_root"],
    )
    shadowed_member_names = {
        *symbols,
        *(variable["name"] for variable in variables),
    }
    parsed = loaded["parsed_by_path"][part["_path"]]
    tokens: list[Token] = parsed["tokens"]
    start, end = part["_body_range"]
    referenced_names = {
        token.value
        for token in tokens[start:end]
        if token.kind == "identifier"
    }
    variables.extend(
        item
        for item in _source_declaration_facts(loaded)[0]
        if item["scope"] == "member"
        and item.get("owner") == part["owner"]
        and item["name"] in referenced_names
        and item["name"] not in shadowed_member_names
    )
    for variable in variables:
        if any(
            token.value in {".", "->"}
            for token in lex_source(variable["type_expression"])
        ):
            continue
        canonical_type = _canonical_type_expression(
            variable["type_expression"]
        )
        if not canonical_type:
            continue
        symbols[variable["name"]] = canonical_type
        outer_type = _primary_type_name(canonical_type)
        if (
            outer_type
            and outer_type[0].isupper()
            and not outer_type.isupper()
        ):
            type_names.add(canonical_type)
    for semicolon in range(start, end):
        if tokens[semicolon].value != ";":
            continue
        statement_start = _statement_start(tokens, start, semicolon)
        classification = _classify_declaration(
            tokens,
            parsed["forward"],
            statement_start,
            semicolon,
        )
        if classification["kind"] != "callable":
            continue
        name_index = int(classification["name_index"])
        if (
            name_index <= statement_start
            or name_index + 1 >= semicolon
            or tokens[name_index + 1].value not in {"(", "{"}
            or tokens[name_index - 1].value in {".", "->", "::"}
            or any(
                tokens[index].value in {".", "->"}
                for index in range(statement_start, name_index)
            )
        ):
            continue
        canonical_type = _canonical_type_expression(
            _raw_from_values(tokens[statement_start:name_index])
        )
        outer_type = _primary_type_name(canonical_type)
        if (
            not outer_type
            or not outer_type[0].isupper()
            or outer_type.isupper()
        ):
            continue
        symbols[str(classification["name"])] = canonical_type
        type_names.add(canonical_type)
    return symbols, type_names


def _call_name_before_open(
    tokens: list[Token],
    open_index: int,
    lower: int,
) -> int | None:
    candidate = open_index - 1
    if candidate >= lower and tokens[candidate].kind == "identifier":
        return candidate
    if candidate < lower or tokens[candidate].value not in {">", ">>"}:
        return None
    depth = 0
    for cursor in range(candidate, lower - 1, -1):
        value = tokens[cursor].value
        if value == ">":
            depth += 1
        elif value == ">>":
            depth += 2
        elif value == "<":
            depth -= 1
            if depth == 0:
                name_index = cursor - 1
                if (
                    name_index >= lower
                    and tokens[name_index].kind == "identifier"
                ):
                    return name_index
                return None
    return None


def _external_methods(
    part: dict[str, Any],
    loaded: dict[str, Any],
    symbol_types: dict[str, str],
) -> list[str]:
    parsed = loaded["parsed_by_path"][part["_path"]]
    text = parsed["text"]
    tokens: list[Token] = parsed["tokens"]
    forward: dict[int, int] = parsed["forward"]
    reverse: dict[int, int] = parsed["reverse"]
    start, end = part["_body_range"]
    local_methods = {
        item["name"]
        for item in loaded["parts"]
        if item["owner"] == part["owner"]
    }
    results: list[str] = []
    for open_index in range(start, end):
        if tokens[open_index].value != "(" or open_index not in forward:
            continue
        close_index = forward[open_index]
        if close_index >= end:
            continue
        name_index = _call_name_before_open(tokens, open_index, start)
        if name_index is None or name_index - 1 < start:
            continue
        operator = tokens[name_index - 1].value
        if operator not in {".", "->", "::"}:
            continue
        callee_start = _member_chain_start(
            tokens, reverse, name_index, start
        )
        receiver_tokens = tokens[callee_start : name_index - 1]
        receiver_identifiers = [
            token.value
            for token in receiver_tokens
            if token.kind == "identifier"
        ]
        owner_type: str | None = None
        if operator == "::" and name_index >= 2:
            owner_type = tokens[name_index - 2].value
        elif receiver_identifiers:
            receiver_root = receiver_identifiers[0]
            owner_type = (
                part["owner"]
                if receiver_root == "this"
                else symbol_types.get(receiver_root)
            )
        method_name = tokens[name_index].value
        if owner_type == part["owner"] and method_name in local_methods:
            continue
        original_expression = _raw(
            text, tokens, callee_start, close_index + 1
        )
        if owner_type is None:
            results.append(original_expression)
            continue
        method_expression = _raw(
            text, tokens, name_index, close_index + 1
        )
        results.append(f"{owner_type}{operator}{method_expression}")
    return list(dict.fromkeys(results))


def _external_type_facts(
    part: dict[str, Any],
    loaded: dict[str, Any],
    candidate_names: set[str],
) -> list[str]:
    local_types = {
        class_item["name"]
        for _, source_parsed in loaded["parsed_files"]
        for class_item in source_parsed["classes"]
    }
    return sorted(
        {
            type_expression
            for type_expression in candidate_names
            if (
                (outer_type := _primary_type_name(type_expression))
                and outer_type not in local_types
                and outer_type[0].isupper()
                and not outer_type.isupper()
            )
        },
        key=str.casefold,
    )


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
            responsibility="Report external type and method references for all definitions matching one function name.",
            boundaries=[
                "External means not defined by the selected C++ file or its companion.",
                "Type names are derived from local declaration syntax; wrapped template types remain one expression.",
                "Member-call receivers are replaced with locally declared type expressions when available.",
                "Called methods, inheritance, overloads, and included source are not followed.",
            ],
            additional_problems=[
                {
                    "severity": "error",
                    "code": "function-not-found",
                    "selection": function_name,
                    "message": "No matching function definition was found",
                }
            ],
        )
    relations = {
        (
            item["callable"]["kind"],
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
        symbol_types, candidate_type_names = _function_symbol_types(
            candidate, loaded
        )
        methods = _external_methods(candidate, loaded, symbol_types)
        matches.append(
            {
                "function_id": candidate["function_id"],
                "function": _public_callable(candidate),
                "relation": _public_relation(
                    relations[candidate["_identity"]]
                ),
                "external_types": _external_type_facts(
                    candidate,
                    loaded,
                    candidate_type_names,
                ),
                "external_methods": methods,
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
        responsibility="Report external type and method references for all definitions matching one function name.",
        boundaries=[
            "External means not defined by the selected C++ file or its companion.",
            "Type names are derived from local declaration syntax; wrapped template types remain one expression.",
            "Member-call receivers are replaced with locally declared type expressions when available.",
            "Called methods, inheritance, overloads, and included source are not followed.",
        ],
    )
