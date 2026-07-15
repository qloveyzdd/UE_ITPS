from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .common import iter_files, normalized, sha256_file


def module_entrypoints(module_dir: Path) -> list[str]:
    results: list[str] = []
    pattern = re.compile(r"\bIMPLEMENT_(?:PRIMARY_GAME_)?MODULE\s*\(")
    if not module_dir.is_dir():
        return results
    for path in iter_files(module_dir, ".cpp"):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        if pattern.search(text):
            results.append(normalized(path))
    return sorted(results, key=str.casefold)


def inspect_modules(
    project_root: Path,
    declarations: list[Any],
    additional_roots: list[Path],
) -> dict[str, Any]:
    modules: list[dict[str, Any]] = []
    source_root = project_root / "Source"
    search_roots = [source_root, project_root / "Platforms", *additional_roots]
    problems: list[dict[str, str]] = []

    for declaration_index, raw in enumerate(declarations):
        if not isinstance(raw, dict) or not isinstance(raw.get("Name"), str):
            continue
        name = raw["Name"]
        conventional_dir = source_root / name
        conventional_rules = conventional_dir / f"{name}.Build.cs"
        rule_candidates: list[Path] = []
        for search_root in search_roots:
            rule_candidates.extend(
                path
                for path in iter_files(search_root, ".Build.cs")
                if path.name.casefold() == f"{name}.Build.cs".casefold()
            )
        unique_rules = sorted(
            {path.resolve() for path in rule_candidates},
            key=lambda path: normalized(path).casefold(),
        )
        module_dirs = sorted(
            {path.parent for path in unique_rules},
            key=lambda path: normalized(path).casefold(),
        )
        source_files = [
            path
            for module_dir in module_dirs
            for path in [*iter_files(module_dir, ".h"), *iter_files(module_dir, ".cpp")]
        ]
        entrypoints = sorted(
            {
                entrypoint
                for module_dir in module_dirs
                for entrypoint in module_entrypoints(module_dir)
            },
            key=str.casefold,
        )
        status = (
            "complete"
            if len(unique_rules) == 1
            else ("missing" if not unique_rules else "ambiguous")
        )
        if status != "complete":
            problems.append(
                {
                    "severity": "error",
                    "code": "project-module-build-rules-not-unique",
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
                "raw_declaration": raw,
                "conventional_location": {
                    "directory": normalized(conventional_dir),
                    "build_rules": normalized(conventional_rules),
                },
                "actual": {
                    "build_rule_candidates": [
                        normalized(path) for path in unique_rules
                    ],
                    "build_rule_evidence": [
                        {"path": normalized(path), "sha256": sha256_file(path)}
                        for path in unique_rules
                    ],
                    "source_file_count": len(
                        {path.resolve() for path in source_files}
                    ),
                    "module_entrypoint_candidates": entrypoints,
                },
                "status": status,
            }
        )
    return {
        "schema_version": "ue-itps.project-modules.v1",
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
