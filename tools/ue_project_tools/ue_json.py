from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class _ObjectPairs:
    def __init__(self, pairs: list[tuple[str, Any]]) -> None:
        self.pairs = pairs


def _strip_comments(text: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
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
            while index < len(text) and text[index] != "\n":
                output.append(" ")
                index += 1
            continue
        if text.startswith("/*", index):
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
    return "".join(output)


def _strip_trailing_commas(text: str) -> str:
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
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
                index += 1
                continue
        output.append(char)
        index += 1
    return "".join(output)


def _reject_constant(value: str) -> Any:
    raise ValueError(f"Non-standard JSON constant is not allowed: {value}")


def _pointer_child(pointer: str, value: str) -> str:
    escaped = value.replace("~", "~0").replace("/", "~1")
    return f"{pointer}/{escaped}"


def _materialize_json(
    value: Any,
    pointer: str,
    duplicate_fields: list[dict[str, Any]],
) -> Any:
    if isinstance(value, _ObjectPairs):
        result: dict[str, Any] = {}
        counts: dict[str, int] = {}
        for key, item in value.pairs:
            child_pointer = _pointer_child(pointer, key)
            counts[key] = counts.get(key, 0) + 1
            result[key] = _materialize_json(item, child_pointer, duplicate_fields)
        for key, occurrence_count in counts.items():
            if occurrence_count > 1:
                duplicate_fields.append(
                    {
                        "field": key,
                        "descriptor_pointer": _pointer_child(pointer, key),
                        "occurrence_count": occurrence_count,
                    }
                )
        return result
    if isinstance(value, list):
        return [
            _materialize_json(item, f"{pointer}/{index}", duplicate_fields)
            for index, item in enumerate(value)
        ]
    return value


def read_ue_json(
    path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    text = path.read_text(encoding="utf-8-sig")
    without_comments = _strip_comments(text)
    normalized = _strip_trailing_commas(without_comments)
    parsed = json.loads(
        normalized,
        object_pairs_hook=_ObjectPairs,
        parse_constant=_reject_constant,
    )
    duplicate_fields: list[dict[str, Any]] = []
    value = _materialize_json(parsed, "", duplicate_fields)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    duplicate_fields.sort(key=lambda item: str(item["descriptor_pointer"]))
    return value, duplicate_fields
