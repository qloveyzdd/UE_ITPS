from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import iter_files, normalized, result_document
from .plugin_descriptor import plugin_descriptor_facts
from .source_parser import find_registration_macros


def inspect_plugin_modules(path: Path) -> dict[str, Any]:
    descriptor, problems = plugin_descriptor_facts(path)
    resolved = path.resolve()
    plugin_root = resolved.parent
    search_roots = [plugin_root / "Source", plugin_root / "Platforms"]
    build_rules = sorted(
        {
            candidate.resolve()
            for root in search_roots
            for candidate in iter_files(root, ".Build.cs")
        },
        key=lambda candidate: normalized(candidate).casefold(),
    )
    by_name: dict[str, list[Path]] = {}
    actual_names: dict[str, str] = {}
    for candidate in build_rules:
        name = candidate.name[: -len(".Build.cs")]
        key = name.casefold()
        by_name.setdefault(key, []).append(candidate)
        actual_names.setdefault(key, name)

    declarations = descriptor["modules"]
    declaration_indices: dict[str, list[int]] = {}
    for index, declaration in enumerate(declarations):
        declaration_indices.setdefault(str(declaration["name"]).casefold(), []).append(index)

    items: list[dict[str, Any]] = []
    for index, declaration in enumerate(declarations):
        name = str(declaration["name"])
        key = name.casefold()
        indices = declaration_indices[key]
        if len(indices) > 1:
            if index != indices[0]:
                problems.append(
                    {
                        "severity": "error",
                        "code": "plugin-module-declaration-duplicate",
                        "module_name": name,
                        "descriptor_pointer": declaration["descriptor_pointer"],
                        "first_descriptor_pointer": declarations[indices[0]]["descriptor_pointer"],
                        "message": f"Plugin module {name} is declared more than once",
                    }
                )
            continue
        candidates = by_name.get(key, [])
        build_status = "resolved" if len(candidates) == 1 else ("missing" if not candidates else "ambiguous")
        candidate_items = [{"path": normalized(candidate)} for candidate in candidates]
        if build_status != "resolved":
            problems.append(
                {
                    "severity": "error",
                    "code": f"plugin-module-build-rules-{build_status}",
                    "module_name": name,
                    "descriptor_pointer": declaration["descriptor_pointer"],
                    "candidates": candidate_items,
                    "message": f"Plugin module {name} has {len(candidates)} Build.cs candidates",
                }
            )
        entry_candidates: list[dict[str, Any]] = []
        if len(candidates) == 1:
            entry_candidates = [
                item
                for item in find_registration_macros(candidates[0].parent)
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

    declared_keys = set(declaration_indices)
    unlisted = [
        {"module_name": actual_names[key], "path": normalized(candidate)}
        for key in sorted(set(by_name) - declared_keys, key=lambda item: actual_names[item].casefold())
        for candidate in by_name[key]
    ]
    for item in unlisted:
        problems.append(
            {
                "severity": "error",
                "code": "plugin-module-build-rules-unlisted",
                **item,
                "message": f"Build.cs for {item['module_name']} is not declared by the selected .uplugin",
            }
        )

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
