from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .common import iter_files, normalized, result_document
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


def _is_target_type_setting(operation: dict[str, Any]) -> bool:
    path = [str(item) for item in operation.get("target_path", [])]
    return path in (["Type"], ["this", "Type"], ["base", "Type"])


def _target_type_value(operation: dict[str, Any]) -> str | None:
    path = [str(item) for item in operation.get("value_path", [])]
    if len(path) >= 2 and path[-2] == "TargetType":
        return path[-1]
    return None


def _extra_module_action(operation: dict[str, Any]) -> str | None:
    path = [str(item) for item in operation.get("callee_path", [])]
    if len(path) < 2 or path[-2] != "ExtraModuleNames":
        return None
    if path[:-2] not in ([], ["this"], ["base"]):
        return None
    return path[-1] if path[-1] in {"Add", "AddRange"} else None


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
            if operation["kind"] == "assignment" and _is_target_type_setting(operation):
                saw_target_type_assignment = True
                target_type = _target_type_value(operation)
                if target_type:
                    target_types.append(target_type)
                else:
                    problems.append(
                        {
                            "severity": "warning",
                            "code": "target-type-unresolved",
                            "path": normalized(path),
                            "line": int(operation["location"]["line"]),
                            "expression": str(operation.get("value_expression", "")),
                            "message": (
                                "Target Type is assigned from an expression that "
                                "cannot be resolved statically"
                            ),
                        }
                    )
                continue

            if operation["kind"] != "invocation":
                continue
            action = _extra_module_action(operation)
            if action is None:
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
    base_types = list(rules_class.get("base_type_facts", []))
    if not base_types:
        return None
    return str(base_types[0].get("name") or "") or None


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
        list(base_values["extra_module_names"]) if base_values is not None else []
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
