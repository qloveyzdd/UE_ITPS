from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import result_document
from .source_parser import parse_rule_file


_MODULE_DEPENDENCY_SETTINGS = {
    "PublicDependencyModuleNames": "public_dependency_modules",
    "PrivateDependencyModuleNames": "private_dependency_modules",
    "DynamicallyLoadedModuleNames": "dynamically_loaded_modules",
}


def _is_empty_literal_add_range(
    operation: dict[str, Any],
) -> bool:
    rule = operation.get("rule", {})
    arguments = operation.get("arguments", [])
    if rule.get("action") != "AddRange" or len(arguments) != 1:
        return False
    evaluation = arguments[0].get("evaluation", {})
    return evaluation.get("status") == "literal" and not evaluation.get(
        "literal_values"
    )


def _rules_class_problems(
    facts: dict[str, Any], base_type: str
) -> list[dict[str, Any]]:
    if facts["rules_classes"]:
        return list(facts.get("problems", []))
    return [
        *facts.get("problems", []),
        {
            "severity": "error",
            "code": "rules-class-not-found",
            "path": facts["path"],
            "required_base_type": base_type,
            "message": f"No class derived from {base_type} was found in the selected file",
        },
    ]


def _target_rules_problems(facts: dict[str, Any]) -> list[dict[str, Any]]:
    if not facts["rules_classes"]:
        return _rules_class_problems(facts, "TargetRules")
    return [
        *facts.get("problems", []),
        *[
            {
                "severity": "warning",
                "code": "target-rules-base-unresolved",
                "path": facts["path"],
                "class_name": rules_class["name"],
                "base_types": list(rules_class["base_types"]),
                "message": (
                    "The filename and TargetInfo constructor identify a local Target "
                    "candidate, but its TargetRules inheritance cannot be confirmed "
                    "from the selected file"
                ),
            }
            for rules_class in facts["rules_classes"]
            if rules_class.get("base_resolution") == "unresolved"
        ],
    ]


def _reachable_method_names(rules_class: dict[str, Any]) -> set[str]:
    roots = {
        method["name"] for method in rules_class["methods"] if method["is_constructor"]
    }
    graph: dict[str, set[str]] = {}
    for call in rules_class["same_file_calls"]:
        graph.setdefault(call["caller"], set()).add(call["callee"])
    reachable = set(roots)
    pending = list(roots)
    while pending:
        caller = pending.pop()
        for callee in graph.get(caller, set()):
            if callee not in reachable:
                reachable.add(callee)
                pending.append(callee)
    return reachable


def _project_target_rules_class(rules_class: dict[str, Any]) -> dict[str, Any]:
    methods = sorted(
        rules_class["methods"],
        key=lambda method: int(method["location"]["line"]),
    )

    return {
        "kind": rules_class["kind"],
        "name": rules_class["name"],
        "base_types": list(rules_class["base_types"]),
        "inheritance": {
            "kind": rules_class.get("base_resolution", "confirmed"),
        },
        "member_details": {
            "variables": [
                {
                    "name": str(field["name"]),
                    "type_expression": str(field["type_expression"]),
                    "evidence": {
                        key: int(field["location"][key])
                        for key in ("line", "end_line")
                        if key in field["location"]
                    },
                }
                for field in rules_class["fields"]
            ],
            "functions": [
                {
                    "name": str(method["name"]),
                    "signature": " ".join(str(method["signature"]).split()),
                    "is_constructor": bool(method["is_constructor"]),
                    "has_body": bool(method["has_body"]),
                    "evidence": {
                        key: int(method["location"][key])
                        for key in ("line", "end_line")
                        if key in method["location"]
                    },
                }
                for method in methods
            ],
        },
        "evidence": {
            key: int(rules_class["location"][key])
            for key in ("line", "end_line")
            if key in rules_class["location"]
        },
    }


