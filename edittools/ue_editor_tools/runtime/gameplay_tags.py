from __future__ import annotations

import json
from typing import Any

import unreal


TOOLSET = "GameplayTagsToolset.GameplayTagsToolset"


def _execute(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not unreal.ToolsetRegistry.is_toolset_registered(TOOLSET):
        raise RuntimeError(f"Required UE toolset is not registered: {TOOLSET}")
    result = unreal.ToolsetRegistry.execute_tool(
        TOOLSET,
        tool_name,
        json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
    )
    if not result.is_complete:
        raise RuntimeError(
            f"Tool did not complete synchronously: {TOOLSET}.{tool_name}"
        )
    if result.error:
        raise RuntimeError(str(result.error))
    value = json.loads(result.value)
    if not isinstance(value, dict):
        raise RuntimeError(f"Tool returned a non-object result: {TOOLSET}.{tool_name}")
    return value


def list_gameplay_tags(
    parent_tag: str = "", include_info: bool = False
) -> dict[str, Any]:
    tags = [
        str(value)
        for value in _execute("ListTags", {"parentTag": parent_tag})["returnValue"]
    ]
    tags.sort(key=str.casefold)
    infos: list[dict[str, Any]] = []
    if include_info:
        for tag in tags:
            info = _execute("GetTagInfo", {"tagName": tag})["returnValue"]
            infos.append(
                {
                    "tag": tag,
                    "comment": str(info.get("comment", "")),
                    "source": str(info.get("source", "")),
                    "children": sorted(
                        (str(item) for item in info.get("children", [])),
                        key=str.casefold,
                    ),
                }
            )
    return {"parent_tag": parent_tag, "tags": tags, "tag_infos": infos}


def find_tag_referencers(tag: str) -> dict[str, Any]:
    referencers = [
        str(value)
        for value in _execute("FindReferencersByTag", {"tagName": tag})["returnValue"]
    ]
    return {"tag": tag, "referencers": sorted(set(referencers), key=str.casefold)}


def find_tag_referencers_batch(tags: list[str]) -> dict[str, Any]:
    return {
        "items": [
            find_tag_referencers(tag) for tag in sorted(set(tags), key=str.casefold)
        ]
    }
