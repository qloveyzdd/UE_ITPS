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


_CONTROL_KEYWORDS = {
    "break",
    "case",
    "catch",
    "continue",
    "default",
    "do",
    "else",
    "for",
    "goto",
    "if",
    "return",
    "switch",
    "throw",
    "try",
    "while",
    "yield",
}

_NON_DECLARATION_STARTS = _CONTROL_KEYWORDS

_TYPE_KEYWORDS = {
    "auto",
    "bool",
    "char",
    "char16_t",
    "char32_t",
    "const",
    "double",
    "float",
    "int",
    "int8",
    "int16",
    "int32",
    "int64",
    "long",
    "mutable",
    "short",
    "signed",
    "static",
    "uint8",
    "uint16",
    "uint32",
    "uint64",
    "unsigned",
    "void",
    "volatile",
    "wchar_t",
}

_FORBIDDEN_CALLABLE_NAMES = _CONTROL_KEYWORDS | _TYPE_KEYWORDS

_DECLARATION_PREFIXES = {
    "explicit",
    "extern",
    "friend",
    "inline",
    "static",
    "virtual",
}


def _angle_delta(value: str) -> int:
    if value == "<":
        return 1
    if value == ">":
        return -1
    if value == ">>":
        return -2
    return 0


def _declaration_assignment(
    tokens: list[Token], start: int, end: int
) -> int:
    paren_depth = 0
    bracket_depth = 0
    angle_depth = 0
    for index in range(start, end):
        value = tokens[index].value
        if value == "(":
            paren_depth += 1
        elif value == ")":
            paren_depth = max(0, paren_depth - 1)
        elif value == "[":
            bracket_depth += 1
        elif value == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif paren_depth == 0 and bracket_depth == 0:
            angle_depth = max(0, angle_depth + _angle_delta(value))
            if (
                angle_depth == 0
                and value in {"=", "+=", "-=", "*=", "/=", "??="}
            ):
                return index
    return end


