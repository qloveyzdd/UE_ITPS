from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .common import result_document
from .source_parser import parse_rule_file


_REFERENCE_KINDS = {
    "PublicDependencyModuleNames": "module",
    "PrivateDependencyModuleNames": "module",
    "DynamicallyLoadedModuleNames": "module",
    "PublicIncludePathModuleNames": "module",
    "PrivateIncludePathModuleNames": "module",
    "PublicIncludePaths": "path",
    "PrivateIncludePaths": "path",
    "PublicSystemIncludePaths": "path",
    "PrivatePCHHeaderFile": "path",
    "SharedPCHHeaderFile": "path",
    "PublicDefinitions": "definition",
    "PrivateDefinitions": "definition",
}

_COLLECTION_MUTATION = re.compile(
    r"(?:^|[.>])(?P<member>[A-Za-z_]\w*)\."
    r"(?P<action>AddRange|Add|Remove|RemoveAll)$"
)
_SYMBOL_EXPRESSION = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
_BARE_CALL = re.compile(r"(?:(?:this|base)\.)?[A-Za-z_]\w*")
_NO_PRIMITIVE = object()
_ASSIGNMENT_ACTIONS = {
    "=": "set",
    "+=": "add",
    "-=": "remove",
    "*=": "multiply",
    "/=": "divide",
    "??=": "set_if_null",
    "++": "increment",
    "--": "decrement",
}
_COLLECTION_ACTIONS = {
    "Add": "add",
    "AddRange": "add",
    "Remove": "remove",
    "RemoveAll": "remove",
}


def _rules_class_problems(
    facts: dict[str, Any], base_type: str
) -> list[dict[str, Any]]:
    if facts["rules_classes"]:
        return []
    return [
        {
            "severity": "error",
            "code": "rules-class-not-found",
            "path": facts["path"],
            "required_base_type": base_type,
            "message": f"No class derived from {base_type} was found in the selected file",
        }
    ]


def _inspect_rules(path: Path, base_type: str, schema: str) -> dict[str, Any]:
    facts = parse_rule_file(path, base_type)
    problems = _rules_class_problems(facts, base_type)
    kind = "Target.cs" if base_type == "TargetRules" else "Build.cs"
    return result_document(
        schema,
        facts,
        problems,
        responsibility=f"Report deterministic static source facts from one {kind} file.",
        boundaries=[
            "Static declarations are not effective UBT build results.",
            "Conditions and expressions are preserved but are not executed against a Target profile.",
            "Only direct same-file method relationships are resolved.",
            "Unsupported expressions remain unresolved source facts instead of inferred values.",
        ],
    )


def inspect_target_rules(path: Path) -> dict[str, Any]:
    return _inspect_rules(path, "TargetRules", "ue-itps.target-rules-source.v1")


