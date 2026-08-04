from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .common import iter_files, normalized, result_document
from .dependency_graph import DependencyGraph
from .source_parser import parse_cpp_file, parse_rule_file


def discover_module_build_rules(
    search_roots: Iterable[Path],
) -> tuple[dict[str, list[Path]], dict[str, str]]:
    all_rules = sorted(
        {
            path
            for search_root in search_roots
            for path in iter_files(search_root, ".Build.cs")
        },
        key=lambda path: path.as_posix().casefold(),
    )
    rules_by_module: dict[str, list[Path]] = {}
    discovered_module_names: dict[str, str] = {}
    for path in all_rules:
        module_name = path.name[: -len(".Build.cs")]
        module_key = module_name.casefold()
        rules_by_module.setdefault(module_key, []).append(path)
        discovered_module_names.setdefault(module_key, module_name)
    return rules_by_module, discovered_module_names


def module_entrypoints(module_dir: Path) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    if not module_dir.is_dir():
        return results
    for path in iter_files(module_dir, ".cpp"):
        try:
            parsed = parse_cpp_file(path)
        except (OSError, ValueError):
            continue
        path_text = normalized(path)
        for macro in parsed["registration_macros"]:
            if not macro.get("module_class") or not macro.get("module_name"):
                continue
            results.append(
                {
                    "path": path_text,
                    "macro": str(macro["macro"]),
                    "module_class": str(macro["module_class"]),
                    "module_name": str(macro["module_name"]),
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
    dependency_graph = DependencyGraph()
    source_root = project_root / "Source"
    search_roots = [source_root, project_root / "Platforms", *additional_roots]
    problems: list[dict[str, Any]] = []

    rules_by_module, discovered_module_names = discover_module_build_rules(
        search_roots
    )

    valid_declarations: list[tuple[int, dict[str, Any], str, str]] = []
    declaration_indices_by_module: dict[str, list[int]] = {}
    for declaration_index, raw in enumerate(declarations):
        if not isinstance(raw, dict) or not isinstance(raw.get("Name"), str):
            continue
        name = raw["Name"]
        module_key = name.casefold()
        valid_declarations.append((declaration_index, raw, name, module_key))
        declaration_indices_by_module.setdefault(module_key, []).append(
            declaration_index
        )

    for declaration_index, _, name, module_key in valid_declarations:
        declaration_indices = declaration_indices_by_module[module_key]
        if declaration_index != declaration_indices[0]:
            problems.append(
                {
                    "severity": "error",
                    "code": "project-module-declaration-duplicate",
                    "module_name": name,
                    "descriptor_pointer": f"/Modules/{declaration_index}",
                    "first_descriptor_pointer": (f"/Modules/{declaration_indices[0]}"),
                    "message": (
                        f"Module {name} is declared more than once in .uproject"
                    ),
                }
            )

    for declaration_index, raw, name, module_key in valid_declarations:
        if len(declaration_indices_by_module[module_key]) != 1:
            continue
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
                    "conventional": candidate_path.casefold() == conventional_rule_key,
                }
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
                    "module_name": name,
                    "descriptor_pointer": f"/Modules/{declaration_index}",
                    "candidates": build_rule_candidates,
                    "message": (
                        f"Declared module {name} has {len(unique_rules)} "
                        "Build.cs candidates"
                    ),
                }
            )
            continue

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

    for module in modules:
        dependency_graph.add_node(
            str(module["name"]),
            kind="module",
            file=str(module["build_rules"]["candidates"][0]["path"]),
        )
        rules_path = Path(str(module["build_rules"]["candidates"][0]["path"]))
        try:
            parsed_rules = parse_rule_file(rules_path, "ModuleRules")
        except (OSError, ValueError) as exc:
            problems.append(
                {
                    "severity": "warning",
                    "code": "project-module-rules-parse-failure",
                    "module_name": module["name"],
                    "message": str(exc),
                }
            )
            module["declared_dependencies"] = []
            continue
        dependencies: list[dict[str, Any]] = []
        for rules_class in parsed_rules["rules_classes"]:
            for method in rules_class["methods"]:
                for operation in method["operations"]:
                    rule = operation.get("rule", {})
                    if not str(rule.get("kind", "")).endswith("dependency"):
                        continue
                    values = operation.get("evaluation", {}).get("literal_values", [])
                    for target in values:
                        if not isinstance(target, str) or not target:
                            continue
                        dependency = {
                            "name": target,
                            "kind": rule["kind"],
                            "applicability": operation.get("applicability", "direct"),
                            "evidence": {"line": int(operation["location"]["line"])},
                        }
                        if dependency not in dependencies:
                            dependencies.append(dependency)
                        dependency_graph.add_node(target, kind="module", file="")
                        dependency_graph.add_edge(
                            str(module["name"]), target,
                            kind=str(rule["kind"]), file=normalized(rules_path),
                            line=int(operation["location"]["line"]),
                        )
        module["declared_dependencies"] = sorted(
            dependencies,
            key=lambda item: (item["name"].casefold(), item["kind"], item["evidence"]["line"]),
        )

    for module_key in sorted(
        set(rules_by_module) - set(declaration_indices_by_module),
        key=lambda key: discovered_module_names[key].casefold(),
    ):
        module_name = discovered_module_names[module_key]
        candidates = [
            {"path": normalized(path)} for path in rules_by_module[module_key]
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

    return result_document(
        "ue_inspect_modules",
        {
            "reconciled_module_count": len(modules),
            "items": modules,
            "dependency_graph": dependency_graph.document(),
        },
        problems,
        responsibility=(
            "Reconcile declared project Modules with Build.cs and entrypoint evidence."
        ),
        boundaries=[
            "Build.cs location is discovered by basename; Source/<Name>/<Name>.Build.cs is only conventional.",
            "AdditionalDependencies and statically declared Build.cs dependencies are reported separately.",
            "The result does not evaluate UBT rules, compile Modules, or prove runtime loading.",
        ],
    )


def inspect_targets(project_root: Path) -> dict[str, Any]:
    targets: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    source_root = (project_root / "Source").resolve()
    for path in iter_files(source_root, ".Target.cs"):
        name = path.name[: -len(".Target.cs")]
        parsed_rules = parse_rule_file(path, "TargetRules")
        targets.append(
            {
                "name": name,
                "path": normalized(path),
                "is_root_target": path.parent == source_root,
                "rules_classes": [
                    item["name"] for item in parsed_rules["rules_classes"]
                ],
                "syntax": {
                    "engine": parsed_rules["syntax_tree"]["engine"],
                    "parse_error_count": parsed_rules["syntax_tree"]["parse_error_count"],
                },
            }
        )
        problems.extend(parsed_rules.get("problems", []))
    targets.sort(key=lambda item: str(item["name"]).casefold())
    classification = (
        "native-project"
        if any(target["is_root_target"] for target in targets)
        else "undetermined-no-native-target"
    )
    root_targets = [target for target in targets if target["is_root_target"]]
    nested_targets = [target for target in targets if not target["is_root_target"]]
    if not targets:
        problems.append(
            {
                "severity": "error",
                "code": "project-target-not-found",
                "message": (
                    "No project Target.cs files were found under Source; add at "
                    "least one, preferably directly under Source."
                ),
            }
        )
    elif not root_targets:
        problems.append(
            {
                "severity": "warning",
                "code": "project-target-root-missing",
                "target_names": [target["name"] for target in nested_targets],
                "message": (
                    "Target.cs files exist only in Source subdirectories; add or "
                    "move at least one directly under Source for UE source-project "
                    "detection."
                ),
            }
        )
    elif nested_targets:
        problems.append(
            {
                "severity": "warning",
                "code": "project-target-nested",
                "target_names": [target["name"] for target in nested_targets],
                "message": (
                    "Target.cs files exist both directly under Source and in its "
                    "subdirectories; review and move nested targets directly under "
                    "Source when possible."
                ),
            }
        )
    return result_document(
        "ue_inspect_targets",
        {
            "items": targets,
            "classification": classification,
        },
        problems,
        responsibility=(
            "Discover project Target.cs files, validate their placement, and "
            "classify native Target evidence."
        ),
        boundaries=[
            "native-project means at least one Source/*.Target.cs file was discovered.",
            (
                "No root Target produces undetermined-no-native-target; "
                "it does not prove the project is Blueprint-only."
            ),
            (
                "A Target in a Source subdirectory is supported by UBT and is not "
                "invalid by itself; nested-only placement is a warning."
            ),
            "Root and nested Targets together produce a distinct placement warning.",
            "Target files are syntax-parsed and matching TargetRules classes are reported, but rules are not evaluated.",
            "Temporary or hybrid Target reasons require UBT-level analysis.",
        ],
    )
