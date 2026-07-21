from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable

from .common import iter_files, normalized


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    start: int
    end: int
    line: int


_MULTI_OPERATORS = tuple(
    sorted(
        (
            "::",
            "->",
            "==",
            "!=",
            "<=",
            ">=",
            "&&",
            "||",
            "+=",
            "-=",
            "*=",
            "/=",
            "??=",
            "??",
            "=>",
            "++",
            "--",
            "<<",
            ">>",
        ),
        key=len,
        reverse=True,
    )
)


def lex_source(text: str) -> list[Token]:
    """Tokenize the C#/C++ subset used by UE rule and module entry files."""
    tokens: list[Token] = []
    index = 0
    line = 1

    def advance(raw: str) -> None:
        nonlocal line
        line += raw.count("\n")

    while index < len(text):
        start = index
        start_line = line
        if text[index].isspace():
            while index < len(text) and text[index].isspace():
                index += 1
            advance(text[start:index])
            continue
        if text.startswith("//", index):
            end = text.find("\n", index + 2)
            index = len(text) if end < 0 else end
            advance(text[start:index])
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = len(text) if end < 0 else end + 2
            advance(text[start:index])
            continue

        string_prefix = next(
            (
                prefix
                for prefix in ('$@"', '@$"', '@"', '$"', 'TEXT("', 'L"', 'u8"', 'u"', 'U"', '"')
                if text.startswith(prefix, index)
            ),
            None,
        )
        if string_prefix is not None:
            verbatim = "@" in string_prefix
            quote_index = index + string_prefix.rfind('"')
            index = quote_index + 1
            while index < len(text):
                if verbatim and text.startswith('""', index):
                    index += 2
                    continue
                if text[index] == '"':
                    index += 1
                    if string_prefix == 'TEXT("' and index < len(text) and text[index] == ")":
                        index += 1
                    break
                if not verbatim and text[index] == "\\":
                    index = min(len(text), index + 2)
                else:
                    index += 1
            raw = text[start:index]
            tokens.append(Token("string", raw, start, index, start_line))
            advance(raw)
            continue
        if text[index] == "'":
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    index = min(len(text), index + 2)
                elif text[index] == "'":
                    index += 1
                    break
                else:
                    index += 1
            raw = text[start:index]
            tokens.append(Token("char", raw, start, index, start_line))
            advance(raw)
            continue
        if text[index].isalpha() or text[index] == "_":
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                index += 1
            raw = text[start:index]
            tokens.append(Token("identifier", raw, start, index, start_line))
            advance(raw)
            continue
        if text[index].isdigit():
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] in "._"):
                index += 1
            raw = text[start:index]
            tokens.append(Token("number", raw, start, index, start_line))
            advance(raw)
            continue

        operator = next(
            (candidate for candidate in _MULTI_OPERATORS if text.startswith(candidate, index)),
            None,
        )
        raw = operator or text[index]
        index += len(raw)
        tokens.append(Token("symbol", raw, start, index, start_line))
        advance(raw)
    return tokens


def token_pairs(tokens: list[Token]) -> tuple[dict[int, int], dict[int, int]]:
    opening = {"(": ")", "[": "]", "{": "}"}
    closing = {value: key for key, value in opening.items()}
    stack: list[tuple[str, int]] = []
    forward: dict[int, int] = {}
    reverse: dict[int, int] = {}
    for index, token in enumerate(tokens):
        if token.value in opening:
            stack.append((token.value, index))
        elif token.value in closing:
            expected = closing[token.value]
            for stack_index in range(len(stack) - 1, -1, -1):
                if stack[stack_index][0] == expected:
                    _, open_index = stack.pop(stack_index)
                    forward[open_index] = index
                    reverse[index] = open_index
                    break
    return forward, reverse


def _raw(text: str, tokens: list[Token], start: int, end: int) -> str:
    if start >= end or start < 0 or end > len(tokens):
        return ""
    return re.sub(r"\s+", " ", text[tokens[start].start : tokens[end - 1].end]).strip()


def _location(first: Token, last: Token | None = None) -> dict[str, int]:
    final = last or first
    return {
        "line": first.line,
        "end_line": final.line,
    }


def _decode_string(token: Token) -> str | None:
    raw = token.value
    if raw.startswith('TEXT("') and raw.endswith('")'):
        raw = raw[5:-1]
    prefixes = ('$@"', '@$"', '@"', '$"', 'u8"', 'L"', 'u"', 'U"', '"')
    prefix = next((item for item in prefixes if raw.startswith(item)), None)
    if prefix is None or not raw.endswith('"'):
        return None
    content = raw[len(prefix) : -1]
    if "@" in prefix:
        return content.replace('""', '"')
    replacements = {
        '\\"': '"',
        "\\\\": "\\",
        "\\n": "\n",
        "\\r": "\r",
        "\\t": "\t",
    }
    for old, new in replacements.items():
        content = content.replace(old, new)
    return content