def _classify_declaration(
    tokens: list[Token],
    forward: dict[int, int],
    start: int,
    end: int,
) -> dict[str, Any]:
    """Classify one declaration-shaped token range without guessing."""
    while (
        start + 1 < end
        and tokens[start].value in {"public", "protected", "private"}
        and tokens[start + 1].value == ":"
    ):
        start += 2
    if start >= end:
        return {"kind": "ignored", "reason": "empty"}
    if tokens[start].value in _NON_DECLARATION_STARTS | {
        "class",
        "enum",
        "namespace",
        "struct",
        "typedef",
        "using",
    }:
        return {"kind": "ignored", "reason": "not-a-variable-or-callable"}

    declaration_end = _declaration_assignment(tokens, start, end)
    if declaration_end <= start:
        return {"kind": "unresolved", "reason": "missing_declarator"}

    paren_depth = 0
    bracket_depth = 0
    angle_depth = 0
    top_level_commas: list[int] = []
    structured_binding = False
    callable_open: int | None = None
    callable_name_index: int | None = None
    for index in range(start, declaration_end):
        value = tokens[index].value
        if value == "<" and paren_depth == 0 and bracket_depth == 0:
            angle_depth += 1
            continue
        if value in {">", ">>"} and paren_depth == 0 and bracket_depth == 0:
            angle_depth = max(0, angle_depth + _angle_delta(value))
            continue
        if value == "[":
            if (
                paren_depth == 0
                and angle_depth == 0
                and index > start
                and tokens[index - 1].value in {"auto", "&", "&&"}
            ):
                structured_binding = True
            bracket_depth += 1
            continue
        if value == "]":
            bracket_depth = max(0, bracket_depth - 1)
            continue
        if value == "(":
            if (
                paren_depth == 0
                and bracket_depth == 0
                and angle_depth == 0
                and index > start
                and tokens[index - 1].kind == "identifier"
                and tokens[index - 1].value not in _TYPE_KEYWORDS
            ):
                candidate = tokens[index - 1].value
                close = forward.get(index)
                if close is not None and close <= declaration_end:
                    if not (
                        re.fullmatch(r"[A-Z][A-Z0-9_]*", candidate)
                        and close + 1 < declaration_end
                    ):
                        callable_open = index
                        callable_name_index = index - 1
                        break
            paren_depth += 1
            continue
        if value == ")":
            paren_depth = max(0, paren_depth - 1)
            continue
        if (
            value == ","
            and paren_depth == 0
            and bracket_depth == 0
            and angle_depth == 0
        ):
            top_level_commas.append(index)

    if callable_open is not None and callable_name_index is not None:
        return {
            "kind": "callable",
            "name": tokens[callable_name_index].value,
            "name_index": callable_name_index,
            "parameter_open": callable_open,
        }
    if top_level_commas:
        return {"kind": "unresolved", "reason": "multiple_declarators"}
    if structured_binding:
        return {"kind": "unresolved", "reason": "structured_binding"}

    # Function and member-function pointers keep the declared name inside
    # parentheses; prefer the identifier immediately following '*'.
    pointer_name_index = next(
        (
            index
            for index in range(declaration_end - 1, start, -1)
            if tokens[index].kind == "identifier"
            and tokens[index - 1].value == "*"
        ),
        None,
    )
    if pointer_name_index is not None:
        return {
            "kind": "variable",
            "name": tokens[pointer_name_index].value,
            "name_index": pointer_name_index,
        }

    angle_depth = 0
    paren_depth = 0
    bracket_depth = 0
    candidates: list[int] = []
    for index in range(start, declaration_end):
        value = tokens[index].value
        if value == "<" and paren_depth == 0 and bracket_depth == 0:
            angle_depth += 1
        elif value in {">", ">>"} and paren_depth == 0 and bracket_depth == 0:
            angle_depth = max(0, angle_depth + _angle_delta(value))
        elif value == "(":
            paren_depth += 1
        elif value == ")":
            paren_depth = max(0, paren_depth - 1)
        elif value == "[":
            bracket_depth += 1
        elif value == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif (
            tokens[index].kind == "identifier"
            and angle_depth == 0
            and paren_depth == 0
            and bracket_depth == 0
            and tokens[index].value not in _TYPE_KEYWORDS | _DECLARATION_PREFIXES
        ):
            candidates.append(index)
    if not candidates:
        return {"kind": "unresolved", "reason": "ambiguous_declarator"}
    name_index = candidates[-1]
    if (
        name_index == start
        and re.fullmatch(r"[A-Z][A-Z0-9_]*", tokens[name_index].value)
    ):
        return {"kind": "ignored", "reason": "macro_declaration"}
    return {
        "kind": "variable",
        "name": tokens[name_index].value,
        "name_index": name_index,
    }


def _member_start(tokens: list[Token], lower: int, index: int) -> int:
    cursor = index - 1
    while cursor >= lower:
        if tokens[cursor].value in {";", "{", "}"}:
            return cursor + 1
        if tokens[cursor].value == "#":
            directive_line = tokens[cursor].line
            after_directive = cursor + 1
            while (
                after_directive < index
                and tokens[after_directive].line == directive_line
            ):
                after_directive += 1
            return after_directive
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
    forward, _ = token_pairs(tokens)
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
            classification = _classify_declaration(
                tokens, forward, statement_start, cursor
            )
            if classification["kind"] == "variable":
                names.append(classification["name"])
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


def _class_definition_brace(
    tokens: list[Token],
    forward: dict[int, int],
    class_index: int,
) -> int | None:
    if (
        class_index > 0
        and tokens[class_index - 1].value == "enum"
    ):
        return None
    cursor = class_index + 1
    while cursor < len(tokens):
        value = tokens[cursor].value
        if value == ";":
            return None
        if value == "{":
            return cursor if cursor in forward else None
        if value in {"class", "enum", "struct", "=", ")"}:
            return None
        if value == "(":
            if (
                cursor > class_index + 1
                and tokens[cursor - 1].value in {"alignas", "decltype"}
                and cursor in forward
            ):
                cursor = forward[cursor] + 1
                continue
            return None
        cursor += 1
    return None


