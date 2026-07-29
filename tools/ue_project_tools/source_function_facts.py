from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .source_context import load_source_context, source_result
from .source_controls import _member_chain_start
from .source_declarations import (
    _FORBIDDEN_CALLABLE_NAMES,
    _TYPE_KEYWORDS,
    _classify_declaration,
    parse_free_function_declarations,
)
from .source_signatures import parameter_signature
from .source_tokens import (
    Token,
    _raw,
    _raw_from_values,
    _split_arguments,
    lex_source,
    token_pairs,
)

from .source_fact_common import (
    _SOURCE_MACROS,
    _SOURCE_MACRO_PREFIXES,
    _callable_name,
    _declaration_variables,
    _public_location,
    _source_declaration_facts,
    _source_macros,
    _statement_start,
)

def _qualifiers(signature: str) -> list[str]:
    values = []
    for value in (
        "static",
        "virtual",
        "inline",
        "constexpr",
    ):
        if re.search(rf"\b{value}\b", signature):
            values.append(value)
    suffix = signature.rsplit(")", 1)[-1] if ")" in signature else ""
    for value in ("const", "volatile", "noexcept", "override", "final"):
        if re.search(rf"\b{value}\b", suffix):
            values.append(value)
    if re.search(r"(?:^|\s)&&(?:\s|$)", suffix):
        values.append("rvalue_ref")
    elif re.search(r"(?:^|\s)&(?:\s|$)", suffix):
        values.append("lvalue_ref")
    if re.search(r"=\s*0\b", signature):
        values.append("pure_virtual")
    if re.search(r"=\s*default\b", signature):
        values.append("defaulted")
    if re.search(r"=\s*delete\b", signature):
        values.append("deleted")
    return values


def _identity_qualifiers(signature: str) -> tuple[str, ...]:
    return tuple(
        qualifier
        for qualifier in _qualifiers(signature)
        if qualifier in {"const", "volatile", "lvalue_ref", "rvalue_ref"}
    )


def _function_id(
    kind: str,
    owner: str | None,
    name: str,
    parameter_signature: list[list[str]],
    identity_qualifiers: tuple[str, ...],
) -> str:
    parameters = ";".join(" ".join(group) for group in parameter_signature)
    qualifiers = ",".join(identity_qualifiers)
    return "|".join(
        (kind, owner or "", name, f"({parameters})", qualifiers)
    )


def _callable_part(
    *,
    kind: str,
    owner: str | None,
    name: str,
    parameters: str,
    signature: str,
    role: str,
    path: Path,
    location: dict[str, Any],
    body_range: tuple[int, int] | None,
    project_root: Path,
    engine_root: Path | None,
) -> dict[str, Any]:
    actual_name = _callable_name(name, signature)
    normalized_parameters = [
        list(group) for group in parameter_signature(parameters)
    ]
    identity_qualifiers = _identity_qualifiers(signature)
    function_id = _function_id(
        kind,
        owner,
        actual_name,
        normalized_parameters,
        identity_qualifiers,
    )
    return {
        "function_id": function_id,
        "kind": kind,
        "owner": owner,
        "name": actual_name,
        "parameters": parameters,
        "parameter_signature": normalized_parameters,
        "signature": " ".join(signature.split()),
        "qualifiers": _qualifiers(signature),
        "role": role,
        "evidence": _public_location(path, location, project_root, engine_root),
        "_identity": (
            kind,
            owner or "",
            actual_name,
            tuple(tuple(group) for group in normalized_parameters),
            identity_qualifiers,
        ),
        "_body_range": body_range,
        "_path": path,
    }


