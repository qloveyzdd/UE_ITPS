from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .source_context import load_source_context, source_result
from .source_controls import _member_chain_start
from .source_declarations import _TYPE_KEYWORDS, _classify_declaration
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
from .source_namespaces import (
    namespace_at,
    observed_namespace_names,
    qualified_name,
    resolve_observed_namespace,
)
from .source_tokens import (
    Token,
    _raw,
    _raw_from_values,
    _split_arguments,
    lex_source,
    token_pairs,
)
from .source_type_facts import (
    _global_variable_facts as _declared_global_variable_facts,
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


def _unit_for_path(path: Path) -> str:
    return "header" if path.suffix.casefold() in {".h", ".hpp"} else "cpp"


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
            and (line is None or tokens[index].line == line)
        ),
        None,
    )


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
        for index, token in reversed(list(enumerate(tokens[start:end], start)))
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


def _member_call_facts(
    part: dict[str, Any],
    loaded: dict[str, Any],
    symbol_types: dict[str, str],
    confirmed_type_names: set[str],
    observed_namespaces: set[str],
    free_function_names: set[str],
) -> tuple[list[dict[str, Any]], set[int]]:
    parsed = loaded["parsed_by_path"][part["_path"]]
    text = parsed["text"]
    tokens: list[Token] = parsed["tokens"]
    forward: dict[int, int] = parsed["forward"]
    reverse: dict[int, int] = parsed["reverse"]
    start, end = part["_body_range"]
    results: list[dict[str, Any]] = []
    call_name_indices: set[int] = set()
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
        call_name_indices.add(name_index)
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
        if operator == "::":
            receiver_expression = _canonical_type_expression(
                _raw_from_values(receiver_tokens)
            )
            if _qualifier_is_confirmed_type(
                receiver_expression,
                confirmed_type_names,
            ):
                owner_type = receiver_expression
            else:
                namespace = _resolved_namespace_for(
                    receiver_expression,
                    parsed,
                    name_index,
                    observed_namespaces,
                )
                function_name = (
                    qualified_name(
                        namespace,
                        tokens[name_index].value,
                    )
                    if namespace
                    else None
                )
                if (
                    function_name is not None
                    and function_name in free_function_names
                ):
                    results.append(
                        _symbol_fact(
                            "free_function",
                            function_name,
                            part["_path"],
                            tokens[callee_start].line,
                            callee_start,
                        )
                    )
                    continue
        elif receiver_identifiers:
            receiver_root = receiver_identifiers[0]
            owner_type = (
                part["owner"]
                if receiver_root == "this"
                else symbol_types.get(receiver_root)
            )
        original_expression = _raw(
            text, tokens, callee_start, close_index + 1
        )
        if owner_type is None:
            results.append(
                _symbol_fact(
                    "unknown",
                    original_expression,
                    part["_path"],
                    tokens[callee_start].line,
                    callee_start,
                )
            )
            continue
        method_expression = _raw(
            text, tokens, name_index, close_index + 1
        )
        results.append(
            _symbol_fact(
                "member_call",
                f"{owner_type}{operator}{method_expression}",
                part["_path"],
                tokens[callee_start].line,
                callee_start,
                owner_type=owner_type,
            )
        )
    return results, call_name_indices


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


def _callback_api(name: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:Add|Bind|Create)(?:Dynamic|Lambda|Raw|SP|Static|"
            r"UFunction|UObject|WeakLambda)?",
            name,
        )
        or name in {"SetTimer", "SetTimerForNextTick"}
        or re.search(r"(?:Callback|Handler)$", name)
    )


def _address_expression(
    tokens: list[Token],
    ampersand: int,
    end: int,
) -> tuple[str, str | None, int] | None:
    cursor = ampersand + 1
    if cursor >= end or tokens[cursor].kind != "identifier":
        return None
    expression_end = cursor + 1
    while (
        expression_end + 1 < end
        and tokens[expression_end].value == "::"
        and tokens[expression_end + 1].kind == "identifier"
    ):
        expression_end += 2
    expression_tokens = tokens[cursor:expression_end]
    identifiers = [
        token.value for token in expression_tokens
        if token.kind == "identifier"
    ]
    spelling = _raw_from_values(expression_tokens)
    qualifier = (
        _raw_from_values(expression_tokens[:-2])
        if len(identifiers) > 1
        else None
    )
    return spelling, qualifier, expression_end


