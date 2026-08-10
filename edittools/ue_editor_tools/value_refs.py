from __future__ import annotations

import re
from typing import Any, Iterator


_OBJECT_PATH = re.compile(
    r"(?:(?P<class>[A-Za-z_][\w:]*)')?"
    r"(?P<path>/(?:Game|Script|Engine|[A-Za-z_][\w]*)/[^'\s,\)\]]+)"
    r"'?"
)
_TAG_VALUE = re.compile(r"(?:TagName\s*=\s*\"|GameplayTag\s*=\s*\")([^\"]+)")


def normalize_object_path(value: str) -> str:
    text = value.strip().strip('"').strip("'")
    if "'" in text and text.endswith("'"):
        text = text.split("'", 1)[1][:-1]
    return text.replace("\\", "/")


def string_references(value: str) -> list[dict[str, str]]:
    references: dict[tuple[str, str], dict[str, str]] = {}
    for match in _OBJECT_PATH.finditer(value):
        path = normalize_object_path(match.group("path"))
        wrapper = str(match.group("class") or "")
        kind = (
            "class"
            if path.startswith("/Script/") or wrapper.endswith("Class")
            else "asset"
        )
        references[(kind, path)] = {"kind": kind, "target": path}
    for match in _TAG_VALUE.finditer(value):
        tag = match.group(1).strip()
        if tag:
            references[("gameplay_tag", tag)] = {
                "kind": "gameplay_tag",
                "target": tag,
            }
    return [references[key] for key in sorted(references)]


def walk_value_references(value: Any, field: str = "") -> Iterator[dict[str, str]]:
    if isinstance(value, dict):
        for key in sorted(value, key=lambda item: str(item).casefold()):
            child = f"{field}.{key}" if field else str(key)
            yield from walk_value_references(value[key], child)
        return
    if isinstance(value, (list, tuple, set)):
        for index, item in enumerate(value):
            child = f"{field}[{index}]" if field else f"[{index}]"
            yield from walk_value_references(item, child)
        return
    if not isinstance(value, str):
        return
    for reference in string_references(value):
        yield {**reference, "field": field, "value": value}


def unique_references(value: Any) -> list[dict[str, str]]:
    items: dict[tuple[str, str, str], dict[str, str]] = {}
    for reference in walk_value_references(value):
        key = (
            str(reference["kind"]),
            str(reference["target"]),
            str(reference.get("field", "")),
        )
        items[key] = reference
    return [items[key] for key in sorted(items)]
