from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .common import iter_files, normalized, sha256_file


def module_entrypoints(module_dir: Path) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    pattern = re.compile(
        r"\b(?P<macro>IMPLEMENT_(?:(?:PRIMARY_)?GAME_)?MODULE)\s*"
        r"\(\s*(?P<module_class>[A-Za-z_]\w*)\s*,\s*"
        r"(?P<module_name>[A-Za-z_]\w*)\b"
    )
    if not module_dir.is_dir():
        return results
    for path in iter_files(module_dir, ".cpp"):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        path_text = normalized(path)
        for match in pattern.finditer(text):
            results.append(
                {
                    "path": path_text,
                    "macro": match.group("macro"),
                    "module_class": match.group("module_class"),
                    "module_name": match.group("module_name"),
                }
            )
    return sorted(
        results,
        key=lambda item: (
            item["path"].casefold(),
            item["macro"],
            item["module_class"],
            item["module_name"],
        ),
    )


def inspect_modules(
    project_root: Path,
    declarations: list[Any],
    additional_roots: list[Path],
) -> dict[str, Any]:
    modules: list[dict[str, Any]] = []
    source_root = project_root / "Source"
    search_roots = [source_root, project_root / "Platforms", *additional_roots]
    problems: list[dict[str, Any]] = []

    all_rules = sorted(
        {
            path.resolve()
            for search_root in search_roots
            for path in iter_files(search_root, ".Build.cs")
        },
        key=lambda path: normalized(path).casefold(),
    )
    rules_by_module: dict[str, list[Path]] = {}
    discovered_module_names: dict[str, str] = {}
    for path in all_rules:
        module_name = path.name[: -len(".Build.cs")]
        module_key = module_name.casefold()
        rules_by_module.setdefault(module_key, []).append(path)
        discovered_module_names.setdefault(module_key, module_name)

    declared_module_indices: dict[str, int] = {}

    for declaration_index, raw in enumerate(declarations):
        if not isinstance(raw, dict) or not isinstance(raw.get("Name"), str):
            continue
        name = raw["Name"]
        module_key = name.casefold()
        first_declaration_index = declared_module_indices.get(module_key)
        if first_declaration_index is None:
            declared_module_indices[module_key] = declaration_index
        else:
            problems.append(
                {
                    "severity": "error",
                    "code": "project-module-declaration-duplicate",
                    "module_name": name,
                    "descriptor_pointer": f"/Modules/{declaration_index}",
                    "first_descriptor_pointer": (
                        f"/Modules/{first_declaration_index}"
                    ),
                    "message": (
                        f"Module {name} is declared more than once in .uproject"
                    ),
                }
            )
        conventional_dir = source_root / name
        conventional_rules = conventional_dir / f"{name}.Build.cs"
        unique_rules = rules_by_module.get(module_key, [])
        conventional_rule_key = normalized(conventional_rules).casefold()
        build_rule_candidates = []
        for path in unique_rules:
            candidate_path = normalized(path)
            build_rule_candidates.append(
                {
                    "path": candidate_path,
                    "sha256": sha256_file(path),
                    "conventional": candidate_path.casefold()
                    == conventional_rule_key,
                }
            )
        module_dirs = sorted(
            {path.parent for path in unique_rules},
            key=lambda path: normalized(path).casefold(),
        )
        entrypoint_candidates = [
            entrypoint
            for module_dir in module_dirs
            for entrypoint in module_entrypoints(module_dir)
        ]
        entrypoints = sorted(
            {
                (
                    entrypoint["path"],
                    entrypoint["macro"],
                    entrypoint["module_class"],
                    entrypoint["module_name"],
                ): entrypoint
                for entrypoint in entrypoint_candidates
            }.values(),
            key=lambda item: (
                item["path"].casefold(),
                item["macro"],
                item["module_class"],
                item["module_name"],
            ),
        )
        status = (
            "resolved"
            if len(unique_rules) == 1
            else ("missing" if not unique_rules else "ambiguous")
        )
        if status != "resolved":
            problems.append(
                {
                    "severity": "error",
                    "code": (
                        "project-module-build-rules-missing"
                        if status == "missing"
                        else "project-module-build-rules-ambiguous"
                    ),
                    "descriptor_pointer": f"/Modules/{declaration_index}",
                    "message": (
                        f"Declared module {name} has {len(unique_rules)} "
                        "Build.cs candidates"
                    ),
                }
            )
        modules.append(
            {
                "name": name,
                "type": raw.get("Type"),
                "loading_phase": raw.get("LoadingPhase", "Default"),
                "additional_dependencies": raw.get("AdditionalDependencies", []),
                "descriptor_pointer": f"/Modules/{declaration_index}",
                "build_rules": {
                    "status": status,
                    "candidates": build_rule_candidates,
                },
                "actual": {
                    "module_entrypoint_candidates": entrypoints,
                },
            }
        )

    for module_key in sorted(
        set(rules_by_module) - set(declared_module_indices),
        key=lambda key: discovered_module_names[key].casefold(),
    ):
        module_name = discovered_module_names[module_key]
        candidates = [
            {"path": normalized(path), "sha256": sha256_file(path)}
            for path in rules_by_module[module_key]
        ]
        problems.append(
            {
                "severity": "error",
                "code": "project-module-build-rules-undeclared",
                "module_name": module_name,
                "candidates": candidates,
                "message": (
                    f"Module {module_name} has {len(candidates)} Build.cs "
                    "candidates but is not declared in .uproject"
                ),
            }
        )

    return {
        "schema_version": "ue-itps.project-modules.v2",
        "count": len(modules),
        "items": modules,
        "validation": {
            "status": "error" if problems else "ok",
            "problems": problems,
        },
        "limits": [
            "Build.cs location is discovered by basename; Source/<Name>/<Name>.Build.cs is only conventional.",
            "AdditionalDependencies does not replace Build.cs dependency analysis.",
        ],
    }


def inspect_targets(project_root: Path) -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    for path in iter_files(project_root / "Source", ".Target.cs"):
        name = path.name[: -len(".Target.cs")]
        targets.append(
            {"name": name, "path": normalized(path), "sha256": sha256_file(path)}
        )
    targets.sort(key=lambda item: str(item["name"]).casefold())

    source_root = project_root / "Source"
    root_targets = (
        sorted(
            [
                path.resolve()
                for path in source_root.glob("*.Target.cs")
                if path.is_file()
            ],
            key=lambda path: normalized(path).casefold(),
        )
        if source_root.is_dir()
        else []
    )
    return {
        "schema_version": "ue-itps.project-targets.v1",
        "count": len(targets),
        "items": targets,
        "native_project_evidence": {
            "rule_id": "ue5.6-project-has-code-root-target",
            "has_native_targets": bool(root_targets),
            "root_target_count": len(root_targets),
            "root_targets": [normalized(path) for path in root_targets],
            "classification": (
                "native-project" if root_targets else "undetermined-no-native-target"
            ),
            "limits": (
                "Temporary/hybrid target reasons require UBT-level analysis and "
                "are not inferred here."
            ),
        },
    }
