from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import result_document
from .plugin_descriptor import plugin_descriptor_facts
from .source_parser import find_registration_macros


def inspect_plugin_modules(path: Path) -> dict[str, Any]:
    descriptor, problems = plugin_descriptor_facts(path)
    declarations = descriptor["modules"]
    declaration_indices: dict[str, list[int]] = {}
    for index, declaration in enumerate(declarations):
        declaration_indices.setdefault(str(declaration["name"]).casefold(), []).append(index)

    items: list[dict[str, Any]] = []
    for declaration in declarations:
        name = str(declaration["name"])
        key = name.casefold()
        indices = declaration_indices[key]
        if len(indices) > 1:
            continue
        build_rules = declaration["build_rules"]
        build_status = str(build_rules["status"])
        candidate_items = [
            {"path": str(candidate["path"])}
            for candidate in build_rules["candidates"]
        ]
        entry_candidates: list[dict[str, Any]] = []
        if build_status == "resolved":
            entry_candidates = [
                item
                for item in find_registration_macros(
                    Path(candidate_items[0]["path"]).parent
                )
                if str(item.get("module_name", "")).casefold() == key
            ]
        entry_status = (
            "resolved"
            if len(entry_candidates) == 1
            else ("missing" if not entry_candidates else "ambiguous")
        )
        if build_status == "resolved" and entry_status != "resolved":
            problems.append(
                {
                    "severity": "warning",
                    "code": f"plugin-module-entrypoint-{entry_status}",
                    "module_name": name,
                    "descriptor_pointer": declaration["descriptor_pointer"],
                    "candidates": entry_candidates,
                    "message": f"Plugin module {name} has {len(entry_candidates)} matching IMPLEMENT_*_MODULE candidates",
                }
            )
        items.append(
            {
                "name": name,
                "type": declaration["type"],
                "loading_phase": declaration["loading_phase"],
                "descriptor_pointer": declaration["descriptor_pointer"],
                "build_rules": {"status": build_status, "candidates": candidate_items},
                "entrypoints": {"status": entry_status, "candidates": entry_candidates},
            }
        )

    unlisted = descriptor["unlisted_build_rules"]

    return result_document(
        "ue-itps.plugin-modules.v1",
        {
            "plugin_descriptor": descriptor["descriptor_path"],
            "declared_module_count": len(declarations),
            "items": items,
            "unlisted_build_rules": unlisted,
        },
        problems,
        responsibility="Locate Build.cs and IMPLEMENT_*_MODULE entrypoint evidence for one selected plugin.",
        boundaries=[
            "This is a navigation and reconciliation result; Build.cs and C++ bodies are not expanded.",
            "Only files under the selected plugin Source and Platforms directories are searched.",
            "A located declaration is static evidence, not proof that UBT builds or loads the module.",
            "Plugin dependency descriptors are not resolved or traversed.",
        ],
    )