def _reachable_method_names(rules_class: dict[str, Any]) -> set[str]:
    roots = {
        method["name"]
        for method in rules_class["methods"]
        if method["is_constructor"]
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


def _is_empty_collection_argument(operation: dict[str, Any]) -> bool:
    if operation.get("kind") != "invocation":
        return False
    action = str(operation.get("rule", {}).get("action", ""))
    if not action:
        match = _COLLECTION_MUTATION.search(str(operation.get("callee", "")))
        action = match.group("action") if match else ""
    if action != "AddRange" or len(operation.get("arguments", [])) != 1:
        return False
    expression = re.sub(
        r"\s+", "", str(operation["arguments"][0].get("expression", ""))
    )
    return bool(re.fullmatch(r"new(?:[A-Za-z_]\w*)?\[\]\{\}", expression))


def _primitive_value(expression: str) -> Any:
    if expression == "true":
        return True
    if expression == "false":
        return False
    if expression == "null":
        return None
    if re.fullmatch(r"[+-]?\d+", expression):
        return int(expression)
    if re.fullmatch(r"[+-]?(?:\d+\.\d*|\d*\.\d+)(?:[fFdDmM])?", expression):
        return float(expression.rstrip("fFdDmM"))
    return _NO_PRIMITIVE


def _operand(operation: dict[str, Any], setting: str) -> dict[str, Any]:
    evaluation = operation.get("evaluation", {})
    literal_values = list(evaluation.get("literal_values", []))
    reference_kind = _REFERENCE_KINDS.get(setting)
    if evaluation.get("status") == "literal" and literal_values:
        result: dict[str, Any] = {"kind": "literal"}
        if reference_kind:
            result["reference_kind"] = reference_kind
        result["references"] = literal_values
        return result

    if operation["kind"] == "assignment":
        expression = str(operation.get("value_expression", ""))
        primitive = _primitive_value(expression)
        if primitive is not _NO_PRIMITIVE:
            return {"kind": "literal", "values": [primitive]}
        if _SYMBOL_EXPRESSION.fullmatch(expression):
            return {"kind": "symbol", "references": [expression]}
    else:
        arguments = operation.get("arguments", [])
        expression = ", ".join(str(item.get("expression", "")) for item in arguments)

    return {"kind": "expression", "expression": expression}


def _line(operation: dict[str, Any]) -> int:
    return int(operation["location"]["line"])


def _applicability(operation: dict[str, Any]) -> dict[str, Any]:
    applicability: dict[str, Any] = {
        "kind": str(operation.get("applicability", "direct"))
    }
    control_path = list(operation.get("control_path", []))
    if control_path:
        applicability["control_path"] = control_path
    related_symbols = list(operation.get("related_symbols", []))
    if related_symbols:
        applicability["related_symbols"] = related_symbols
    return {"applicability": applicability}


def _known_mutation(operation: dict[str, Any]) -> dict[str, Any] | None:
    rule = operation.get("rule")
    if not rule or _is_empty_collection_argument(operation):
        return None
    action = _COLLECTION_ACTIONS.get(str(rule["action"]), "set")
    if operation["kind"] == "assignment":
        action = _ASSIGNMENT_ACTIONS.get(str(operation.get("operator", "")), "set")
    return {
        "setting": rule["member"],
        "operation": action,
        "operand": _operand(operation, str(rule["member"])),
        **_applicability(operation),
        "line": _line(operation),
    }


def _unclassified_mutation(operation: dict[str, Any]) -> dict[str, Any] | None:
    if operation.get("rule") or _is_empty_collection_argument(operation):
        return None
    if operation["kind"] == "assignment":
        operator = str(operation.get("operator", ""))
        return {
            "target": str(operation.get("target", "")),
            "operation": _ASSIGNMENT_ACTIONS.get(
                operator, "set"
            ),
            "expression": str(
                operation.get("expression", "")
                if operator in {"++", "--"}
                else operation.get("value_expression", "")
            ),
            **_applicability(operation),
            "line": _line(operation),
        }
    match = _COLLECTION_MUTATION.search(str(operation.get("callee", "")))
    if not match:
        return None
    arguments = operation.get("arguments", [])
    return {
        "target": match.group("member"),
        "operation": _COLLECTION_ACTIONS[match.group("action")],
        "expression": ", ".join(str(item.get("expression", "")) for item in arguments),
        **_applicability(operation),
        "line": _line(operation),
    }


def _contains_operation(parent: dict[str, Any], child: dict[str, Any]) -> bool:
    if parent is child:
        return False
    parent_location = parent["location"]
    child_location = child["location"]
    return (
        parent_location["line"] <= child_location["line"]
        and child_location["end_line"] <= parent_location["end_line"]
        and str(child.get("expression", "")) in str(parent.get("expression", ""))
    )


def _project_module_rules_class(rules_class: dict[str, Any]) -> dict[str, Any]:
    reachable = _reachable_method_names(rules_class)
    methods = [
        method for method in rules_class["methods"] if method["name"] in reachable
    ]
    method_names = {method["name"] for method in rules_class["methods"]}
    mutation_operations: list[dict[str, Any]] = []
    declared: list[dict[str, Any]] = []
    unclassified: list[dict[str, Any]] = []

    for method in methods:
        for operation in method["operations"]:
            known = _known_mutation(operation)
            if known is not None:
                declared.append(known)
                mutation_operations.append(operation)
                continue
            unknown = _unclassified_mutation(operation)
            if unknown is not None:
                unclassified.append(unknown)
                mutation_operations.append(operation)

    unresolved_calls: list[dict[str, Any]] = []
    mutation_operation_ids = {id(operation) for operation in mutation_operations}
    for method in methods:
        for operation in method["operations"]:
            if (
                operation["kind"] != "invocation"
                or id(operation) in mutation_operation_ids
            ):
                continue
            callee = str(operation.get("callee", ""))
            callee_name = callee.split(".")[-1].split("::")[-1]
            if callee_name in method_names:
                continue
            if not _BARE_CALL.fullmatch(callee):
                continue
            if any(_contains_operation(parent, operation) for parent in mutation_operations):
                continue
            unresolved_calls.append(
                {
                    "callee": callee,
                    "arguments": [
                        str(argument.get("expression", ""))
                        for argument in operation.get("arguments", [])
                    ],
                    **_applicability(operation),
                    "line": _line(operation),
                }
            )

    def source_key(item: dict[str, Any]) -> int:
        return int(item["line"])

    return {
        "name": rules_class["name"],
        "declared_mutations": sorted(declared, key=source_key),
        "unclassified_mutations": sorted(unclassified, key=source_key),
        "unresolved_effect_calls": sorted(unresolved_calls, key=source_key),
    }


def inspect_module_rules(path: Path) -> dict[str, Any]:
    facts = parse_rule_file(path, "ModuleRules")
    content = {
        "path": facts["path"],
        "rules_classes": [
            _project_module_rules_class(rules_class)
            for rules_class in facts["rules_classes"]
        ],
    }
    return result_document(
        "ue-itps.module-rule-relations.v1",
        content,
        _rules_class_problems(facts, "ModuleRules"),
        responsibility=(
            "Report declared ModuleRules mutations and referenced values from one Build.cs file."
        ),
        boundaries=[
            "Static declarations are not effective UBT build results.",
            "Only constructors and statically reachable same-file helpers contribute mutations.",
            "Applicability reports direct or recognized enclosing control structures; direct does not prove runtime execution.",
            "Control paths preserve only ordered construct kinds; condition expressions are not returned or evaluated.",
            "Related symbols come from enclosing controls and are not evaluated or classified as inputs versus constants.",
            "Explicit mutations and calls in control expressions are reported; short-circuit and ternary gating are syntactic approximations, not a full C# control-flow model.",
            "Caller control paths are not propagated into mutations inside reachable helpers.",
            "Unclassified mutations are candidates, not confirmed ModuleRules members.",
            "Unresolved effect calls identify possible rule changes without inferring their effects.",
            "Output order is deterministic source order, not runtime execution order.",
        ],
    )
