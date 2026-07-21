from __future__ import annotations

import re
from typing import Any

from .source_tokens import (
    Token,
    _base_types,
    _location,
    _ordered_union,
    _raw,
    token_pairs,
)


_NON_DECLARATION_STARTS = {
    "break",
    "case",
    "continue",
    "default",
    "goto",
    "return",
    "throw",
    "yield",
}


def _member_start(tokens: list[Token], lower: int, index: int) -> int:
    cursor = index - 1
    while cursor >= lower:
        if tokens[cursor].value in {";", "{", "}"}:
            return cursor + 1
        cursor -= 1
    return lower


def _declaration_name(
    text: str, tokens: list[Token], start: int, end: int
) -> str | None:
    if start >= end or tokens[start].value in _NON_DECLARATION_STARTS:
        return None
    candidate = tokens[end - 1]
    if candidate.kind != "identifier":
        return None
    prefix = text[tokens[start].start : candidate.start]
    if (
        not prefix
        or not prefix[-1].isspace()
        or not prefix.rstrip()
        or prefix.rstrip().endswith((".", "::", "->", "]", ")"))
    ):
        return None
    return candidate.value


def _class_field_names(
    text: str, tokens: list[Token], start: int, end: int
) -> list[str]:
    names: list[str] = []
    statement_start = start
    brace_depth = 0
    paren_depth = 0
    bracket_depth = 0
    for cursor in range(start, end):
        value = tokens[cursor].value
        if value == "(":
            paren_depth += 1
        elif value == ")":
            paren_depth = max(0, paren_depth - 1)
        elif value == "[":
            bracket_depth += 1
        elif value == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif value == "{" and paren_depth == 0 and bracket_depth == 0:
            brace_depth += 1
        elif value == "}" and paren_depth == 0 and bracket_depth == 0:
            brace_depth = max(0, brace_depth - 1)
            if brace_depth == 0:
                statement_start = cursor + 1
        elif (
            value == ";"
            and brace_depth == 0
            and paren_depth == 0
            and bracket_depth == 0
        ):
            assignment = next(
                (
                    index
                    for index in range(statement_start, cursor)
                    if tokens[index].value in {"=", "+=", "-=", "*=", "/=", "??="}
                ),
                cursor,
            )
            name = _declaration_name(text, tokens, statement_start, assignment)
            if name:
                names.append(name)
            statement_start = cursor + 1
    return _ordered_union(names)


def _local_declaration_names(
    text: str, tokens: list[Token], start: int, end: int
) -> list[str]:
    names: list[str] = []
    statement_start = start
    paren_depth = 0
    bracket_depth = 0
    for cursor in range(start, end):
        value = tokens[cursor].value
        if value == "(":
            paren_depth += 1
        elif value == ")":
            paren_depth = max(0, paren_depth - 1)
        elif value == "[":
            bracket_depth += 1
        elif value == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif value in {"{", "}"} and paren_depth == 0 and bracket_depth == 0:
            statement_start = cursor + 1
        elif value == ";" and paren_depth == 0 and bracket_depth == 0:
            assignment = next(
                (
                    index
                    for index in range(statement_start, cursor)
                    if tokens[index].value in {"=", "+=", "-=", "*=", "/=", "??="}
                ),
                cursor,
            )
            name = _declaration_name(text, tokens, statement_start, assignment)
            if name:
                names.append(name)
            statement_start = cursor + 1
    return _ordered_union(names)


def parse_classes(text: str, tokens: list[Token]) -> tuple[list[dict[str, Any]], dict[int, int], dict[int, int]]:
    forward, reverse = token_pairs(tokens)
    classes: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if token.value not in {"class", "struct"}:
            continue
        brace = next(
            (cursor for cursor in range(index + 1, len(tokens)) if tokens[cursor].value in {"{", ";"}),
            None,
        )
        if brace is None or tokens[brace].value != "{" or brace not in forward:
            continue
        colon = next(
            (cursor for cursor in range(index + 1, brace) if tokens[cursor].value == ":"),
            None,
        )
        name_end = colon if colon is not None else brace
        name_candidates = [
            cursor
            for cursor in range(index + 1, name_end)
            if tokens[cursor].kind == "identifier" and tokens[cursor].value not in {"final"}
        ]
        if not name_candidates:
            continue
        name_index = name_candidates[-1]
        bases = _base_types(text, tokens, colon + 1, brace) if colon is not None else []
        body_end = forward[brace]
        members = _class_members(text, tokens, forward, reverse, tokens[name_index].value, brace + 1, body_end)
        classes.append(
            {
                "name": tokens[name_index].value,
                "kind": token.value,
                "base_types": bases,
                "location": _location(token, tokens[body_end]),
                "members": members,
                "body_range": (brace + 1, body_end),
            }
        )
    return classes, forward, reverse


