from __future__ import annotations

import re

from .source_tokens import lex_source


def _parameter_token_groups(parameters: str) -> list[list[str]]:
    tokens = lex_source(parameters)
    groups: list[list[str]] = []
    current: list[str] = []
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    angle_depth = 0
    in_default = False

    for token in tokens:
        value = token.value
        if value == "," and not any(
            (paren_depth, bracket_depth, brace_depth, angle_depth)
        ):
            groups.append(current)
            current = []
            in_default = False
            continue
        if value == "=" and not any(
            (paren_depth, bracket_depth, brace_depth, angle_depth)
        ):
            in_default = True
            continue

        if not in_default:
            current.append(value)
        if value == "(":
            paren_depth += 1
        elif value == ")":
            paren_depth = max(0, paren_depth - 1)
        elif value == "[":
            bracket_depth += 1
        elif value == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif value == "{":
            brace_depth += 1
        elif value == "}":
            brace_depth = max(0, brace_depth - 1)
        elif value == "<" and not in_default:
            angle_depth += 1
        elif value == ">" and not in_default:
            angle_depth = max(0, angle_depth - 1)
        elif value == ">>" and not in_default:
            angle_depth = max(0, angle_depth - 2)

    if current or tokens:
        groups.append(current)
    return groups


def _without_parameter_name(tokens: list[str]) -> tuple[str, ...]:
    if not tokens or tokens == ["void"]:
        return tuple(tokens)

    for index in range(1, len(tokens) - 1):
        if (
            re.match(r"^[A-Za-z_]\w*$", tokens[index])
            and tokens[index - 1] in {"*", "&", "&&"}
            and tokens[index + 1] == ")"
        ):
            return tuple(tokens[:index] + tokens[index + 1 :])

    for index in range(1, len(tokens) - 1):
        if (
            re.match(r"^[A-Za-z_]\w*$", tokens[index])
            and tokens[index + 1] == "["
        ):
            return tuple(tokens[:index] + tokens[index + 1 :])

    if not re.match(r"^[A-Za-z_]\w*$", tokens[-1]):
        return tuple(tokens)
    if len(tokens) > 1 and tokens[-2] == "::":
        return tuple(tokens)

    non_type_prefixes = {
        "class",
        "const",
        "enum",
        "struct",
        "typename",
        "volatile",
    }
    has_type_prefix = any(
        re.match(r"^[A-Za-z_]\w*$", value)
        and value not in non_type_prefixes
        for value in tokens[:-1]
    ) or any(
        value in {"*", "&", "&&", ">", ">>", "]", ")"}
        for value in tokens[:-1]
    )
    return tuple(tokens[:-1]) if has_type_prefix else tuple(tokens)


def parameter_signature(
    parameters: str,
) -> tuple[tuple[str, ...], ...]:
    signature = tuple(
        _without_parameter_name(group)
        for group in _parameter_token_groups(parameters)
    )
    return () if signature == (("void",),) else signature
