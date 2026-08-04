from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .source_declarators import _classify_declaration
from .source_namespaces import (
    namespace_at,
    resolve_observed_namespace,
)
from .source_tokens import (
    Token,
    _raw_from_values,
    _split_arguments,
    lex_source,
    token_pairs,
)
from .source_variable_facts import (
    _declaration_variables,
    _source_declaration_facts,
    _statement_start,
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


def _parameter_symbol_types(
    part: dict[str, Any],
) -> dict[str, str]:
    tokens = lex_source(part["parameters"])
    forward, _ = token_pairs(tokens)
    symbols: dict[str, str] = {}
    for start, end in _split_arguments(tokens, 0, len(tokens)):
        classification = _classify_declaration(
            tokens,
            forward,
            start,
            end,
        )
        if classification["kind"] != "variable":
            continue
        name_index = int(classification["name_index"])
        type_expression = _raw_from_values(tokens[start:name_index])
        canonical_type = _canonical_type_expression(type_expression)
        if canonical_type:
            symbols[str(classification["name"])] = canonical_type
    return symbols


def _unit_for_path(path: Path) -> str:
    return (
        "header"
        if path.suffix.casefold() in {".h", ".hpp"}
        else "cpp"
    )


def _symbol_fact(
    kind: str,
    spelling: str,
    path: Path,
    line: int,
    token_index: int,
    *,
    owner_type: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "kind": kind,
        "spelling": spelling,
    }
    if owner_type is not None:
        result["owner_type"] = owner_type
    result["evidence"] = {
        "unit": _unit_for_path(path),
        "line": line,
    }
    result["_token_index"] = token_index
    return result


def _first_identifier_index(
    tokens: list[Token],
    start: int,
    end: int,
    name: str,
    *,
    line: int | None = None,
) -> int | None:
    return next(
        (
            index
            for index in range(start, end)
            if tokens[index].kind == "identifier"
            and tokens[index].value == name
            and (
                line is None
                or tokens[index].line == line
            )
        ),
        None,
    )


def _control_initializer_variables(
    parsed: dict[str, Any],
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    tokens: list[Token] = parsed["tokens"]
    forward: dict[int, int] = parsed["forward"]
    results: list[dict[str, Any]] = []
    for keyword_index in range(start, end - 1):
        if (
            tokens[keyword_index].value not in {"if", "switch", "while"}
            or tokens[keyword_index + 1].value != "("
            or keyword_index + 1 not in forward
        ):
            continue
        open_index = keyword_index + 1
        close_index = forward[open_index]
        if close_index >= end:
            continue
        declaration_start = open_index + 1
        declaration_end = close_index
        cursor = declaration_start
        while cursor < close_index:
            if tokens[cursor].value == "(" and cursor in forward:
                cursor = forward[cursor] + 1
                continue
            if tokens[cursor].value == ";":
                declaration_end = cursor
                break
            cursor += 1
        if not any(
            tokens[index].value == "="
            for index in range(declaration_start, declaration_end)
        ):
            continue
        classification = _classify_declaration(
            tokens,
            forward,
            declaration_start,
            declaration_end,
        )
        if classification.get("kind") != "variable":
            continue
        name_index = int(classification["name_index"])
        type_tokens = tokens[declaration_start:name_index]
        if not type_tokens or any(
            token.value in {".", "->"} for token in type_tokens
        ):
            continue
        canonical_type = _canonical_type_expression(
            _raw_from_values(type_tokens)
        )
        outer_type = _primary_type_name(canonical_type)
        if (
            not canonical_type
            or not outer_type
            or not outer_type[0].isupper()
            or outer_type.isupper()
        ):
            continue
        results.append(
            {
                "name": str(classification["name"]),
                "type_expression": canonical_type,
                "token_index": name_index,
            }
        )
    return results


def _function_symbol_context(
    part: dict[str, Any],
    loaded: dict[str, Any],
) -> tuple[dict[str, str], list[dict[str, Any]], set[str]]:
    symbols = _parameter_symbol_types(part)
    parsed = loaded["parsed_by_path"][part["_path"]]
    tokens: list[Token] = parsed["tokens"]
    start, end = part["_body_range"]
    type_facts = [
        _symbol_fact(
            "type",
            type_expression,
            part["_path"],
            int(part["evidence"]["line"]),
            start - 1,
        )
        for type_expression in dict.fromkeys(symbols.values())
        if _is_external_type_expression(type_expression, part)
    ]
    local_variables, _ = _declaration_variables(
        loaded["parsed_by_path"][part["_path"]],
        part["_path"],
        start,
        end,
        scope="local",
        owner=part["owner"],
        project_root=loaded["project_root"],
        engine_root=loaded["engine_root"],
    )
    shadowed_member_names = {
        *symbols,
        *(variable["name"] for variable in local_variables),
    }
    referenced_indices = {
        token.value: index
        for index, token in reversed(
            list(enumerate(tokens[start:end], start))
        )
        if token.kind == "identifier"
    }
    member_variables = [
        item
        for item in _source_declaration_facts(loaded)[0]
        if item["scope"] == "member"
        and item.get("owner") == part["owner"]
        and item["name"] in referenced_indices
        and item["name"] not in shadowed_member_names
    ]
    for variable in [*local_variables, *member_variables]:
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
        if not _is_external_type_expression(canonical_type, part):
            continue
        if variable["scope"] == "member":
            token_index = referenced_indices[variable["name"]]
        else:
            token_index = (
                _first_identifier_index(
                    tokens,
                    start,
                    end,
                    variable["name"],
                    line=int(variable["evidence"]["line"]),
                )
                or start
            )
        type_facts.append(
            _symbol_fact(
                "type",
                canonical_type,
                part["_path"],
                tokens[token_index].line,
                token_index,
            )
        )
    for variable in _control_initializer_variables(parsed, start, end):
        canonical_type = str(variable["type_expression"])
        symbols[str(variable["name"])] = canonical_type
        if not _is_external_type_expression(canonical_type, part):
            continue
        token_index = int(variable["token_index"])
        type_facts.append(
            _symbol_fact(
                "type",
                canonical_type,
                part["_path"],
                tokens[token_index].line,
                token_index,
            )
        )
    for semicolon in range(start, end):
        if tokens[semicolon].value != ";":
            continue
        statement_start = _statement_start(
            tokens,
            start,
            semicolon,
        )
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
            _raw_from_values(
                tokens[statement_start:name_index]
            )
        )
        outer_type = _primary_type_name(canonical_type)
        if (
            not outer_type
            or not outer_type[0].isupper()
            or outer_type.isupper()
        ):
            continue
        symbols[str(classification["name"])] = canonical_type
        if _is_external_type_expression(canonical_type, part):
            type_facts.append(
                _symbol_fact(
                    "type",
                    canonical_type,
                    part["_path"],
                    tokens[statement_start].line,
                    statement_start,
                )
            )
    local_names = {
        *symbols,
        *(variable["name"] for variable in member_variables),
    }
    return symbols, type_facts, local_names


def _qualifier_is_confirmed_type(
    qualifier: str,
    confirmed_type_names: set[str],
) -> bool:
    normalized = qualifier.removeprefix("::")
    segments = normalized.split("::")
    return bool(
        normalized in confirmed_type_names
        or segments[0] in confirmed_type_names
        or segments[-1] in confirmed_type_names
    )


def _resolved_namespace_for(
    qualifier: str,
    parsed: dict[str, Any],
    token_index: int,
    observed_namespaces: set[str],
) -> str | None:
    return resolve_observed_namespace(
        qualifier.removeprefix("::"),
        namespace_at(
            parsed.get("namespace_scopes", []),
            token_index,
        ),
        observed_namespaces,
    )


def _is_external_type_expression(
    type_expression: str,
    part: dict[str, Any],
) -> bool:
    outer_type = _primary_type_name(type_expression)
    return bool(
        outer_type
        and outer_type != part["owner"]
        and outer_type[0].isupper()
        and not outer_type.isupper()
    )


def _namespace_chain(namespace: str | None) -> list[str]:
    chain: list[str] = []
    current = namespace
    while current is not None:
        chain.append(current)
        current = (
            current.rsplit("::", 1)[0]
            if "::" in current
            else None
        )
    return chain


def _visible_free_functions(
    part: dict[str, Any],
    parts: list[dict[str, Any]],
) -> dict[str, str]:
    namespaces: list[str | None] = []
    current = part["namespace"]
    while current:
        namespaces.append(current)
        current = (
            current.rsplit("::", 1)[0]
            if "::" in current
            else None
        )
    namespaces.append(None)
    results: dict[str, str] = {}
    for namespace in namespaces:
        for candidate in parts:
            if (
                candidate["kind"] == "free_function"
                and candidate["namespace"] == namespace
            ):
                results.setdefault(
                    candidate["name"],
                    candidate["qualified_name"],
                )
    return results


def _qualified_type_facts(
    part: dict[str, Any],
    loaded: dict[str, Any],
    confirmed_type_names: set[str],
) -> list[dict[str, Any]]:
    parsed = loaded["parsed_by_path"][part["_path"]]
    tokens: list[Token] = parsed["tokens"]
    start, end = part["_body_range"]
    results: list[dict[str, Any]] = []
    for index in range(start, end - 1):
        token = tokens[index]
        if (
            token.kind != "identifier"
            or tokens[index + 1].value != "::"
            or token.value not in confirmed_type_names
            or token.value == part["owner"]
            or (
                index > start
                and tokens[index - 1].value == "::"
            )
        ):
            continue
        results.append(
            _symbol_fact(
                "type",
                token.value,
                part["_path"],
                token.line,
                index,
            )
        )
    return results


def _confirmed_type_names(
    loaded: dict[str, Any],
    type_facts: list[dict[str, Any]],
) -> set[str]:
    names = {
        value
        for _, parsed in loaded["parsed_files"]
        for item in [
            *parsed["classes"],
            *parsed.get("forward_declarations", []),
        ]
        for value in {
            item["name"],
            item.get("qualified_name"),
        }
        if value
    }
    names.update(
        outer_type
        for item in type_facts
        if (
            outer_type := _primary_type_name(item["spelling"])
        )
    )
    return names