def _enclosing_callback_call(
    tokens: list[Token],
    forward: dict[int, int],
    address_index: int,
    lower: int,
) -> bool:
    enclosing = sorted(
        (
            (forward[open_index] - open_index, open_index)
            for open_index in range(lower, address_index)
            if tokens[open_index].value == "("
            and open_index in forward
            and address_index < forward[open_index]
        )
    )
    for _, open_index in enclosing:
        name_index = _call_name_before_open(tokens, open_index, lower)
        if (
            name_index is not None
            and _callback_api(tokens[name_index].value)
        ):
            return True
    return False


def _function_address_facts(
    part: dict[str, Any],
    loaded: dict[str, Any],
    callable_names: set[str],
    callable_qualified_names: set[str],
    variable_names: set[str],
    confirmed_type_names: set[str],
    observed_namespaces: set[str],
) -> list[dict[str, Any]]:
    parsed = loaded["parsed_by_path"][part["_path"]]
    tokens: list[Token] = parsed["tokens"]
    forward: dict[int, int] = parsed["forward"]
    start, end = part["_body_range"]
    results: list[dict[str, Any]] = []
    for index in range(start, end):
        if tokens[index].value != "&":
            continue
        address = _address_expression(tokens, index, end)
        if address is None:
            continue
        spelling, qualifier, _ = address
        target_name = spelling.rsplit("::", 1)[-1]
        owner_type = (
            qualifier
            if qualifier is not None
            and _qualifier_is_confirmed_type(
                qualifier,
                confirmed_type_names,
            )
            else None
        )
        namespace = (
            _resolved_namespace_for(
                qualifier,
                parsed,
                index,
                observed_namespaces,
            )
            if qualifier is not None
            and owner_type is None
            else None
        )
        resolved_spelling = (
            qualified_name(namespace, target_name)
            if namespace is not None
            else spelling
        )
        lexical_callable_names = {
            spelling,
            *(
                qualified_name(namespace, spelling)
                for namespace in _namespace_chain(part["namespace"])
            ),
        }
        known_callable = (
            resolved_spelling in callable_qualified_names
            or bool(
                lexical_callable_names.intersection(
                    callable_qualified_names
                )
            )
            or (
                qualifier is None
                and target_name in callable_names
            )
        )
        is_callback = _enclosing_callback_call(
            tokens, forward, index, start
        )
        if not is_callback and (
            target_name in variable_names
            or not known_callable
        ):
            results.append(
                _symbol_fact(
                    "unknown",
                    f"&{spelling}",
                    part["_path"],
                    tokens[index].line,
                    index,
                )
            )
            continue
        results.append(
            _symbol_fact(
                "callback_target" if is_callback else "function_address",
                spelling,
                part["_path"],
                tokens[index].line,
                index,
                owner_type=owner_type,
            )
        )
    return results


