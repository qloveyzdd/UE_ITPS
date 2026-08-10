from __future__ import annotations

from typing import Any

from .source_tokens import Token, _ordered_union, _raw_from_values


_CONTROL_REFERENCE_KEYWORDS = {
    "as",
    "bool",
    "byte",
    "catch",
    "char",
    "decimal",
    "defined",
    "double",
    "false",
    "float",
    "for",
    "foreach",
    "if",
    "in",
    "int",
    "is",
    "long",
    "new",
    "null",
    "object",
    "out",
    "ref",
    "sbyte",
    "short",
    "string",
    "switch",
    "true",
    "uint",
    "ulong",
    "ushort",
    "var",
    "when",
    "while",
}


def _statement_after(tokens: list[Token], forward: dict[int, int], start: int, end: int) -> tuple[int, int, int]:
    if start >= end:
        return start, start, start
    if tokens[start].value == "{" and start in forward:
        close = min(forward[start], end)
        return start + 1, close, close + 1
    depth = 0
    cursor = start
    while cursor < end:
        value = tokens[cursor].value
        if value in {"(", "[", "{"}:
            depth += 1
        elif value in {")",
            "]",
            "}",
        }:
            if depth == 0:
                break
            depth -= 1
        elif value == ";" and depth == 0:
            return start, cursor + 1, cursor + 1
        cursor += 1
    return start, cursor, cursor


def condition_spans(tokens: list[Token], forward: dict[int, int], start: int, end: int) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []

    def walk(lower: int, upper: int) -> None:
        index = lower
        while index < upper:
            if tokens[index].value == "if" and index + 1 < upper and tokens[index + 1].value == "(" and index + 1 in forward:
                condition_close = forward[index + 1]
                then_start, then_end, after_then = _statement_after(tokens, forward, condition_close + 1, upper)
                expression = _raw_from_values(tokens[index + 2 : condition_close])
                spans.append(
                    {
                        "start": then_start,
                        "end": then_end,
                        "start_line": tokens[index].line,
                        "condition": {"kind": "if", "expression": expression, "branch": "then"},
                    }
                )
                walk(then_start, then_end)
                if after_then < upper and tokens[after_then].value == "else":
                    else_start, else_end, after_else = _statement_after(tokens, forward, after_then + 1, upper)
                    spans.append(
                        {
                            "start": else_start,
                            "end": else_end,
                            "start_line": tokens[index].line,
                            "condition": {"kind": "if", "expression": expression, "branch": "else"},
                        }
                    )
                    walk(else_start, else_end)
                    index = max(after_else, after_then + 1)
                else:
                    index = max(after_then, condition_close + 1)
                continue
            if tokens[index].value == "{" and index in forward:
                close = min(forward[index], upper)
                walk(index + 1, close)
                index = close + 1
                continue
            index += 1

    walk(start, end)
    return spans


def _control_references(
    tokens: list[Token], excluded_roots: Iterable[str] = ()
) -> list[str]:
    excluded = set(excluded_roots)
    references: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.kind != "identifier" or token.value in _CONTROL_REFERENCE_KEYWORDS:
            index += 1
            continue
        if index > 0 and tokens[index - 1].value in {".", "::", "->"}:
            index += 1
            continue
        parts = [token.value]
        cursor = index + 1
        while (
            cursor + 1 < len(tokens)
            and tokens[cursor].value in {".", "::", "->"}
            and tokens[cursor + 1].kind == "identifier"
        ):
            parts.append(tokens[cursor + 1].value)
            cursor += 2
        if parts[0] not in excluded:
            references.append(".".join(parts))
        index = cursor
    return _ordered_union(references)


def _loop_local_names(kind: str, header: list[Token]) -> set[str]:
    if kind == "foreach":
        for index, token in enumerate(header):
            if token.value == "in" and index > 0:
                return {header[index - 1].value}
        return set()
    if kind != "for":
        return set()
    initializer_end = next(
        (index for index, token in enumerate(header) if token.value == ";"),
        len(header),
    )
    initializer = header[:initializer_end]
    for index in range(1, len(initializer)):
        if (
            initializer[index].kind == "identifier"
            and initializer[index - 1].kind == "identifier"
        ):
            return {initializer[index].value}
    return set()