def parse_classes(text: str, tokens: list[Token]) -> tuple[list[dict[str, Any]], dict[int, int], dict[int, int]]:
    forward, reverse = token_pairs(tokens)
    classes: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if token.value not in {"class", "struct"}:
            continue
        brace = _class_definition_brace(tokens, forward, index)
        if brace is None:
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
        specialization_open = next(
            (
                cursor
                for cursor in range(index + 1, name_end)
                if tokens[cursor].value == "<"
                and cursor > index + 1
                and tokens[cursor - 1].kind == "identifier"
            ),
            None,
        )
        name_index = (
            specialization_open - 1
            if specialization_open is not None
            else name_candidates[-1]
        )
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
        cursor = close + 1
        while cursor < end and tokens[cursor].value not in {"{", ";"}:
            cursor += 1
        if cursor >= end:
            break
        classification = _classify_declaration(
            tokens, forward, member_start, cursor
        )
        if (
            classification["kind"] != "callable"
            or classification.get("name_index") != name_index
            or classification.get("parameter_open") != index
        ):
            index = close + 1
            continue
        if any(token.value == "=" for token in tokens[member_start:index]):
            index = close + 1
            continue
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
    namespace_braces: set[int] = set()
    for namespace_index, token in enumerate(tokens):
        if token.value != "namespace":
            continue
        cursor = namespace_index + 1
        while cursor < len(tokens) and tokens[cursor].value not in {"{", ";"}:
            cursor += 1
        if (
            cursor < len(tokens)
            and tokens[cursor].value == "{"
            and cursor in forward
        ):
            namespace_braces.add(cursor)

    results: list[dict[str, Any]] = []
    active_braces: list[int] = []
    index = 1
    while index < len(tokens) - 3:
        value = tokens[index].value
        if value == "{":
            active_braces.append(index)
            index += 1
            continue
        if value == "}":
            if (
                active_braces
                and forward.get(active_braces[-1]) == index
            ):
                active_braces.pop()
            index += 1
            continue
        if any(brace not in namespace_braces for brace in active_braces):
            index += 1
            continue
        if tokens[index].value != "::":
            index += 1
            continue
        if tokens[index - 1].kind != "identifier":
            index += 1
            continue
        name_index = index + 1
        if tokens[name_index].value == "~":
            name_index += 1
        if (
            name_index >= len(tokens)
            or tokens[name_index].kind != "identifier"
        ):
            index += 1
            continue
        open_index = name_index + 1
        if tokens[open_index].value != "(" or open_index not in forward:
            index += 1
            continue
        close = forward[open_index]
        cursor = close + 1
        initializer_list = False
        while cursor < len(tokens):
            if tokens[cursor].value == ";":
                break
            if tokens[cursor].value == ":":
                initializer_list = True
                cursor += 1
                continue
            if tokens[cursor].value in {"(", "["} and cursor in forward:
                cursor = forward[cursor] + 1
                continue
            if tokens[cursor].value == "{" and cursor in forward:
                previous = tokens[cursor - 1]
                if initializer_list and (
                    previous.kind == "identifier"
                    or previous.value in {">", ">>", "]"}
                ):
                    cursor = forward[cursor] + 1
                    continue
                break
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor].value != "{" or cursor not in forward:
            index = close + 1
            continue
        body_end = forward[cursor]
        signature_start = _member_start(tokens, 0, index - 1)
        results.append(
            {
                "class_name": tokens[index - 1].value,
                "name": tokens[name_index].value,
                "parameters": _raw(text, tokens, open_index + 1, close),
                "signature": _raw(text, tokens, signature_start, cursor),
                "location": _location(tokens[signature_start], tokens[body_end]),
                "body_range": (cursor + 1, body_end),
            }
        )
        index = body_end + 1
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
            or (
                name_index > 1
                and tokens[name_index - 1].value == "~"
                and tokens[name_index - 2].value == "::"
            )
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
