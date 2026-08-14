from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Iterable

from .common import iter_files, normalized, result_document
from .dependency_graph import DependencyGraph
from .module_entry import registration_macros_for_source
from .source_parser import parse_rule_file


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


def module_entrypoints(
    module_dir: Path,
    project_root: Path,
    compilation_database: Path | None = None,
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    if not module_dir.is_dir():
        return results
    for path in iter_files(module_dir, ".cpp"):
        path_text = normalized(path)
        for macro in registration_macros_for_source(
            path, project_root, compilation_database
        ):
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
    compilation_database: Path | None = None,
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
            for entrypoint in module_entrypoints(
                module_dir, project_root, compilation_database
            )
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


_TARGET_TYPE_EXPRESSION = re.compile(
    r"(?:[A-Za-z_]\w*\.)*TargetType\.(?P<name>[A-Za-z_]\w*)"
)
_TARGET_TYPE_SETTING = re.compile(r"(?:(?:this|base)\.)?Type")
_EXTRA_MODULE_MUTATION = re.compile(
    r"(?:(?:this|base)\.)?ExtraModuleNames\.(?P<action>Add|AddRange)"
)


def _reachable_target_methods(rules_class: dict[str, Any]) -> list[dict[str, Any]]:
    roots = {
        str(method["name"])
        for method in rules_class["methods"]
        if method["is_constructor"]
    }
    graph: dict[str, set[str]] = {}
    for call in rules_class["same_file_calls"]:
        graph.setdefault(str(call["caller"]), set()).add(str(call["callee"]))
    reachable = set(roots)
    pending = list(roots)
    while pending:
        caller = pending.pop()
        for callee in graph.get(caller, set()):
            if callee not in reachable:
                reachable.add(callee)
                pending.append(callee)
    return [
        method for method in rules_class["methods"] if str(method["name"]) in reachable
    ]


def _direct_target_declarations(
    path: Path,
    rules_class: dict[str, Any],
) -> dict[str, Any]:
    target_types: list[str] = []
    extra_module_names: list[str] = []
    problems: list[dict[str, Any]] = []
    saw_target_type_assignment = False

    for method in _reachable_target_methods(rules_class):
        for operation in method["operations"]:
            if (
                operation["kind"] == "assignment"
                and _TARGET_TYPE_SETTING.fullmatch(
                    str(operation.get("target", ""))
                )
            ):
                saw_target_type_assignment = True
                match = _TARGET_TYPE_EXPRESSION.fullmatch(
                    str(operation.get("value_expression", "")).strip()
                )
                if match:
                    target_types.append(match.group("name"))
                else:
                    problems.append(
                        {
                            "severity": "warning",
                            "code": "target-type-unresolved",
                            "path": normalized(path),
                            "line": int(operation["location"]["line"]),
                            "expression": str(
                                operation.get("value_expression", "")
                            ),
                            "message": (
                                "Target Type is assigned from an expression that "
                                "cannot be resolved statically"
                            ),
                        }
                    )
                continue

            if operation["kind"] != "invocation":
                continue
            mutation = _EXTRA_MODULE_MUTATION.fullmatch(
                str(operation.get("callee", ""))
            )
            if mutation is None:
                continue
            evaluation = operation.get("evaluation", {})
            if evaluation.get("status") == "literal":
                extra_module_names.extend(
                    str(value) for value in evaluation.get("literal_values", [])
                )
            else:
                problems.append(
                    {
                        "severity": "warning",
                        "code": "target-extra-modules-unresolved",
                        "path": normalized(path),
                        "line": int(operation["location"]["line"]),
                        "expression": str(operation.get("expression", "")),
                        "message": (
                            "ExtraModuleNames contains values that cannot be "
                            "resolved statically"
                        ),
                    }
                )

    unique_target_types = list(dict.fromkeys(target_types))
    target_type = unique_target_types[0] if len(unique_target_types) == 1 else None
    if len(unique_target_types) > 1:
        problems.append(
            {
                "severity": "warning",
                "code": "target-type-ambiguous",
                "path": normalized(path),
                "candidates": unique_target_types,
                "message": "Multiple TargetType assignments were found",
            }
        )

    return {
        "target_type": target_type,
        "extra_module_names": list(dict.fromkeys(extra_module_names)),
        "has_type_assignment": saw_target_type_assignment,
        "problems": problems,
    }


def _target_base_name(rules_class: dict[str, Any]) -> str | None:
    base_types = list(rules_class.get("base_types", []))
    if not base_types:
        return None
    expression = str(base_types[0]).split("<", 1)[0]
    return expression.rsplit(".", 1)[-1]


def _resolve_target_values(
    record_id: int,
    records: list[dict[str, Any]],
    cache: dict[int, dict[str, Any]],
    stack: list[int],
    problems: list[dict[str, Any]],
    reported_cycles: set[tuple[str, ...]],
) -> dict[str, Any]:
    if record_id in cache:
        return cache[record_id]
    record = records[record_id]
    direct = record["direct"]
    if record_id in stack:
        cycle_start = stack.index(record_id)
        cycle_ids = [*stack[cycle_start:], record_id]
        cycle = tuple(str(records[item]["name"]) for item in cycle_ids)
        if cycle not in reported_cycles:
            reported_cycles.add(cycle)
            problems.append(
                {
                    "severity": "error",
                    "code": "target-inheritance-cycle",
                    "inheritance_chain": list(cycle),
                    "message": "Target inheritance contains a cycle",
                }
            )
        return {
            "target_type": None,
            "extra_module_names": [],
            "inheritance_chain": [str(record["name"])],
            "cycle": True,
        }

    base_id = record.get("base_id")
    base_values = None
    inherited_cycle = False
    if base_id is not None:
        base_values = _resolve_target_values(
            int(base_id),
            records,
            cache,
            [*stack, record_id],
            problems,
            reported_cycles,
        )
        if base_values.get("cycle"):
            inherited_cycle = True
            base_values = None

    inferred_fields: list[str] = []
    target_type = direct["target_type"]
    if (
        target_type is None
        and not direct["has_type_assignment"]
        and base_values is not None
        and base_values["target_type"] is not None
    ):
        target_type = base_values["target_type"]
        inferred_fields.append("target_type")

    inherited_modules = (
        list(base_values["extra_module_names"])
        if base_values is not None
        else []
    )
    if inherited_modules:
        inferred_fields.append("extra_module_names")
    extra_module_names = list(
        dict.fromkeys([*inherited_modules, *direct["extra_module_names"]])
    )
    inheritance_chain = [str(record["name"])]
    if base_values is not None:
        inheritance_chain.extend(base_values["inheritance_chain"])

    result = {
        "target_type": target_type,
        "extra_module_names": extra_module_names,
        "inheritance_chain": inheritance_chain,
        "cycle": inherited_cycle,
    }
    cache[record_id] = result
    if inferred_fields and not inherited_cycle:
        problems.append(
            {
                "severity": "info",
                "code": "target-values-inherited",
                "inheritance_chain": inheritance_chain,
                "inferred_fields": inferred_fields,
                "message": "Target values were inferred through inheritance",
            }
        )
    return result


def inspect_targets(project_root: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    source_root = (project_root / "Source").resolve()
    target_paths = list(iter_files(source_root, ".Target.cs"))
    for path in target_paths:
        parsed_rules = parse_rule_file(path, "TargetRules")
        problems.extend(parsed_rules.get("problems", []))
        for rules_class in parsed_rules["rules_classes"]:
            direct = _direct_target_declarations(path, rules_class)
            problems.extend(direct["problems"])
            records.append(
                {
                    "name": str(rules_class["name"]),
                    "path": normalized(path),
                    "rules_class": rules_class,
                    "direct": direct,
                }
            )

    class_index: dict[str, list[int]] = {}
    for record_id, record in enumerate(records):
        class_index.setdefault(str(record["name"]), []).append(record_id)

    for record in records:
        base_name = _target_base_name(record["rules_class"])
        if base_name is None or base_name == "TargetRules":
            record["base_id"] = None
            continue
        candidates = class_index.get(base_name, [])
        if len(candidates) == 1:
            record["base_id"] = candidates[0]
        elif not candidates:
            record["base_id"] = None
            problems.append(
                {
                    "severity": "warning",
                    "code": "target-base-unresolved",
                    "path": record["path"],
                    "base_type": base_name,
                    "message": "Target base class was not found in project Target files",
                }
            )
        else:
            record["base_id"] = None
            problems.append(
                {
                    "severity": "warning",
                    "code": "target-base-ambiguous",
                    "path": record["path"],
                    "base_type": base_name,
                    "message": "Multiple project Target classes match the base type",
                }
            )

    targets: list[dict[str, Any]] = []
    cache: dict[int, dict[str, Any]] = {}
    reported_cycles: set[tuple[str, ...]] = set()
    for record_id, record in enumerate(records):
        values = _resolve_target_values(
            record_id,
            records,
            cache,
            [],
            problems,
            reported_cycles,
        )
        if (
            values["target_type"] is None
            and not record["direct"]["has_type_assignment"]
            and record.get("base_id") is None
            and _target_base_name(record["rules_class"]) in {None, "TargetRules"}
        ):
            problems.append(
                {
                    "severity": "warning",
                    "code": "target-type-not-found",
                    "path": record["path"],
                    "message": "No statically resolved TargetType assignment was found",
                }
            )
        targets.append(
            {
                "name": record["name"],
                "path": record["path"],
                "target_type": values["target_type"],
                "extra_module_names": values["extra_module_names"],
            }
        )

    targets.sort(key=lambda item: str(item["name"]).casefold())
    if not target_paths:
        problems.append(
            {
                "severity": "error",
                "code": "project-target-not-found",
                "message": "No project Target.cs files were found under Source.",
            }
        )
    return result_document(
        "ue_inspect_targets",
        {
            "items": targets,
        },
        problems,
        responsibility=(
            "Discover project Target.cs classes and report directly declared or "
            "inherited Target types and extra modules."
        ),
        boundaries=[
            "Target files are discovered recursively under Source without evaluating their placement.",
            "Only TargetRules constructors and statically reachable same-file helpers are inspected.",
            "Project-local Target inheritance is followed by class name; external base classes are not resolved.",
            "Inherited values are static inferences and are reported as validation info, not effective UBT results.",
            "ExtraModuleNames reports direct and inherited Target module declarations, not Build.cs dependencies or their transitive closure.",
            "Dynamic Target types and module expressions are reported as unresolved instead of inferred.",
        ],
    )