def inspect_target_rules(path: Path) -> dict[str, Any]:
    facts = parse_rule_file(path, "TargetRules")
    content = {
        "path": facts["path"],
        "rules_classes": [
            _project_target_rules_class(rules_class)
            for rules_class in facts["rules_classes"]
        ],
    }
    return result_document(
        "ue_inspect_target_rules",
        content,
        _target_rules_problems(facts),
        responsibility=(
            "Index TargetRules classes and their member variables and functions from one Target.cs file."
        ),
        boundaries=[
            "Member variables and functions are a Tree-sitter syntax index, not semantic summaries or effective UBT build results.",
            "Function bodies, mutations, calls, conditions, and referenced values are not included.",
            "Use the focused C# function inspector to inspect one explicitly selected function name.",
            "Filename-matching Target candidates with unresolved bases are local evidence, not inheritance proof.",
            "Output order is deterministic source order.",
        ],
    )


def _project_module_rules_class(
    rules_class: dict[str, Any],
    path: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    reachable = _reachable_method_names(rules_class)
    methods = [
        method for method in rules_class["methods"] if method["name"] in reachable
    ]
    dependencies: dict[str, list[str]] = {
        "public_dependency_modules": [],
        "private_dependency_modules": [],
        "dynamically_loaded_modules": [],
    }
    seen = {kind: set() for kind in dependencies}
    problems: list[dict[str, Any]] = []

    for method in methods:
        for operation in method["operations"]:
            rule = operation.get("rule", {})
            setting = str(rule.get("member", ""))
            dependency_kind = _MODULE_DEPENDENCY_SETTINGS.get(setting)
            if (
                dependency_kind is None
                or operation.get("kind") != "invocation"
                or rule.get("action") not in {"Add", "AddRange"}
            ):
                continue
            evaluation = operation.get("evaluation", {})
            for value in evaluation.get("literal_values", []):
                module_name = str(value)
                if module_name not in seen[dependency_kind]:
                    seen[dependency_kind].add(module_name)
                    dependencies[dependency_kind].append(module_name)
            if evaluation.get(
                "status"
            ) != "literal" and not _is_empty_literal_add_range(operation):
                problems.append(
                    {
                        "severity": "warning",
                        "code": "module-dependency-expression-unresolved",
                        "path": path,
                        "class_name": rules_class["name"],
                        "setting": setting,
                        "line": int(operation["location"]["line"]),
                        "message": (
                            "The dependency expression is not fully composed of "
                            "string literals; the reported module list may be incomplete"
                        ),
                    }
                )

    return (
        {
            "name": rules_class["name"],
            "dependencies": dependencies,
        },
        problems,
    )


def inspect_module_rules(path: Path) -> dict[str, Any]:
    facts = parse_rule_file(path, "ModuleRules")
    projected = [
        _project_module_rules_class(rules_class, facts["path"])
        for rules_class in facts["rules_classes"]
    ]
    content = {
        "rules_classes": [rules_class for rules_class, _ in projected],
    }
    problems = [
        *_rules_class_problems(facts, "ModuleRules"),
        *[problem for _, class_problems in projected for problem in class_problems],
    ]
    return result_document(
        "ue_inspect_module_rules",
        content,
        problems,
        responsibility=(
            "Report public, private, and dynamically loaded module dependency "
            "names from one Build.cs file."
        ),
        boundaries=[
            "Only PublicDependencyModuleNames, PrivateDependencyModuleNames, and DynamicallyLoadedModuleNames are reported.",
            "Only string literals passed to Add or AddRange are returned.",
            "An empty literal AddRange is treated as a resolved empty dependency list even when its initializer contains comments.",
            "Constructors and statically reachable same-file helpers contribute dependency names.",
            "Dependencies found in recognized conditional branches are included without condition metadata.",
            "Duplicate dependency names are removed within each dependency kind while preserving source order.",
            "Warnings identify expressions that are not fully composed of string literals and may make a dependency list incomplete.",
            "Static declarations are not effective UBT build results or transitive dependency closure.",
        ],
    )
