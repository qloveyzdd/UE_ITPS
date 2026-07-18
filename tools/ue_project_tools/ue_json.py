from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _strip_comments(text: str) -> tuple[str, bool]:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    found = False
    while index < len(text):
        char = text[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if text.startswith("//", index):
            found = True
            while index < len(text) and text[index] != "\n":
                output.append(" ")
                index += 1
            continue
        if text.startswith("/*", index):
            found = True
            output.extend("  ")
            index += 2
            while index < len(text) and not text.startswith("*/", index):
                output.append("\n" if text[index] == "\n" else " ")
                index += 1
            if index < len(text):
                output.extend("  ")
                index += 2
            continue
        output.append(char)
        index += 1
    return "".join(output), found


def _strip_trailing_commas(text: str) -> tuple[str, bool]:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    found = False
    while index < len(text):
        char = text[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "]}":
                output.append(" ")
                found = True
                index += 1
                continue
        output.append(char)
        index += 1
    return "".join(output), found


def _reject_constant(value: str) -> Any:
    raise ValueError(f"Non-standard JSON constant is not allowed: {value}")


def read_ue_json(path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    text = path.read_text(encoding="utf-8-sig")
    without_comments, had_comments = _strip_comments(text)
    normalized, had_trailing_commas = _strip_trailing_commas(without_comments)
    duplicate_fields: list[str] = []

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                duplicate_fields.append(key)
            value[key] = item
        return value

    value = json.loads(
        normalized,
        object_pairs_hook=object_pairs,
        parse_constant=_reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    extensions: list[str] = []
    if had_comments:
        extensions.append("comments")
    if had_trailing_commas:
        extensions.append("trailing-commas")
    return value, extensions, sorted(set(duplicate_fields))