def _class_members(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
    reverse: dict[int, int],
    class_name: str,
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    index = start
    nested_braces = 0
    while index < end:
        value = tokens[index].value
        if value == "{":
            nested_braces += 1
            index += 1
            continue
        if value == "}":
            nested_braces = max(0, nested_braces - 1)
            index += 1
            continue
        if value != "(" or nested_braces or index not in forward:
            index += 1
            continue
        close = forward[index]
        name_index = index - 1
        if name_index < start or tokens[name_index].kind != "identifier":
            index = close + 1
            continue
        member_start = _member_start(tokens, start, name_index)
        if any(token.value == "=" for token in tokens[member_start:index]):
            index = close + 1
            continue
        cursor = close + 1
        while cursor < end and tokens[cursor].value not in {"{", ";"}:
            if tokens[cursor].value == ":" and cursor + 1 < end:
                cursor += 1
            cursor += 1
        if cursor >= end:
            break
        has_body = tokens[cursor].value == "{" and cursor in forward
        final_index = forward[cursor] if has_body else cursor
        members.append(
            {
                "name": tokens[name_index].value,
                "parameters": _raw(text, tokens, index + 1, close),
                "signature": _raw(text, tokens, member_start, cursor),
                "location": _location(tokens[member_start], tokens[final_index]),
                "has_body": has_body,
                "is_constructor": tokens[name_index].value == class_name,
                "body_range": (cursor + 1, final_index) if has_body else None,
            }
        )
        index = final_index + 1
    return members


def parse_external_definitions(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index in range(1, len(tokens) - 3):
        if tokens[index].value != "::":
            continue
        if tokens[index - 1].kind != "identifier" or tokens[index + 1].kind != "identifier":
            continue
        open_index = index + 2
        if tokens[open_index].value != "(" or open_index not in forward:
            continue
        close = forward[open_index]
        cursor = close + 1
        while cursor < len(tokens) and tokens[cursor].value not in {"{", ";"}:
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor].value != "{" or cursor not in forward:
            continue
        body_end = forward[cursor]
        signature_start = _member_start(tokens, 0, index - 1)
        results.append(
            {
                "class_name": tokens[index - 1].value,
                "name": tokens[index + 1].value,
                "parameters": _raw(text, tokens, open_index + 1, close),
                "signature": _raw(text, tokens, signature_start, cursor),
                "location": _location(tokens[signature_start], tokens[body_end]),
                "body_range": (cursor + 1, body_end),
            }
        )
    return results


def parse_free_functions(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
) -> list[dict[str, Any]]:
    """Read top-level function definitions without building a general C++ AST."""
    excluded = {
        "alignof",
        "catch",
        "decltype",
        "for",
        "foreach",
        "if",
        "new",
        "sizeof",
        "switch",
        "while",
    }
    results: list[dict[str, Any]] = []
    brace_depth = 0
    index = 0
    while index < len(tokens):
        value = tokens[index].value
        if value == "{":
            brace_depth += 1
            index += 1
            continue
        if value == "}":
            brace_depth = max(0, brace_depth - 1)
            index += 1
            continue
        if value != "(" or brace_depth or index not in forward or index == 0:
            index += 1
            continue

        name_index = index - 1
        if (
            tokens[name_index].kind != "identifier"
            or tokens[name_index].value in excluded
            or (name_index > 0 and tokens[name_index - 1].value == "::")
            or (name_index > 0 and tokens[name_index - 1].value in {":", ","})
        ):
            index = forward[index] + 1
            continue

        declaration_start = _member_start(tokens, 0, name_index)
        if any(
            token.value in {"=", "return"}
            for token in tokens[declaration_start:index]
        ):
            index = forward[index] + 1
            continue

        close = forward[index]
        cursor = close + 1
        if cursor >= len(tokens) or tokens[cursor].value != "{" or cursor not in forward:
            index = close + 1
            continue

        body_end = forward[cursor]
        results.append(
            {
                "name": tokens[name_index].value,
                "parameters": _raw(text, tokens, index + 1, close),
                "signature": _raw(text, tokens, declaration_start, cursor),
                "location": _location(tokens[declaration_start], tokens[body_end]),
                "body_range": (cursor + 1, body_end),
            }
        )
        index = body_end + 1
    return results
