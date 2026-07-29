from __future__ import annotations

from typing import Any

from .source_tokens import Token


ANONYMOUS_NAMESPACE = "(anonymous)"


def namespace_scopes(
    tokens: list[Token],
    forward: dict[int, int],
) -> list[dict[str, Any]]:
    """Return named and anonymous namespace body ranges."""
    scopes: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if token.value != "namespace":
            continue
        cursor = index + 1
        while cursor < len(tokens) and tokens[cursor].value not in {"{", ";"}:
            cursor += 1
        if (
            cursor >= len(tokens)
            or tokens[cursor].value != "{"
            or cursor not in forward
        ):
            continue
        segments = [
            candidate.value
            for candidate in tokens[index + 1 : cursor]
            if candidate.kind == "identifier"
            and candidate.value != "inline"
        ]
        scopes.append(
            {
                "segments": segments or [ANONYMOUS_NAMESPACE],
                "open": cursor,
                "close": forward[cursor],
            }
        )
    return sorted(scopes, key=lambda item: int(item["open"]))


def namespace_at(
    scopes: list[dict[str, Any]],
    token_index: int,
) -> str | None:
    segments = [
        str(segment)
        for scope in scopes
        if int(scope["open"]) < token_index < int(scope["close"])
        for segment in scope["segments"]
    ]
    return "::".join(segments) if segments else None


def qualified_name(namespace: str | None, lexical_name: str) -> str:
    return f"{namespace}::{lexical_name}" if namespace else lexical_name
