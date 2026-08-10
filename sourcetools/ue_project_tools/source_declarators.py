from __future__ import annotations

import re
from typing import Any

from .source_tokens import Token, _raw


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

_NON_DECLARATION_STARTS = _CONTROL_KEYWORDS | {"{", "}"}

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

_MEMBER_ANNOTATION_MACROS = {
    "GENERATED_BODY",
    "GENERATED_IINTERFACE_BODY",
    "GENERATED_UCLASS_BODY",
    "GENERATED_UINTERFACE_BODY",
    "GENERATED_USTRUCT_BODY",
    "UFUNCTION",
}

_SOURCE_ANNOTATION_MACROS = _MEMBER_ANNOTATION_MACROS | {
    "UCLASS",
    "UENUM",
    "UINTERFACE",
    "UPROPERTY",
    "USTRUCT",
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
    tokens: list[Token],
    start: int,
    end: int,
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
    if tokens[start].value == "friend":
        return {"kind": "ignored", "reason": "friend-declaration"}
    if tokens[start].value in _NON_DECLARATION_STARTS | {
        "class",
        "enum",
        "namespace",
        "struct",
        "typedef",
        "using",
    }:
        return {
            "kind": "ignored",
            "reason": "not-a-variable-or-callable",
        }

    declaration_end = _declaration_assignment(tokens, start, end)
    if declaration_end <= start:
        return {
            "kind": "unresolved",
            "reason": "missing_declarator",
        }

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
                        re.fullmatch(
                            r"[A-Z][A-Z0-9_]*",
                            candidate,
                        )
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
        return {
            "kind": "unresolved",
            "reason": "multiple_declarators",
        }
    if structured_binding:
        return {
            "kind": "unresolved",
            "reason": "structured_binding",
        }

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
        elif (
            value in {">", ">>"}
            and paren_depth == 0
            and bracket_depth == 0
        ):
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
            and tokens[index].value
            not in _TYPE_KEYWORDS | _DECLARATION_PREFIXES
        ):
            candidates.append(index)
    if not candidates:
        return {
            "kind": "unresolved",
            "reason": "ambiguous_declarator",
        }
    name_index = candidates[-1]
    if (
        name_index == start
        and re.fullmatch(
            r"[A-Z][A-Z0-9_]*",
            tokens[name_index].value,
        )
    ):
        return {
            "kind": "ignored",
            "reason": "macro_declaration",
        }
    return {
        "kind": "variable",
        "name": tokens[name_index].value,
        "name_index": name_index,
    }


def _callable_has_initializer_expression(
    tokens: list[Token],
    forward: dict[int, int],
    classification: dict[str, Any],
) -> bool:
    """Identify call-shaped declarators that contain value expressions."""
    if classification.get("kind") != "callable":
        return False
    open_index = int(classification["parameter_open"])
    close_index = forward.get(open_index)
    if close_index is None:
        return False
    return any(
        token.kind in {"char", "number", "string"}
        for token in tokens[open_index + 1 : close_index]
    )


def _member_start(
    tokens: list[Token],
    lower: int,
    index: int,
) -> int:
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


def _member_declaration_prefix(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
    start: int,
    end: int,
) -> tuple[int, list[str]]:
    cursor = start
    macros: list[str] = []
    while cursor < end:
        if (
            cursor + 1 < end
            and tokens[cursor].value
            in {"public", "protected", "private"}
            and tokens[cursor + 1].value == ":"
        ):
            cursor += 2
            continue
        if (
            cursor + 1 < end
            and tokens[cursor].value in _MEMBER_ANNOTATION_MACROS
            and tokens[cursor + 1].value == "("
            and cursor + 1 in forward
            and forward[cursor + 1] < end
        ):
            close = forward[cursor + 1]
            if tokens[cursor].value == "UFUNCTION":
                macros.append(
                    _raw(
                        text,
                        tokens,
                        cursor,
                        close + 1,
                    )
                )
            cursor = close + 1
            continue
        break
    return cursor, macros


def _declaration_name(
    text: str,
    tokens: list[Token],
    start: int,
    end: int,
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