def _global_variable_facts(
    part: dict[str, Any],
    loaded: dict[str, Any],
    local_names: set[str],
    confirmed_type_names: set[str],
    observed_namespaces: set[str],
) -> list[dict[str, Any]]:
    parsed = loaded["parsed_by_path"][part["_path"]]
    tokens: list[Token] = parsed["tokens"]
    reverse: dict[int, int] = parsed["reverse"]
    start, end = part["_body_range"]
    declared_variables = _source_declaration_facts(loaded)[0]
    declared_globals = _declared_global_variable_facts(
        loaded,
        declared_variables,
    )
    known_global_names = {
        item["name"] for item in declared_globals
    }
    known_global_qualified_names = {
        item["qualified_name"] for item in declared_globals
    }
    results: list[dict[str, Any]] = []
    for index in range(start, end):
        token = tokens[index]
        heuristic_global = bool(
            re.fullmatch(r"G[A-Z][A-Za-z0-9_]*", token.value)
        )
        if (
            token.kind != "identifier"
            or token.value in local_names
            or (
                token.value not in known_global_names
                and not heuristic_global
            )
        ):
            continue
        operator = (
            tokens[index - 1].value
            if index - 1 >= start
            else None
        )
        if operator in {".", "->"}:
            spelling_start = _member_chain_start(
                tokens, reverse, index, start
            )
            results.append(
                _symbol_fact(
                    "unknown",
                    _raw_from_values(
                        tokens[spelling_start : index + 1]
                    ),
                    part["_path"],
                    tokens[spelling_start].line,
                    spelling_start,
                )
            )
            continue
        spelling_start = index
        if operator == "::":
            while (
                spelling_start - 2 >= start
                and tokens[spelling_start - 1].value == "::"
                and tokens[spelling_start - 2].kind == "identifier"
            ):
                spelling_start -= 2
            if (
                spelling_start - 1 >= start
                and tokens[spelling_start - 1].value == "::"
            ):
                spelling_start -= 1
            qualifier = _raw_from_values(
                tokens[spelling_start : index - 1]
            ).removeprefix("::")
            qualifier_is_type = _qualifier_is_confirmed_type(
                qualifier,
                confirmed_type_names,
            )
            qualifier_is_namespace = (
                not qualifier_is_type
                and (
                    resolved_namespace := _resolved_namespace_for(
                        qualifier,
                        parsed,
                        index,
                        observed_namespaces,
                    )
                )
                is not None
            )
            qualified_global = (
                qualified_name(
                    resolved_namespace,
                    token.value,
                )
                if qualifier_is_namespace
                else None
            )
            if (
                not qualifier_is_namespace
                or (
                    not heuristic_global
                    and qualified_global
                    not in known_global_qualified_names
                )
            ):
                results.append(
                    _symbol_fact(
                        "unknown",
                        _raw_from_values(
                            tokens[spelling_start : index + 1]
                        ),
                        part["_path"],
                        tokens[spelling_start].line,
                        spelling_start,
                    )
                )
                continue
        elif (
            not heuristic_global
            and not any(
                qualified_name(namespace, token.value)
                in known_global_qualified_names
                for namespace in [
                    *_namespace_chain(
                        namespace_at(
                            parsed["namespace_scopes"],
                            index,
                        )
                    ),
                    None,
                ]
            )
        ):
            results.append(
                _symbol_fact(
                    "unknown",
                    token.value,
                    part["_path"],
                    token.line,
                    index,
                )
            )
            continue
        results.append(
            _symbol_fact(
                "global_variable",
                _raw_from_values(
                    tokens[spelling_start : index + 1]
                ),
                part["_path"],
                tokens[spelling_start].line,
                spelling_start,
            )
        )
    return results


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


def _bare_call_facts(
    part: dict[str, Any],
    loaded: dict[str, Any],
    call_name_indices: set[int],
    known_type_names: set[str],
    variable_names: set[str],
    visible_free_functions: dict[str, str],
) -> list[dict[str, Any]]:
    parsed = loaded["parsed_by_path"][part["_path"]]
    text = parsed["text"]
    tokens: list[Token] = parsed["tokens"]
    forward: dict[int, int] = parsed["forward"]
    start, end = part["_body_range"]
    methods = {
        item["name"]
        for item in loaded["parts"]
        if item["kind"] == "method"
        and item["namespace"] == part["namespace"]
        and item["owner"] == part["owner"]
    }
    ignored_macros = {
        "check",
        "checkf",
        "ensure",
        "ensureAlways",
        "ensureAlwaysMsgf",
        "ensureMsgf",
    }
    control_keywords = {
        "catch",
        "for",
        "if",
        "sizeof",
        "switch",
        "while",
    }
    results: list[dict[str, Any]] = []
    for open_index in range(start, end):
        if tokens[open_index].value != "(" or open_index not in forward:
            continue
        close_index = forward[open_index]
        if close_index >= end:
            continue
        name_index = _call_name_before_open(tokens, open_index, start)
        if name_index is None or name_index in call_name_indices:
            continue
        name = tokens[name_index].value
        if (
            name in known_type_names
            or name in variable_names
            or name in _TYPE_KEYWORDS
            or name in ignored_macros
            or name in control_keywords
            or name.isupper()
            or (
                name == part["name"]
                and (
                    part["kind"] == "free_function"
                    or part["owner"] is not None
                )
            )
        ):
            continue
        if name in methods and part["owner"] is not None:
            expression = _raw(text, tokens, name_index, close_index + 1)
            results.append(
                _symbol_fact(
                    "member_call",
                    f"{part['owner']}->{expression}",
                    part["_path"],
                    tokens[name_index].line,
                    name_index,
                    owner_type=part["owner"],
                )
            )
        elif name in visible_free_functions:
            results.append(
                _symbol_fact(
                    "free_function",
                    visible_free_functions[name],
                    part["_path"],
                    tokens[name_index].line,
                    name_index,
                )
            )
        else:
            expression = _raw(
                text, tokens, name_index, close_index + 1
            )
            results.append(
                _symbol_fact(
                    "unknown",
                    expression,
                    part["_path"],
                    tokens[name_index].line,
                    name_index,
                )
            )
    return results


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
        if (outer_type := _primary_type_name(item["spelling"]))
    )
    return names