def _evaluation(tokens: list[Token]) -> dict[str, Any]:
    literals = [
        decoded
        for token in tokens
        if token.kind == "string" and (decoded := _decode_string(token)) is not None
    ]
    if not literals:
        return {"status": "unresolved", "literal_values": []}
    ignored_identifiers = {"new", "string", "String", "TEXT"}
    unresolved_identifiers = [
        token.value
        for token in tokens
        if token.kind == "identifier"
        and token.value not in ignored_identifiers
        and token.value not in {"true", "false", "null"}
    ]
    unsupported_symbols = [
        token.value
        for token in tokens
        if token.kind == "symbol" and token.value not in {",", "{", "}", "[", "]", "(", ")"}
    ]
    interpolated = any(
        token.kind == "string" and "$" in token.value[: token.value.find('"')]
        for token in tokens
    )
    status = "partial" if unresolved_identifiers or unsupported_symbols or interpolated else "literal"
    return {"status": status, "literal_values": literals}


def _split_arguments(tokens: list[Token], start: int, end: int) -> list[tuple[int, int]]:
    arguments: list[tuple[int, int]] = []
    depth = 0
    item_start = start
    for index in range(start, end):
        value = tokens[index].value
        if value in {"(", "[", "{"}:
            depth += 1
        elif value in {")",
            "]",
            "}",
        }:
            depth = max(0, depth - 1)
        elif value == "," and depth == 0:
            if item_start < index:
                arguments.append((item_start, index))
            item_start = index + 1
    if item_start < end:
        arguments.append((item_start, end))
    return arguments


def _base_types(text: str, tokens: list[Token], start: int, end: int) -> list[str]:
    segments = _split_arguments(tokens, start, end)
    results: list[str] = []
    for segment_start, segment_end in segments:
        values = [
            token.value
            for token in tokens[segment_start:segment_end]
            if token.value not in {"public", "private", "protected", "virtual"}
        ]
        value = "".join(values).strip()
        if value:
            results.append(value)
    return results


def _member_start(tokens: list[Token], lower: int, index: int) -> int:
    cursor = index - 1
    while cursor >= lower:
        if tokens[cursor].value in {";", "{", "}"}:
            return cursor + 1
        cursor -= 1
    return lower


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


def _ordered_union(*groups: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            if item and item not in seen:
                seen.add(item)
                result.append(item)
    return result


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

    def append_switch_cases(lower: int, upper: int) -> None:
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
            )

    def walk(lower: int, upper: int) -> None:
        index = lower
        while index < upper:
            value = tokens[index].value
            if value == "if":
                index = parse_if(index, upper)
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
                )
                if value == "switch":
                    append_switch_cases(body_start, body_end)
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


def _raw_from_values(tokens: Iterable[Token]) -> str:
    values = [token.value for token in tokens]
    if not values:
        return ""
    rendered = " ".join(values)
    rendered = re.sub(r"\s*([.(),\[\]{}])\s*", r"\1", rendered)
    rendered = re.sub(r"\s*(::|->)\s*", r"\1", rendered)
    rendered = re.sub(r"([!~])\s+", r"\1", rendered)
    rendered = re.sub(r"\s+", " ", rendered)
    return rendered.strip()


def preprocessor_conditions(text: str) -> dict[int, list[dict[str, Any]]]:
    active: list[dict[str, Any]] = []
    result: dict[int, list[dict[str, Any]]] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#if "):
            active.append({"kind": "preprocessor", "expression": stripped[4:].strip(), "branch": "then", "start_line": line_number})
        elif stripped.startswith("#ifdef "):
            active.append({"kind": "preprocessor", "expression": f"defined({stripped[7:].strip()})", "branch": "then", "start_line": line_number})
        elif stripped.startswith("#ifndef "):
            active.append({"kind": "preprocessor", "expression": f"!defined({stripped[8:].strip()})", "branch": "then", "start_line": line_number})
        elif stripped.startswith("#elif ") and active:
            active[-1] = {**active[-1], "expression": stripped[6:].strip(), "branch": "elif"}
        elif stripped.startswith("#else") and active:
            active[-1] = {**active[-1], "branch": "else"}
        elif stripped.startswith("#endif") and active:
            active.pop()
        result[line_number] = [dict(item) for item in active]
    return result


