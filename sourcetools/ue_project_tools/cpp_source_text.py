"""Format syntax ranges while keeping literal and comment bytes intact."""
from __future__ import annotations

import re

from tree_sitter import Node


TOKEN_RE = re.compile(r'::|->|\.\.\.|"(?:\\.|[^"\\])*"|[A-Za-z_]\w*|\d+|[^\s]')
_PROTECTED = {"string_literal", "raw_string_literal", "char_literal", "comment"}


def _canonical_range(node: Node, source: bytes, end: int) -> str:
    """Join AST tokens; never re-lex source strings or merge separated operators."""
    result = ""
    cursor = node.start_byte
    stack = [node]
    while stack:
        current = stack.pop()
        if current.start_byte >= end:
            continue
        if current.type not in _PROTECTED and current.children:
            stack.extend(reversed(current.children))
            continue
        token = source[current.start_byte:min(current.end_byte, end)].decode("utf-8", errors="replace")
        if current.type not in _PROTECTED:
            token = re.sub(r"\s+", " ", token).strip()
        if not token:
            continue
        separated = bool(source[cursor:current.start_byte])
        if result and separated and (
            (result[-1].isalnum() or result[-1] == "_") and (token[0].isalnum() or token[0] == "_")
            or result[-1] in "+-*/%&|^<>=!~" and token[0] in "+-*/%&|^<>=!~"
        ):
            result += " "
        result += token
        if current.type == "comment" and token.startswith("//"):
            result += "\n"
        cursor = current.end_byte
    return result


def source_fragment(node: Node, source: bytes, *, canonical: bool = False,
                    end_byte: int | None = None, normalize_members: bool = False) -> str:
    end = node.end_byte if end_byte is None else end_byte
    if canonical:
        return _canonical_range(node, source, end).strip()
    protected = []
    member_operators = set()
    stack = [node]
    while stack:
        current = stack.pop()
        if current.start_byte >= end:
            continue
        if current.type in _PROTECTED:
            protected.append(current)
        else:
            if normalize_members and current.type == "field_expression":
                operator = current.child_by_field_name("operator")
                if operator and source[operator.start_byte:operator.end_byte] in {b"->", b"."}:
                    protected.append(operator)
                    member_operators.add(operator.start_byte)
            stack.extend(reversed(current.named_children))
    pieces = []
    cursor = node.start_byte
    for current in sorted(protected, key=lambda item: item.start_byte):
        plain = source[cursor:current.start_byte].decode("utf-8", errors="replace")
        if current.start_byte in member_operators:
            pieces.append(re.sub(r"\s+", " ", plain).rstrip())
            pieces.append(".")
            cursor = current.end_byte
            while cursor < end and source[cursor:cursor + 1] in {b" ", b"\t", b"\n", b"\r"}:
                cursor += 1
            continue
        pieces.append(re.sub(r"\s+", " ", plain))
        literal = source[current.start_byte:min(current.end_byte, end)].decode("utf-8", errors="replace")
        # A line comment must keep its terminating newline to preserve the next token.
        if current.type == "comment" and literal.startswith("//"):
            literal += "\n"
        pieces.append(literal)
        cursor = current.end_byte
    plain = source[cursor:end].decode("utf-8", errors="replace")
    pieces.append(re.sub(r"\s+", " ", plain))
    return "".join(pieces).strip()