def control_spans(
    tokens: list[Token], forward: dict[int, int], start: int, end: int
) -> list[dict[str, Any]]:
    """Return flat enclosing control facts for ModuleRules relevance output."""
    spans: list[dict[str, Any]] = []

    def append_span(
        kind: str,
        body_start: int,
        body_end: int,
        control_index: int,
        references: Iterable[str],
        *,
        expression: str = "",
        branch: str = "",
        guard: str = "",
    ) -> None:
        span: dict[str, Any] = {
            "start": body_start,
            "end": body_end,
            "start_line": tokens[control_index].line,
            "kind": kind,
            "references": list(references),
        }
        if expression:
            span["expression"] = expression
        if branch:
            span["branch"] = branch
        if guard:
            span["guard"] = guard
        spans.append(span)

    def parse_if(
        index: int, upper: int, prior_references: Iterable[str] = ()
    ) -> int:
        if (
            index + 1 >= upper
            or tokens[index + 1].value != "("
            or index + 1 not in forward
        ):
            return index + 1
        condition_close = forward[index + 1]
        expression = _raw_from_values(tokens[index + 2 : condition_close])
        condition_references = _ordered_union(
            prior_references,
            _control_references(tokens[index + 2 : condition_close]),
        )
        then_start, then_end, after_then = _statement_after(
            tokens, forward, condition_close + 1, upper
        )
        append_span(
            "if",
            then_start,
            then_end,
            index,
            condition_references,
            expression=expression,
            branch="then",
        )
        walk(then_start, then_end)
        if after_then >= upper or tokens[after_then].value != "else":
            return max(after_then, condition_close + 1)
        branch_start = after_then + 1
        if branch_start < upper and tokens[branch_start].value == "if":
            return parse_if(branch_start, upper, condition_references)
        else_start, else_end, after_else = _statement_after(
            tokens, forward, branch_start, upper
        )
        append_span(
            "if",
            else_start,
            else_end,
            index,
            condition_references,
            expression=expression,
            branch="else",
        )
        walk(else_start, else_end)
        return max(after_else, branch_start)

    def append_switch_cases(lower: int, upper: int, selector: str) -> None:
        labels: list[tuple[int, int, str, list[str]]] = []
        depth = 0
        index = lower
        while index < upper:
            value = tokens[index].value
            if value in {"(", "[", "{"}:
                depth += 1
            elif value in {")", "]", "}"}:
                depth = max(0, depth - 1)
            elif depth == 0 and value in {"case", "default"}:
                colon = index + 1
                nested = 0
                while colon < upper:
                    candidate = tokens[colon].value
                    if candidate in {"(", "[", "{"}:
                        nested += 1
                    elif candidate in {")", "]", "}"}:
                        nested = max(0, nested - 1)
                    elif candidate == ":" and nested == 0:
                        break
                    colon += 1
                expression_tokens = (
                    tokens[index + 1 : colon] if value == "case" else []
                )
                labels.append(
                    (
                        index,
                        colon,
                        _raw_from_values(expression_tokens),
                        _control_references(expression_tokens),
                    )
                )
                index = colon
            index += 1
        for label_index, (control_index, colon, expression, references) in enumerate(
            labels
        ):
            body_end = (
                labels[label_index + 1][0]
                if label_index + 1 < len(labels)
                else upper
            )
            append_span(
                "case",
                colon + 1,
                body_end,
                control_index,
                references,
                expression=expression,
                guard=(
                    f"switch({selector}) == {expression}"
                    if expression
                    else f"switch({selector}): default"
                ),
            )

    def for_guard(header: list[Token]) -> str:
        separators: list[int] = []
        depth = 0
        for index, token in enumerate(header):
            if token.value in {"(", "[", "{"}:
                depth += 1
            elif token.value in {")", "]", "}"}:
                depth = max(0, depth - 1)
            elif token.value == ";" and depth == 0:
                separators.append(index)
        if len(separators) < 2:
            return ""
        return _raw_from_values(header[separators[0] + 1 : separators[1]])

    def walk(lower: int, upper: int) -> None:
        index = lower
        while index < upper:
            value = tokens[index].value
            if value == "if":
                index = parse_if(index, upper)
                continue
            if value == "do":
                body_start, body_end, after_body = _statement_after(
                    tokens, forward, index + 1, upper
                )
                cursor = after_body
                if (
                    cursor + 1 < upper
                    and tokens[cursor].value == "while"
                    and tokens[cursor + 1].value == "("
                    and cursor + 1 in forward
                ):
                    condition_close = forward[cursor + 1]
                    condition_tokens = tokens[cursor + 2 : condition_close]
                    expression = _raw_from_values(condition_tokens)
                    append_span(
                        "do",
                        body_start,
                        body_end,
                        index,
                        _control_references(condition_tokens),
                        expression=expression,
                    )
                    walk(body_start, body_end)
                    index = condition_close + 1
                    if index < upper and tokens[index].value == ";":
                        index += 1
                    continue
            if (
                value in {"for", "foreach", "while", "switch"}
                and index + 1 < upper
                and tokens[index + 1].value == "("
                and index + 1 in forward
            ):
                header_close = forward[index + 1]
                body_start, body_end, after_body = _statement_after(
                    tokens, forward, header_close + 1, upper
                )
                header = tokens[index + 2 : header_close]
                references = _control_references(
                    header, _loop_local_names(value, header)
                )
                append_span(
                    value,
                    body_start,
                    body_end,
                    index,
                    references,
                    expression=_raw_from_values(header),
                    guard=(
                        for_guard(header)
                        if value == "for"
                        else (
                            f"foreach: {_raw_from_values(header)}"
                            if value == "foreach"
                            else (
                                _raw_from_values(header)
                                if value == "while"
                                else ""
                            )
                        )
                    ),
                )
                if value == "switch":
                    append_switch_cases(
                        body_start, body_end, _raw_from_values(header)
                    )
                walk(body_start, body_end)
                index = max(after_body, header_close + 1)
                continue
            if value == "catch":
                cursor = index + 1
                catch_tokens: list[Token] = []
                filter_tokens: list[Token] = []
                if cursor < upper and tokens[cursor].value == "(" and cursor in forward:
                    catch_tokens = tokens[cursor + 1 : forward[cursor]]
                    cursor = forward[cursor] + 1
                if (
                    cursor + 1 < upper
                    and tokens[cursor].value == "when"
                    and tokens[cursor + 1].value == "("
                    and cursor + 1 in forward
                ):
                    filter_close = forward[cursor + 1]
                    filter_tokens = tokens[cursor + 2 : filter_close]
                    cursor = filter_close + 1
                body_start, body_end, after_body = _statement_after(
                    tokens, forward, cursor, upper
                )
                append_span(
                    "catch",
                    body_start,
                    body_end,
                    index,
                    _control_references(filter_tokens),
                    expression=_raw_from_values(filter_tokens or catch_tokens),
                )
                walk(body_start, body_end)
                index = max(after_body, cursor)
                continue
            if value == "{" and index in forward:
                close = min(forward[index], upper)
                walk(index + 1, close)
                index = close + 1
                continue
            index += 1

    walk(start, end)
    return spans
