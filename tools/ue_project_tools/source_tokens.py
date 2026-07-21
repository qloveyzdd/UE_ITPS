from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


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
                for prefix in ('$@"', '@$"', '@"', '$"', 'L"', 'u8"', 'u"', 'U"', '"')
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


def delimiter_problems(tokens: list[Token]) -> list[dict[str, Any]]:
    opening = {"(": ")", "[": "]", "{": "}"}
    closing = {value: key for key, value in opening.items()}
    stack: list[Token] = []
    problems: list[dict[str, Any]] = []
    for token in tokens:
        if token.value in opening:
            stack.append(token)
            continue
        if token.value not in closing:
            continue
        if not stack:
            problems.append(
                {
                    "severity": "error",
                    "code": "source-delimiter-unexpected-closing",
                    "line": token.line,
                    "delimiter": token.value,
                    "message": f"Unexpected closing delimiter {token.value}",
                }
            )
            continue
        if stack[-1].value == closing[token.value]:
            stack.pop()
            continue
        current = stack.pop()
        problems.append(
            {
                "severity": "error",
                "code": "source-delimiter-mismatch",
                "line": token.line,
                "delimiter": token.value,
                "opening_delimiter": current.value,
                "opening_line": current.line,
                "expected": opening[current.value],
                "message": (
                    f"Closing delimiter {token.value} does not match "
                    f"{current.value} opened on line {current.line}"
                ),
            }
        )
    for token in stack:
        problems.append(
            {
                "severity": "error",
                "code": "source-delimiter-unmatched-opening",
                "line": token.line,
                "delimiter": token.value,
                "expected": opening[token.value],
                "message": f"Opening delimiter {token.value} is not closed",
            }
        )
    return problems


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


def _ordered_union(*groups: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            if item and item not in seen:
                seen.add(item)
                result.append(item)
    return result


def _raw_from_values(tokens: Iterable[Token]) -> str:
    values = [token.value for token in tokens]
    if not values:
        return ""
    rendered = " ".join(values)
    rendered = re.sub(r"\s*([.(),\[\]{}])\s*", r"\1", rendered)
    rendered = re.sub(r"\s*(::|->)\s*", r"\1", rendered)
    rendered = re.sub(
        r"\s*(&&|\|\||\?\?|==|!=|<=|>=)\s*", r" \1 ", rendered
    )
    rendered = re.sub(r"([!~])\s+", r"\1", rendered)
    rendered = re.sub(r"\s+", " ", rendered)
    return rendered.strip()