def preprocessor_control_contexts(text: str) -> dict[int, list[dict[str, Any]]]:
    active: list[dict[str, Any]] = []
    result: dict[int, list[dict[str, Any]]] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        expression = ""
        if stripped.startswith("#if "):
            expression = stripped[4:].strip()
        elif stripped.startswith("#ifdef "):
            expression = stripped[7:].strip()
        elif stripped.startswith("#ifndef "):
            expression = stripped[8:].strip()
        if expression:
            active.append(
                {
                    "start_line": line_number,
                    "kind": "preprocessor",
                    "references": _control_references(lex_source(expression)),
                }
            )
        elif stripped.startswith("#elif ") and active:
            references = _control_references(lex_source(stripped[6:].strip()))
            active[-1]["references"] = _ordered_union(
                active[-1]["references"], references
            )
        elif stripped.startswith("#else"):
            pass
        elif stripped.startswith("#endif") and active:
            active.pop()
        result[line_number] = [dict(item) for item in active]
    return result


def _member_chain_start(tokens: list[Token], reverse: dict[int, int], name_index: int, lower: int) -> int:
    start = name_index
    while start - 1 >= lower and tokens[start - 1].value in {".", "::", "->"}:
        operand = start - 2
        if operand < lower:
            break
        if tokens[operand].value == ")" and operand in reverse:
            open_index = reverse[operand]
            callee_name = open_index - 1
            if callee_name >= lower and tokens[callee_name].kind == "identifier":
                start = _member_chain_start(tokens, reverse, callee_name, lower)
                continue
        if tokens[operand].value == "]" and operand in reverse:
            open_index = reverse[operand]
            indexed_name = open_index - 1
            if indexed_name >= lower and tokens[indexed_name].kind == "identifier":
                start = _member_chain_start(tokens, reverse, indexed_name, lower)
                continue
        if tokens[operand].kind == "identifier":
            start = operand
            continue
        break
    return start