def _public_external_symbols(
    facts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    priorities = {
        "type": 0,
        "global_variable": 1,
        "free_function": 2,
        "member_call": 3,
        "function_address": 4,
        "callback_target": 5,
        "unknown": 6,
    }
    ordered = sorted(
        facts,
        key=lambda item: (
            int(item["_token_index"]),
            priorities[item["kind"]],
            item["spelling"],
        ),
    )
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str | None]] = set()
    for item in ordered:
        key = (
            str(item["kind"]),
            str(item["spelling"]),
            item.get("owner_type"),
        )
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                key: value
                for key, value in item.items()
                if not key.startswith("_")
            }
        )
    return results


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
            responsibility="Report external symbols referenced by all definitions matching one function name.",
            boundaries=[
                "Namespace is part of each function's local identity, qualified name, declaration-definition relation, and function_id within the selected source pair.",
                "Method owners retain the full lexical enclosing class chain without repeating the namespace.",
                "function_id is a compact source-pair identity and is not a project-level stable ID.",
                "External means outside the selected function semantic unit, including symbols declared in the selected file or its companion.",
                "Symbol kinds are lexical candidate categories, not call, read, write, or ownership relations.",
                "Type names and receiver types are derived from locally visible declaration syntax; wrapped template types remain one expression.",
                "A bare call is a member_call only for a matching current-class method, or a free_function only for a matching visible declaration in the selected source pair; otherwise it remains unknown.",
                "A scope-qualified call is a member_call when its receiver is a confirmed type, or a free_function when its qualifier is an observed Namespace with a matching declaration; otherwise it remains unknown.",
                "A namespace-qualified reference is a global_variable only when its fully qualified name matches a local variable declaration, or its name has conservative G* spelling evidence; type-qualified, member-shaped, unresolved, and other unmatched accesses remain unknown.",
                "Function addresses and callback targets are distinguished only when local callable declarations or recognized callback API syntax provide evidence; callable matching resolves owner spellings through the current lexical Namespace, and owner_type is present only for confirmed type qualifiers.",
                "Called functions, inheritance, overloads, macros, and included source are not followed.",
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
        symbol_types, type_facts, local_names = _function_symbol_context(
            candidate, loaded
        )
        confirmed_type_names = _confirmed_type_names(
            loaded, type_facts
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
        responsibility="Report external symbols referenced by all definitions matching one function name.",
        boundaries=[
            "Namespace is part of each function's local identity, qualified name, declaration-definition relation, and function_id within the selected source pair.",
            "Method owners retain the full lexical enclosing class chain without repeating the namespace.",
            "function_id is a compact source-pair identity and is not a project-level stable ID.",
            "External means outside the selected function semantic unit, including symbols declared in the selected file or its companion.",
            "Symbol kinds are lexical candidate categories, not call, read, write, or ownership relations.",
            "Type names and receiver types are derived from locally visible declaration syntax; wrapped template types remain one expression.",
            "A bare call is a member_call only for a matching current-class method, or a free_function only for a matching visible declaration in the selected source pair; otherwise it remains unknown.",
            "A scope-qualified call is a member_call when its receiver is a confirmed type, or a free_function when its qualifier is an observed Namespace with a matching declaration; otherwise it remains unknown.",
            "A namespace-qualified reference is a global_variable only when its fully qualified name matches a local variable declaration, or its name has conservative G* spelling evidence; type-qualified, member-shaped, unresolved, and other unmatched accesses remain unknown.",
            "Function addresses and callback targets are distinguished only when local callable declarations or recognized callback API syntax provide evidence; callable matching resolves owner spellings through the current lexical Namespace, and owner_type is present only for confirmed type qualifiers.",
            "Called functions, inheritance, overloads, macros, and included source are not followed.",
        ],
    )
