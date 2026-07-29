from __future__ import annotations

from typing import Any

from .source_declarations import (
    _SOURCE_ANNOTATION_MACROS,
    _callable_has_initializer_expression,
    _classify_declaration,
    _member_start,
)
from .source_namespaces import namespace_scopes
from .source_tokens import Token, _location, _raw


def _namespace_braces(
    tokens: list[Token],
    forward: dict[int, int],
) -> set[int]:
    return {
        int(scope["open"])
        for scope in namespace_scopes(tokens, forward)
    }


def parse_external_definitions(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
) -> list[dict[str, Any]]:
    namespace_braces = _namespace_braces(tokens, forward)
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
            if active_braces and forward.get(active_braces[-1]) == index:
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
        if (
            cursor >= len(tokens)
            or tokens[cursor].value != "{"
            or cursor not in forward
        ):
            index = close + 1
            continue
        body_end = forward[cursor]
        qualifier_start = index - 1
        while (
            qualifier_start >= 2
            and tokens[qualifier_start - 1].value == "::"
            and tokens[qualifier_start - 2].kind == "identifier"
        ):
            qualifier_start -= 2
        qualifier = "::".join(
            token.value
            for token in tokens[qualifier_start:index]
            if token.kind == "identifier"
        )
        signature_start = _member_start(tokens, 0, qualifier_start)
        results.append(
            {
                "class_name": tokens[index - 1].value,
                "qualifier": qualifier,
                "name": tokens[name_index].value,
                "parameters": _raw(text, tokens, open_index + 1, close),
                "signature": _raw(text, tokens, signature_start, cursor),
                "location": _location(
                    tokens[signature_start],
                    tokens[body_end],
                ),
                "body_range": (cursor + 1, body_end),
                "_token_index": signature_start,
                "_name_index": name_index,
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
    namespace_braces = _namespace_braces(tokens, forward)
    active_braces: list[int] = []
    index = 0
    while index < len(tokens):
        value = tokens[index].value
        if value == "{":
            active_braces.append(index)
            index += 1
            continue
        if value == "}":
            if active_braces and forward.get(active_braces[-1]) == index:
                active_braces.pop()
            index += 1
            continue
        if (
            value != "("
            or any(
                brace not in namespace_braces
                for brace in active_braces
            )
            or index not in forward
            or index == 0
        ):
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
        if (
            cursor >= len(tokens)
            or tokens[cursor].value != "{"
            or cursor not in forward
        ):
            index = close + 1
            continue

        body_end = forward[cursor]
        results.append(
            {
                "name": tokens[name_index].value,
                "parameters": _raw(text, tokens, index + 1, close),
                "signature": _raw(text, tokens, declaration_start, cursor),
                "location": _location(
                    tokens[declaration_start],
                    tokens[body_end],
                ),
                "body_range": (cursor + 1, body_end),
                "_token_index": declaration_start,
                "_name_index": name_index,
            }
        )
        index = body_end + 1
    return results


def parse_free_function_declarations(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
) -> list[dict[str, Any]]:
    """Read file- or namespace-scope free-function declarations."""
    excluded = {
        "alignof",
        "catch",
        "decltype",
        "for",
        "if",
        "sizeof",
        "static_assert",
        "switch",
        "while",
    }
    namespace_braces = _namespace_braces(tokens, forward)
    results: list[dict[str, Any]] = []
    active_braces: list[int] = []
    index = 0
    while index < len(tokens):
        value = tokens[index].value
        if value == "{":
            active_braces.append(index)
            index += 1
            continue
        if value == "}":
            if active_braces and forward.get(active_braces[-1]) == index:
                active_braces.pop()
            index += 1
            continue
        if (
            value != "("
            or any(
                brace not in namespace_braces
                for brace in active_braces
            )
            or index not in forward
            or index == 0
        ):
            index += 1
            continue

        name_index = index - 1
        name_token = tokens[name_index]
        if (
            name_token.kind != "identifier"
            or name_token.value in excluded
            or name_token.value in _SOURCE_ANNOTATION_MACROS
            or name_token.value.startswith(
                (
                    "DECLARE_",
                    "DEFINE_",
                    "IMPLEMENT_",
                    "UE_DECLARE_",
                    "UE_DEFINE_",
                )
            )
            or (name_index > 0 and tokens[name_index - 1].value == "::")
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
        while cursor < len(tokens) and tokens[cursor].value not in {";", "{"}:
            cursor += 1
        if (
            cursor >= len(tokens)
            or tokens[cursor].value != ";"
            or declaration_start >= name_index
        ):
            index = close + 1
            continue
        classification = _classify_declaration(
            tokens,
            forward,
            declaration_start,
            cursor,
        )
        if (
            classification["kind"] != "callable"
            or classification.get("name_index") != name_index
            or classification.get("parameter_open") != index
            or _callable_has_initializer_expression(
                tokens,
                forward,
                classification,
            )
        ):
            index = close + 1
            continue
        results.append(
            {
                "name": name_token.value,
                "parameters": _raw(text, tokens, index + 1, close),
                "signature": _raw(
                    text,
                    tokens,
                    declaration_start,
                    cursor,
                ),
                "location": _location(
                    tokens[declaration_start],
                    tokens[cursor],
                ),
                "_token_index": declaration_start,
                "_name_index": name_index,
            }
        )
        index = cursor + 1
    return results