def _top_level_declarations(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    return parse_free_function_declarations(
        parsed["text"],
        parsed["tokens"],
        parsed["forward"],
    )


def _callable_parts(
    parsed_files: list[tuple[Path, dict[str, Any]]],
    project_root: Path,
    engine_root: Path | None,
) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    for path, parsed in parsed_files:
        for class_item in parsed["classes"]:
            for member in class_item["members"]:
                if member["name"] in _SOURCE_MACROS or member["name"].startswith(
                    _SOURCE_MACRO_PREFIXES
                ):
                    continue
                parts.append(
                    _callable_part(
                        kind="method",
                        owner=class_item["name"],
                        name=member["name"],
                        parameters=member["parameters"],
                        signature=member["signature"],
                        role="definition" if member["has_body"] else "declaration",
                        path=path,
                        location=member["location"],
                        body_range=member["body_range"],
                        project_root=project_root,
                        engine_root=engine_root,
                    )
                )
        for definition in parsed["external_definitions"]:
            parts.append(
                _callable_part(
                    kind="method",
                    owner=definition["class_name"],
                    name=definition["name"],
                    parameters=definition["parameters"],
                    signature=definition["signature"],
                    role="definition",
                    path=path,
                    location=definition["location"],
                    body_range=definition["body_range"],
                    project_root=project_root,
                    engine_root=engine_root,
                )
            )
        for function in parsed["free_functions"]:
            parts.append(
                _callable_part(
                    kind="free_function",
                    owner=None,
                    name=function["name"],
                    parameters=function["parameters"],
                    signature=function["signature"],
                    role="definition",
                    path=path,
                    location=function["location"],
                    body_range=function["body_range"],
                    project_root=project_root,
                    engine_root=engine_root,
                )
            )
        for declaration in _top_level_declarations(parsed):
            parts.append(
                _callable_part(
                    kind="free_function",
                    owner=None,
                    name=declaration["name"],
                    parameters=declaration["parameters"],
                    signature=declaration["signature"],
                    role="declaration",
                    path=path,
                    location=declaration["location"],
                    body_range=None,
                    project_root=project_root,
                    engine_root=engine_root,
                )
            )
    return sorted(
        [
            part
            for part in parts
            if part["name"] not in _FORBIDDEN_CALLABLE_NAMES
        ],
        key=lambda item: (
            item["evidence"]["root"],
            item["evidence"]["path"].casefold(),
            item["evidence"]["line"],
            item["name"],
        ),
    )


def _public_callable(part: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in part.items()
        if not key.startswith("_")
        and key not in {"function_id", "parameter_signature", "evidence"}
    }


def _public_relation(relation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: relation[key]
        for key in ("status", "declarations", "definitions")
    }


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


def _relations(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for part in parts:
        grouped.setdefault(part["_identity"], []).append(part)
    relations: list[dict[str, Any]] = []
    for identity, items in sorted(grouped.items(), key=lambda pair: str(pair[0])):
        declarations = [item for item in items if item["role"] == "declaration"]
        definitions = [item for item in items if item["role"] == "definition"]
        if len(definitions) > 1 or len(declarations) > 1:
            status = "ambiguous"
        elif declarations and definitions:
            status = "matched"
        elif definitions:
            definition_path = str(definitions[0]["evidence"]["path"]).casefold()
            status = (
                "inline_definition"
                if definition_path.endswith((".h", ".hpp"))
                else "source_only"
            )
        else:
            status = "declaration_only"
        relations.append(
            {
                "kind": "declaration_definition",
                "callable": {
                    "function_id": _function_id(
                        identity[0],
                        identity[1] or None,
                        identity[2],
                        [list(group) for group in identity[3]],
                        identity[4],
                    ),
                    "kind": identity[0],
                    "owner": identity[1] or None,
                    "name": identity[2],
                    "parameter_signature": [list(group) for group in identity[3]],
                    "identity_qualifiers": list(identity[4]),
                },
                "status": status,
                "declarations": [item["evidence"] for item in declarations],
                "definitions": [item["evidence"] for item in definitions],
            }
        )
    return relations


def _function_facts(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def occurrence(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "signature": item["signature"],
            "evidence": item["evidence"],
        }

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for part in parts:
        grouped.setdefault(part["_identity"], []).append(part)
    relation_by_identity = {
        (
            relation["callable"]["kind"],
            relation["callable"]["owner"] or "",
            relation["callable"]["name"],
            tuple(
                tuple(group)
                for group in relation["callable"]["parameter_signature"]
            ),
            tuple(relation["callable"]["identity_qualifiers"]),
        ): relation
        for relation in _relations(parts)
    }
    results: list[dict[str, Any]] = []
    for identity, items in sorted(
        grouped.items(), key=lambda pair: str(pair[0])
    ):
        declarations = [
            occurrence(item)
            for item in items
            if item["role"] == "declaration"
        ]
        definitions = [
            occurrence(item)
            for item in items
            if item["role"] == "definition"
        ]
        relation = relation_by_identity[identity]
        results.append(
            {
                "kind": identity[0],
                "owner": identity[1] or None,
                "name": identity[2],
                "function_id": items[0]["function_id"],
                "parameters": items[0]["parameters"],
                "parameter_signature": [
                    list(group) for group in identity[3]
                ],
                "identity_qualifiers": list(identity[4]),
                "qualifiers": sorted(
                    {
                        qualifier
                        for item in items
                        for qualifier in item["qualifiers"]
                    }
                ),
                "relation": relation["status"],
                "declarations": declarations,
                "definitions": definitions,
            }
        )
    return results


def list_source_functions(
    source_file: Path,
    engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = load_source_context(source_file, engine_override)
    loaded["parts"] = _callable_parts(
        loaded["parsed_files"],
        loaded["project_root"],
        loaded["engine_root"],
    )
    loaded["macros"] = [
        macro
        for path, parsed in loaded["parsed_files"]
        for macro in _source_macros(
            parsed,
            path,
            loaded["project_root"],
            loaded["engine_root"],
        )
    ]
    loaded["macros"].sort(
        key=lambda item: (
            item["evidence"]["root"],
            item["evidence"]["path"].casefold(),
            item["evidence"]["line"],
        )
    )
    functions = _function_facts(loaded["parts"])
    _, all_unresolved = _source_declaration_facts(loaded)
    unresolved = [
        item
        for item in all_unresolved
        if item["scope"] in {"file", "member"}
    ]
    invalid_names = [
        item for item in functions if item["name"] in _TYPE_KEYWORDS
    ]
    function_macros = [
        {
            key: value
            for key, value in macro.items()
            if not key.startswith("_")
        }
        for macro in loaded["macros"]
        if macro["name"] == "UFUNCTION"
    ]
    return source_result(
        "ue-itps.cxx-functions.v1",
        loaded,
        {
            "functions": functions,
            "unresolved_declarations": unresolved,
            "function_macros": function_macros,
        },
        responsibility="Index callable signatures and conservative declaration-definition relations.",
        boundaries=[
            "Function bodies, calls, and state-changing operations are not included in this index.",
            "Relations are a conservative projection, not a complete C++ AST or linker result.",
        ],
        additional_problems=[
            *[
                {
                    "severity": "warning",
                    "code": "source-function-invalid-name",
                    "function_id": item["function_id"],
                    "name": item["name"],
                    "message": (
                        "A callable projection used a reserved type keyword "
                        "as its name"
                    ),
                }
                for item in invalid_names
            ],
            *(
                [
                    {
                        "severity": "warning",
                        "code": "source-function-declaration-unresolved",
                        "count": len(unresolved),
                        "message": (
                            "One or more declaration-shaped statements could "
                            "not be classified conservatively"
                        ),
                    }
                ]
                if unresolved
                else []
            ),
        ],
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
