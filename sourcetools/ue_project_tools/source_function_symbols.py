from __future__ import annotations

import re
from typing import Any

from .source_controls import _member_chain_start
from .source_declarators import _TYPE_KEYWORDS
from .source_function_context import (
    _canonical_type_expression,
    _namespace_chain,
    _qualifier_is_confirmed_type,
    _resolved_namespace_for,
    _symbol_fact,
)
from .source_namespaces import namespace_at, qualified_name
from .source_tokens import Token, _raw, _raw_from_values
from .source_variable_facts import (
    _global_variable_facts as _declared_global_variable_facts,
    _source_declaration_facts,
)


def _call_name_before_open(
    tokens: list[Token],
    open_index: int,
    lower: int,
) -> int | None:
    candidate = open_index - 1
    if (
        candidate >= lower
        and tokens[candidate].kind == "identifier"
    ):
        return candidate
    if (
        candidate < lower
        or tokens[candidate].value not in {">", ">>"}
    ):
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
        if (
            tokens[open_index].value != "("
            or open_index not in forward
        ):
            continue
        close_index = forward[open_index]
        if close_index >= end:
            continue
        name_index = _call_name_before_open(
            tokens,
            open_index,
            start,
        )
        if name_index is None or name_index - 1 < start:
            continue
        operator = tokens[name_index - 1].value
        if operator not in {".", "->", "::"}:
            continue
        call_name_indices.add(name_index)
        callee_start = _member_chain_start(
            tokens,
            reverse,
            name_index,
            start,
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
            text,
            tokens,
            callee_start,
            close_index + 1,
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
            text,
            tokens,
            name_index,
            close_index + 1,
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


def _callback_api(name: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:Add|Bind|Create)(?:Dynamic|Lambda|Raw|SP|Static|"
            r"UFunction|UObject|WeakLambda)?",
            name,
        )
        or name == "AddUniqueDynamic"
        or name in {"SetTimer", "SetTimerForNextTick"}
        or re.search(r"(?:Callback|Handler)$", name)
    )


def _delegate_subscription_api(name: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:Add|Bind)(?:Dynamic|Lambda|Raw|SP|Static|UFunction|"
            r"UObject|WeakLambda)",
            name,
        )
        or name in {"AddUniqueDynamic", "Bind"}
    )


def _delegate_publish_api(name: str) -> bool:
    return name in {"Broadcast", "Execute", "ExecuteIfBound"}


def _delegate_event_owner(
    tokens: list[Token],
    callee_start: int,
    event_index: int,
    part: dict[str, Any],
    symbol_types: dict[str, str],
    confirmed_type_names: set[str],
) -> str | None:
    if event_index == callee_start:
        return part.get("owner")
    identifiers = [
        token.value
        for token in tokens[callee_start:event_index]
        if token.kind == "identifier"
    ]
    if not identifiers:
        return None
    root = identifiers[0]
    if root == "this":
        return part.get("owner")
    owner_type = symbol_types.get(root)
    if owner_type:
        return owner_type
    if _qualifier_is_confirmed_type(root, confirmed_type_names):
        return root
    return None


def _delegate_callback(
    tokens: list[Token],
    open_index: int,
    close_index: int,
    confirmed_type_names: set[str],
) -> dict[str, str] | None:
    for index in range(open_index + 1, close_index):
        if tokens[index].value != "&":
            continue
        address = _address_expression(tokens, index, close_index)
        if address is None:
            continue
        spelling, qualifier, _ = address
        if (
            qualifier is None
            or not _qualifier_is_confirmed_type(
                qualifier,
                confirmed_type_names,
            )
        ):
            continue
        return {
            "owner_type": qualifier,
            "name": spelling.rsplit("::", 1)[-1],
            "qualified_name": spelling,
        }
    return None


def _delegate_operations(
    part: dict[str, Any],
    loaded: dict[str, Any],
    symbol_types: dict[str, str],
    confirmed_type_names: set[str],
) -> list[dict[str, Any]]:
    parsed = loaded["parsed_by_path"][part["_path"]]
    tokens: list[Token] = parsed["tokens"]
    forward: dict[int, int] = parsed["forward"]
    reverse: dict[int, int] = parsed["reverse"]
    start, end = part["_body_range"]
    results: list[dict[str, Any]] = []
    for open_index in range(start, end):
        if tokens[open_index].value != "(" or open_index not in forward:
            continue
        close_index = forward[open_index]
        if close_index >= end:
            continue
        name_index = _call_name_before_open(tokens, open_index, start)
        if name_index is None or name_index - 2 < start:
            continue
        api = tokens[name_index].value
        operation = (
            "publish"
            if _delegate_publish_api(api)
            else "subscribe"
            if _delegate_subscription_api(api)
            else None
        )
        if operation is None:
            continue
        if (
            tokens[name_index - 1].value not in {".", "->", "::"}
            or tokens[name_index - 2].kind != "identifier"
        ):
            continue
        event_index = name_index - 2
        callee_start = _member_chain_start(
            tokens,
            reverse,
            name_index,
            start,
        )
        if (
            event_index != callee_start
            and tokens[event_index - 1].value not in {".", "->", "::"}
        ):
            continue
        owner_type = _delegate_event_owner(
            tokens,
            callee_start,
            event_index,
            part,
            symbol_types,
            confirmed_type_names,
        )
        if owner_type is None:
            continue
        event_name = tokens[event_index].value
        if (
            api in {"Execute", "ExecuteIfBound"}
            and not (
                event_name.startswith("On")
                or event_name.endswith(("Delegate", "Event"))
            )
        ):
            continue
        callback = (
            _delegate_callback(
                tokens,
                open_index,
                close_index,
                confirmed_type_names,
            )
            if operation == "subscribe"
            else None
        )
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
                    "unit": (
                        "header"
                        if part["_path"].suffix.casefold() in {".h", ".hpp"}
                        else "cpp"
                    ),
                    "line": tokens[callee_start].line,
                },
            }
        )
    return results


def _address_expression(
    tokens: list[Token],
    ampersand: int,
    end: int,
) -> tuple[str, str | None, int] | None:
    cursor = ampersand + 1
    if (
        cursor >= end
        or tokens[cursor].kind != "identifier"
    ):
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
        token.value
        for token in expression_tokens
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
        name_index = _call_name_before_open(
            tokens,
            open_index,
            lower,
        )
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
                for namespace in _namespace_chain(
                    part["namespace"]
                )
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
            tokens,
            forward,
            index,
            start,
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
                (
                    "callback_target"
                    if is_callback
                    else "function_address"
                ),
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
            re.fullmatch(
                r"G[A-Z][A-Za-z0-9_]*",
                token.value,
            )
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
                tokens,
                reverse,
                index,
                start,
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
                and tokens[spelling_start - 2].kind
                == "identifier"
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
                            tokens[
                                spelling_start : index + 1
                            ]
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
        if (
            tokens[open_index].value != "("
            or open_index not in forward
        ):
            continue
        close_index = forward[open_index]
        if close_index >= end:
            continue
        name_index = _call_name_before_open(
            tokens,
            open_index,
            start,
        )
        if (
            name_index is None
            or name_index in call_name_indices
        ):
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
            expression = _raw(
                text,
                tokens,
                name_index,
                close_index + 1,
            )
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
                text,
                tokens,
                name_index,
                close_index + 1,
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