def _conditions_for(
    token_index: int,
    token: Token,
    spans: list[dict[str, Any]],
    preprocessor: dict[int, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    contextual = [
        span
        for span in spans
        if span["start"] <= token_index < span["end"]
    ]
    controls = [dict(item) for item in preprocessor.get(token.line, [])]
    controls.extend(
        {
            **dict(span["condition"]),
            "start_line": span["start_line"],
            "span_width": span["end"] - span["start"],
        }
        for span in contextual
    )
    controls.sort(
        key=lambda item: (
            int(item.get("start_line", 0)),
            -int(item.get("span_width", 0)),
        )
    )
    return controls


def _control_metadata_for(
    token_index: int,
    token: Token,
    spans: list[dict[str, Any]],
    preprocessor: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    contextual = [
        span for span in spans if span["start"] <= token_index < span["end"]
    ]
    contextual.extend(preprocessor.get(token.line, []))
    contextual.sort(key=lambda item: item["start_line"])
    flattened = [item for item in contextual if item.get("kind") != "case"]
    path = [str(item["kind"]) for item in flattened]
    references = _ordered_union(
        *(item.get("references", []) for item in flattened)
    )
    result: dict[str, Any] = {
        "applicability": "conditional" if path else "direct"
    }
    if path:
        result["control_path"] = path
        result["control_details"] = [
            {
                key: value
                for key, value in item.items()
                if key
                in {
                    "kind",
                    "expression",
                    "branch",
                    "references",
                    "start_line",
                }
            }
            for item in contextual
        ]
    if references:
        result["related_symbols"] = references
    return result


def _merge_control_metadata(
    metadata: dict[str, Any], controls: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    items = list(controls)
    if not items:
        return metadata
    path = [*metadata.get("control_path", [])]
    path.extend(str(item["kind"]) for item in items)
    references = _ordered_union(
        metadata.get("related_symbols", []),
        *(item.get("references", []) for item in items),
    )
    result = {**metadata, "applicability": "conditional", "control_path": path}
    details = [*metadata.get("control_details", [])]
    details.extend(dict(item) for item in items)
    if details:
        result["control_details"] = details
    if references:
        result["related_symbols"] = references
    return result


def control_expression_ranges(
    tokens: list[Token], forward: dict[int, int], start: int, end: int
) -> list[dict[str, Any]]:
    """Locate expressions evaluated by control constructs without treating bodies as headers."""
    ranges: list[dict[str, Any]] = []

    def add_range(
        lower: int,
        upper: int,
        controls: Iterable[dict[str, Any]] = (),
        excluded_targets: Iterable[str] = (),
    ) -> None:
        if lower < upper:
            ranges.append(
                {
                    "start": lower,
                    "end": upper,
                    "controls": [dict(item) for item in controls],
                    "excluded_targets": set(excluded_targets),
                }
            )

    def split_for_header(lower: int, upper: int) -> list[tuple[int, int]]:
        separators: list[int] = []
        depth = 0
        for index in range(lower, upper):
            value = tokens[index].value
            if value in {"(", "[", "{"}:
                depth += 1
            elif value in {")", "]", "}"}:
                depth = max(0, depth - 1)
            elif value == ";" and depth == 0:
                separators.append(index)
        boundaries = [lower, *separators, upper]
        return [
            (boundaries[index] + (1 if index else 0), boundaries[index + 1])
            for index in range(len(boundaries) - 1)
        ]

    def parse_if(
        index: int,
        upper: int,
        prior_references: Iterable[str] = (),
        is_else_if: bool = False,
    ) -> int:
        if (
            index + 1 >= upper
            or tokens[index + 1].value != "("
            or index + 1 not in forward
        ):
            return index + 1
        condition_close = forward[index + 1]
        prior = list(prior_references)
        controls = (
            [{"kind": "if", "references": prior}]
            if is_else_if
            else []
        )
        add_range(index + 2, condition_close, controls)
        current_references = _ordered_union(
            prior,
            _control_references(tokens[index + 2 : condition_close]),
        )
        then_start, then_end, after_then = _statement_after(
            tokens, forward, condition_close + 1, upper
        )
        walk(then_start, then_end)
        if after_then >= upper or tokens[after_then].value != "else":
            return max(after_then, condition_close + 1)
        branch_start = after_then + 1
        if branch_start < upper and tokens[branch_start].value == "if":
            return parse_if(branch_start, upper, current_references, True)
        else_start, else_end, after_else = _statement_after(
            tokens, forward, branch_start, upper
        )
        walk(else_start, else_end)
        return max(after_else, branch_start)

    def walk(lower: int, upper: int) -> None:
        index = lower
        while index < upper:
            value = tokens[index].value
            if value == "if":
                index = parse_if(index, upper)
                continue
            if (
                value in {"for", "foreach", "while", "switch"}
                and index + 1 < upper
                and tokens[index + 1].value == "("
                and index + 1 in forward
            ):
                header_close = forward[index + 1]
                header_start = index + 2
                header = tokens[header_start:header_close]
                excluded = _loop_local_names(value, header)
                if value == "for":
                    segments = split_for_header(header_start, header_close)
                    if segments:
                        add_range(*segments[0], excluded_targets=excluded)
                    if len(segments) > 1:
                        add_range(*segments[1], excluded_targets=excluded)
                    if len(segments) > 2:
                        condition_references = _control_references(
                            tokens[segments[1][0] : segments[1][1]], excluded
                        )
                        add_range(
                            *segments[2],
                            controls=[
                                {
                                    "kind": "for",
                                    "references": condition_references,
                                }
                            ],
                            excluded_targets=excluded,
                        )
                elif value == "foreach":
                    in_index = next(
                        (
                            cursor
                            for cursor in range(header_start, header_close)
                            if tokens[cursor].value == "in"
                        ),
                        header_start - 1,
                    )
                    add_range(
                        in_index + 1,
                        header_close,
                        excluded_targets=excluded,
                    )
                else:
                    add_range(header_start, header_close)
                body_start, body_end, after_body = _statement_after(
                    tokens, forward, header_close + 1, upper
                )
                walk(body_start, body_end)
                index = max(after_body, header_close + 1)
                continue
            if value == "catch":
                cursor = index + 1
                if cursor < upper and tokens[cursor].value == "(" and cursor in forward:
                    cursor = forward[cursor] + 1
                if (
                    cursor + 1 < upper
                    and tokens[cursor].value == "when"
                    and tokens[cursor + 1].value == "("
                    and cursor + 1 in forward
                ):
                    filter_close = forward[cursor + 1]
                    add_range(
                        cursor + 2,
                        filter_close,
                        controls=[{"kind": "catch", "references": []}],
                    )
                    cursor = filter_close + 1
                body_start, body_end, after_body = _statement_after(
                    tokens, forward, cursor, upper
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
    return ranges


def _expression_gate_controls(
    tokens: list[Token],
    forward: dict[int, int],
    start: int,
    operation_index: int,
) -> list[dict[str, Any]]:
    controls: list[dict[str, Any]] = []
    for index in range(start, operation_index):
        value = tokens[index].value
        if value not in {"&&", "||", "??", "?"}:
            continue
        containing_closes = [
            close
            for open_index, close in forward.items()
            if open_index < index < close
        ]
        if containing_closes and min(containing_closes) < operation_index:
            continue
        controls.append(
            {
                "kind": "ternary" if value == "?" else "short_circuit",
                "references": _control_references(tokens[start:index]),
                "expression": _raw_from_values(tokens[start:index]),
                "start_line": tokens[index].line,
            }
        )
    return controls


def _assignment_value_end(
    tokens: list[Token], start: int, assignment_index: int, end: int
) -> int:
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    for index in range(start, assignment_index):
        value = tokens[index].value
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
    initial = (paren_depth, bracket_depth, brace_depth)
    for index in range(assignment_index + 1, end):
        value = tokens[index].value
        if value == ")" and paren_depth == initial[0] and initial[0] > 0:
            return index
        if value == "]" and bracket_depth == initial[1] and initial[1] > 0:
            return index
        if value == "}" and brace_depth == initial[2] and initial[2] > 0:
            return index
        if value in {";", ","} and (paren_depth, bracket_depth, brace_depth) == initial:
            return index
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
    return end


def _expression_operations(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
    reverse: dict[int, int],
    expression_range: dict[str, Any],
    spans: list[dict[str, Any]],
    pp_context: dict[int, list[dict[str, str]]],
    flow_spans: list[dict[str, Any]],
    pp_flow: dict[int, list[dict[str, Any]]],
) -> list[tuple[int, dict[str, Any]]]:
    start = int(expression_range["start"])
    end = int(expression_range["end"])
    excluded_targets = set(expression_range.get("excluded_targets", set()))
    base_controls = list(expression_range.get("controls", []))
    results: list[tuple[int, dict[str, Any]]] = []

    for assignment_index in range(start, end):
        operator = tokens[assignment_index].value
        if operator not in {"=", "+=", "-=", "*=", "/=", "??="}:
            continue
        name_index = assignment_index - 1
        while name_index >= start and tokens[name_index].kind != "identifier":
            name_index -= 1
        if name_index < start:
            continue
        target_start = _member_chain_start(tokens, reverse, name_index, start)
        target = _raw(text, tokens, target_start, assignment_index)
        target_root = target.split(".", 1)[0]
        if target_root in excluded_targets:
            continue
        value_end = _assignment_value_end(tokens, start, assignment_index, end)
        if value_end <= assignment_index + 1:
            continue
        metadata = _control_metadata_for(
            assignment_index,
            tokens[assignment_index],
            flow_spans,
            pp_flow,
        )
        metadata = _merge_control_metadata(metadata, base_controls)
        metadata = _merge_control_metadata(
            metadata,
            _expression_gate_controls(tokens, forward, start, target_start),
        )
        operation: dict[str, Any] = {
            "kind": "assignment",
            "target": target,
            "operator": operator,
            "value_expression": _raw(
                text, tokens, assignment_index + 1, value_end
            ),
            "expression": _raw(text, tokens, target_start, value_end),
            "evaluation": _evaluation(tokens[assignment_index + 1 : value_end]),
            "conditions": _conditions_for(
                assignment_index,
                tokens[assignment_index],
                spans,
                pp_context,
            ),
            "location": _location(tokens[target_start], tokens[value_end - 1]),
            **metadata,
        }
        results.append((assignment_index, operation))

    for update_index in range(start, end):
        operator = tokens[update_index].value
        if operator not in {"++", "--"}:
            continue
        prefix = update_index + 1 < end and tokens[update_index + 1].kind == "identifier"
        if prefix:
            target_start = update_index + 1
            target_end = target_start + 1
            while (
                target_end + 1 < end
                and tokens[target_end].value in {".", "::", "->"}
                and tokens[target_end + 1].kind == "identifier"
            ):
                target_end += 2
            expression_start = update_index
            expression_end = target_end
        else:
            name_index = update_index - 1
            if name_index < start or tokens[name_index].kind != "identifier":
                continue
            target_start = _member_chain_start(tokens, reverse, name_index, start)
            target_end = update_index
            expression_start = target_start
            expression_end = update_index + 1
        target = _raw(text, tokens, target_start, target_end)
        if target.split(".", 1)[0] in excluded_targets:
            continue
        metadata = _control_metadata_for(
            update_index, tokens[update_index], flow_spans, pp_flow
        )
        metadata = _merge_control_metadata(metadata, base_controls)
        metadata = _merge_control_metadata(
            metadata,
            _expression_gate_controls(tokens, forward, start, expression_start),
        )
        operation = {
            "kind": "assignment",
            "target": target,
            "operator": operator,
            "value_expression": operator,
            "expression": _raw(text, tokens, expression_start, expression_end),
            "evaluation": {"status": "unresolved", "literal_values": []},
            "conditions": _conditions_for(
                update_index, tokens[update_index], spans, pp_context
            ),
            "location": _location(
                tokens[expression_start], tokens[expression_end - 1]
            ),
            **metadata,
        }
        results.append((update_index, operation))

    excluded_calls = {
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
    for open_index in range(start, end):
        if tokens[open_index].value != "(" or open_index not in forward:
            continue
        close = forward[open_index]
        if close >= end or open_index == start:
            continue
        name_index = open_index - 1
        if (
            tokens[name_index].kind != "identifier"
            or tokens[name_index].value in excluded_calls
        ):
            continue
        callee_start = _member_chain_start(tokens, reverse, name_index, start)
        if callee_start > start and tokens[callee_start - 1].value == "new":
            continue
        argument_ranges = _split_arguments(tokens, open_index + 1, close)
        arguments = [
            {
                "expression": _raw(text, tokens, argument_start, argument_end),
                "evaluation": _evaluation(tokens[argument_start:argument_end]),
            }
            for argument_start, argument_end in argument_ranges
        ]
        evaluation_tokens = [
            token
            for argument_start, argument_end in argument_ranges
            for token in tokens[argument_start:argument_end]
        ]
        metadata = _control_metadata_for(
            name_index, tokens[name_index], flow_spans, pp_flow
        )
        metadata = _merge_control_metadata(metadata, base_controls)
        metadata = _merge_control_metadata(
            metadata,
            _expression_gate_controls(tokens, forward, start, callee_start),
        )
        operation = {
            "kind": "invocation",
            "callee": _raw_from_values(tokens[callee_start:open_index]),
            "arguments": arguments,
            "expression": _raw(text, tokens, callee_start, close + 1),
            "evaluation": _evaluation(evaluation_tokens),
            "conditions": _conditions_for(
                name_index, tokens[name_index], spans, pp_context
            ),
            "location": _location(tokens[callee_start], tokens[close]),
            **metadata,
        }
        results.append((open_index, operation))
    return results


def parse_operations(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
    reverse: dict[int, int],
    start: int,
    end: int,
    include_control_metadata: bool = False,
) -> list[dict[str, Any]]:
    spans = condition_spans(tokens, forward, start, end)
    pp_context = preprocessor_conditions(text)
    flow_spans = control_spans(tokens, forward, start, end) if include_control_metadata else []
    pp_flow = preprocessor_control_contexts(text) if include_control_metadata else {}
    operations: list[tuple[int, dict[str, Any]]] = []
    if include_control_metadata:
        for expression_range in control_expression_ranges(
            tokens, forward, start, end
        ):
            operations.extend(
                _expression_operations(
                    text,
                    tokens,
                    forward,
                    reverse,
                    expression_range,
                    spans,
                    pp_context,
                    flow_spans,
                    pp_flow,
                )
            )
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
            statement_start = cursor + 1
        elif value == "}" and paren_depth == 0 and bracket_depth == 0:
            brace_depth = max(0, brace_depth - 1)
            statement_start = cursor + 1
        elif (
            value == ":"
            and paren_depth == 0
            and bracket_depth == 0
            and statement_start < cursor
            and tokens[statement_start].value in {"case", "default"}
        ):
            statement_start = cursor + 1
        elif value == ";" and paren_depth == 0 and bracket_depth == 0:
            segment_start = statement_start
            while segment_start < cursor and tokens[segment_start].value in {"else"}:
                segment_start += 1
            if segment_start < cursor and tokens[segment_start].value == "if" and segment_start + 1 in forward:
                segment_start = forward[segment_start + 1] + 1
            operations.extend(
                _statement_operations(
                    text,
                    tokens,
                    forward,
                    reverse,
                    segment_start,
                    cursor,
                    spans,
                    pp_context,
                    flow_spans,
                    pp_flow,
                    include_control_metadata,
                )
            )
            statement_start = cursor + 1
    return [item for _, item in sorted(operations, key=lambda pair: pair[0])]


def _statement_operations(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
    reverse: dict[int, int],
    start: int,
    end: int,
    spans: list[dict[str, Any]],
    pp_context: dict[int, list[dict[str, str]]],
    flow_spans: list[dict[str, Any]],
    pp_flow: dict[int, list[dict[str, Any]]],
    include_control_metadata: bool,
) -> list[tuple[int, dict[str, Any]]]:
    if start >= end:
        return []
    results: list[tuple[int, dict[str, Any]]] = []
    depth = 0
    assignment_index: int | None = None
    for index in range(start, end):
        value = tokens[index].value
        if value in {"(", "[", "{"}:
            depth += 1
        elif value in {")",
            "]",
            "}",
        }:
            depth = max(0, depth - 1)
        elif depth == 0 and value in {"=", "+=", "-=", "*=", "/=", "??="}:
            assignment_index = index
            break
    if assignment_index is not None and assignment_index > start:
        target_start = start
        declaration_name = _declaration_name(
            text, tokens, start, assignment_index
        )
        if declaration_name is not None:
            target_start = assignment_index - 1
        value_tokens = tokens[assignment_index + 1 : end]
        operation: dict[str, Any] = {
            "kind": "assignment",
            "target": _raw(text, tokens, target_start, assignment_index),
            "operator": tokens[assignment_index].value,
            "value_expression": _raw(text, tokens, assignment_index + 1, end),
            "expression": _raw(text, tokens, target_start, end),
            "evaluation": _evaluation(value_tokens),
            "conditions": _conditions_for(assignment_index, tokens[assignment_index], spans, pp_context),
            "location": _location(tokens[target_start], tokens[end - 1]),
        }
        if declaration_name is not None:
            operation["declared_name"] = declaration_name
        if include_control_metadata:
            operation.update(
                _control_metadata_for(
                    assignment_index,
                    tokens[assignment_index],
                    flow_spans,
                    pp_flow,
                )
            )
        results.append((assignment_index, operation))

    excluded = {"if", "for", "foreach", "while", "switch", "catch", "sizeof", "decltype", "alignof", "new", "base"}
    for open_index in range(start, end):
        if tokens[open_index].value != "(" or open_index not in forward:
            continue
        close = forward[open_index]
        if close > end or open_index == start:
            continue
        name_index = open_index - 1
        if tokens[name_index].kind != "identifier" or tokens[name_index].value in excluded:
            continue
        callee_start = _member_chain_start(tokens, reverse, name_index, start)
        callee = _raw_from_values(tokens[callee_start:open_index])
        argument_ranges = _split_arguments(tokens, open_index + 1, close)
        arguments = [
            {
                "expression": _raw(text, tokens, argument_start, argument_end),
                "evaluation": _evaluation(tokens[argument_start:argument_end]),
            }
            for argument_start, argument_end in argument_ranges
        ]
        evaluation_tokens = [
            token
            for argument_start, argument_end in argument_ranges
            for token in tokens[argument_start:argument_end]
        ]
        operation = {
            "kind": "invocation",
            "callee": callee,
            "arguments": arguments,
            "expression": _raw(text, tokens, callee_start, close + 1),
            "evaluation": _evaluation(evaluation_tokens),
            "conditions": _conditions_for(name_index, tokens[name_index], spans, pp_context),
            "location": _location(tokens[callee_start], tokens[close]),
        }
        if include_control_metadata:
            operation.update(
                _control_metadata_for(name_index, tokens[name_index], flow_spans, pp_flow)
            )
        results.append((open_index, operation))
    return results


_MODULE_RULE_KINDS = {
    "PublicDependencyModuleNames": "public_dependency",
    "PrivateDependencyModuleNames": "private_dependency",
    "DynamicallyLoadedModuleNames": "dynamic_dependency",
    "PublicIncludePathModuleNames": "public_include_module",
    "PrivateIncludePathModuleNames": "private_include_module",
    "PublicIncludePaths": "public_include_path",
    "PrivateIncludePaths": "private_include_path",
    "PublicSystemIncludePaths": "public_system_include_path",
    "PublicDefinitions": "public_definition",
    "PrivateDefinitions": "private_definition",
}


def _rule_annotation(operation: dict[str, Any]) -> dict[str, str] | None:
    if operation["kind"] == "invocation":
        callee = str(operation.get("callee", ""))
        match = re.search(
            r"(?:^|[.>])(?P<member>[A-Za-z_]\w*)\."
            r"(?P<action>AddRange|Add|Remove|RemoveAll)$",
            callee,
        )
        if match and match.group("member") in _MODULE_RULE_KINDS:
            return {
                "kind": _MODULE_RULE_KINDS[match.group("member")],
                "member": match.group("member"),
                "action": match.group("action"),
            }
    else:
        target = str(operation.get("target", "")).split(".")[-1]
        if target in _MODULE_RULE_KINDS:
            return {
                "kind": _MODULE_RULE_KINDS[target],
                "member": target,
                "action": "assign",
            }
        if target in {"PCHUsage", "PrivatePCHHeaderFile", "SharedPCHHeaderFile"}:
            return {"kind": "pch", "member": target, "action": "assign"}
        if target in {"bEnforceIWYU", "IWYUSupport", "bLegacyPublicIncludePaths"}:
            return {"kind": "iwyu", "member": target, "action": "assign"}
    return None


def parse_rule_file(path: Path, required_base_type: str) -> dict[str, Any]:
    resolved = path.resolve()
    text = resolved.read_text(encoding="utf-8-sig", errors="replace")
    tokens = lex_source(text)
    classes, forward, reverse = parse_classes(text, tokens)
    known_bases = {required_base_type}
    selected: list[dict[str, Any]] = []
    base_resolution: dict[str, str] = {}
    pending = list(classes)
    while pending:
        changed = False
        for item in list(pending):
            if any(base.split("<", 1)[0] in known_bases for base in item["base_types"]):
                selected.append(item)
                base_resolution[item["name"]] = "confirmed"
                known_bases.add(item["name"])
                pending.remove(item)
                changed = True
        if not changed:
            break

    if required_base_type == "TargetRules" and resolved.name.casefold().endswith(
        ".target.cs"
    ):
        expected_name = resolved.name[: -len(".Target.cs")] + "Target"
        for item in list(pending):
            has_target_constructor = any(
                member["is_constructor"]
                and re.search(r"\bTargetInfo\b", str(member["parameters"]))
                for member in item["members"]
            )
            if item["name"].casefold() == expected_name.casefold() and has_target_constructor:
                selected.append(item)
                base_resolution[item["name"]] = "unresolved"
                pending.remove(item)

    selected.sort(key=lambda item: int(item["location"]["line"]))

    rules_classes: list[dict[str, Any]] = []
    for item in selected:
        methods: list[dict[str, Any]] = []
        for member in item["members"]:
            operation_items: list[dict[str, Any]] = []
            declared_names: list[str] = []
            if member["body_range"]:
                declared_names = _local_declaration_names(
                    text,
                    tokens,
                    member["body_range"][0],
                    member["body_range"][1],
                )
                operation_items = parse_operations(
                    text,
                    tokens,
                    forward,
                    reverse,
                    member["body_range"][0],
                    member["body_range"][1],
                    include_control_metadata=required_base_type
                    in {"ModuleRules", "TargetRules"},
                )
                if required_base_type == "ModuleRules":
                    for operation in operation_items:
                        annotation = _rule_annotation(operation)
                        if annotation:
                            operation["rule"] = annotation
            methods.append(
                {
                    "name": member["name"],
                    "parameters": member["parameters"],
                    "signature": member["signature"],
                    "is_constructor": member["is_constructor"],
                    "location": member["location"],
                    "declared_names": declared_names,
                    "operations": operation_items,
                }
            )
        method_names = {method["name"] for method in methods}
        calls: list[dict[str, Any]] = []
        for method in methods:
            for operation in method["operations"]:
                if operation["kind"] != "invocation":
                    continue
                callee = str(operation["callee"]).split(".")[-1].split("::")[-1]
                if callee in method_names and callee != method["name"]:
                    calls.append(
                        {
                            "caller": method["name"],
                            "callee": callee,
                            "location": operation["location"],
                        }
                    )
        unique_calls = {
            (call["caller"], call["callee"], call["location"]["line"]): call
            for call in calls
        }
        rules_classes.append(
            {
                "name": item["name"],
                "base_types": item["base_types"],
                "base_resolution": base_resolution[item["name"]],
                "location": item["location"],
                "declared_fields": _class_field_names(
                    text,
                    tokens,
                    item["body_range"][0],
                    item["body_range"][1],
                ),
                "methods": methods,
                "same_file_calls": sorted(
                    unique_calls.values(),
                    key=lambda value: (value["caller"], value["callee"], value["location"]["line"]),
                ),
            }
        )
    return {"path": normalized(resolved), "rules_classes": rules_classes}


def registration_macros(text: str, tokens: list[Token]) -> list[dict[str, Any]]:
    forward, _ = token_pairs(tokens)
    results: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if not token.value.startswith("IMPLEMENT_") or not token.value.endswith("MODULE"):
            continue
        if index + 1 >= len(tokens) or tokens[index + 1].value != "(" or index + 1 not in forward:
            continue
        close = forward[index + 1]
        ranges = _split_arguments(tokens, index + 2, close)
        arguments = [_raw(text, tokens, start, end) for start, end in ranges]
        results.append(
            {
                "macro": token.value,
                "module_class": arguments[0] if arguments else None,
                "module_name": arguments[1] if len(arguments) > 1 else None,
                "arguments": arguments,
                "location": _location(token, tokens[close]),
            }
        )
    return results


def parse_cpp_file(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    text = resolved.read_text(encoding="utf-8-sig", errors="replace")
    tokens = lex_source(text)
    classes, forward, reverse = parse_classes(text, tokens)
    external = parse_external_definitions(text, tokens, forward)
    free_functions = parse_free_functions(text, tokens, forward)
    return {
        "path": normalized(resolved),
        "text": text,
        "tokens": tokens,
        "forward": forward,
        "reverse": reverse,
        "classes": classes,
        "external_definitions": external,
        "free_functions": free_functions,
        "registration_macros": registration_macros(text, tokens),
    }


def source_files(module_dir: Path) -> list[Path]:
    suffixes = (".h", ".hpp", ".cpp", ".cc")
    return sorted(
        {
            path.resolve()
            for suffix in suffixes
            for path in iter_files(module_dir, suffix)
        },
        key=lambda path: normalized(path).casefold(),
    )
