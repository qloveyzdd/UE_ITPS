from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .common import result_document
from .source_parser import parse_rule_file


_REFERENCE_KINDS = {
    "ExtraModuleNames": "module",
    "EnablePlugins": "plugin",
    "DisablePlugins": "plugin",
    "GlobalDefinitions": "definition",
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
_TARGET_COLLECTION_MUTATION = re.compile(
    r"^(?P<target>.+)\.(?P<action>AddRange|Add|Remove|RemoveAll)$"
)
_TARGET_RULES_PARAMETER = re.compile(
    r"(?:^|,)\s*(?:(?:ref|out|in)\s+)?"
    r"(?:[A-Za-z_]\w*\.)*TargetRules\s+(?P<name>[A-Za-z_]\w*)"
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


def _target_rules_problems(facts: dict[str, Any]) -> list[dict[str, Any]]:
    if not facts["rules_classes"]:
        return _rules_class_problems(facts, "TargetRules")
    return [
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
    ]


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


def _target_receivers(method: dict[str, Any]) -> set[str]:
    return {
        match.group("name")
        for match in _TARGET_RULES_PARAMETER.finditer(str(method["parameters"]))
    }


def _local_names(method: dict[str, Any]) -> set[str]:
    return set(method.get("declared_names", [])) | {
        str(operation["declared_name"])
        for operation in method["operations"]
        if operation.get("declared_name")
    }


def _root_name(expression: str) -> str:
    match = re.match(r"(?:this\.)?(?P<root>[A-Za-z_]\w*)", expression)
    return match.group("root") if match else ""


def _target_setting(
    expression: str,
    method: dict[str, Any],
    local_names: set[str],
    declared_fields: set[str],
) -> str | None:
    normalized_expression = expression.replace("->", ".").replace("::", ".")
    if normalized_expression.startswith("this."):
        setting = normalized_expression[5:]
        return None if _root_name(setting) in declared_fields else setting
    for receiver in _target_receivers(method):
        prefix = f"{receiver}."
        if normalized_expression.startswith(prefix):
            return normalized_expression[len(prefix) :]
    if _root_name(normalized_expression) in local_names | declared_fields:
        return None
    if method["is_constructor"]:
        return normalized_expression
    return None


def _target_applicability(operation: dict[str, Any]) -> dict[str, Any]:
    controls: list[dict[str, Any]] = []
    ordered_controls: list[tuple[int, int, dict[str, Any]]] = []
    for index, item in enumerate(operation.get("conditions", [])):
        ordered_controls.append(
            (
                int(item.get("start_line", 0)),
                index,
                {
                    key: item[key]
                    for key in ("kind", "expression", "branch")
                    if item.get(key) not in {None, ""}
                },
            )
        )
    for index, item in enumerate(operation.get("control_details", [])):
        if item.get("kind") in {"if", "preprocessor"}:
            continue
        ordered_controls.append(
            (
                int(item.get("start_line", 0)),
                len(ordered_controls) + index,
                {
                    key: item[key]
                    for key in ("kind", "expression", "branch")
                    if item.get(key) not in {None, ""}
                },
            )
        )
    controls.extend(
        item for _, _, item in sorted(ordered_controls, key=lambda value: value[:2])
    )
    applicability: dict[str, Any] = {
        "kind": (
            "conditional"
            if controls or operation.get("applicability") == "conditional"
            else "direct"
        )
    }
    if controls:
        applicability["controls"] = controls
    return {"applicability": applicability}


def _target_source(
    method: dict[str, Any], operation: dict[str, Any]
) -> dict[str, Any]:
    return {
        "source": {
            "method": str(method["name"]),
            "line": _line(operation),
        }
    }


def _target_mutation(
    operation: dict[str, Any],
    method: dict[str, Any],
    local_names: set[str],
    declared_fields: set[str],
) -> dict[str, Any] | None:
    if operation.get("declared_name") or _is_empty_collection_argument(operation):
        return None
    if operation["kind"] == "assignment":
        setting = _target_setting(
            str(operation.get("target", "")), method, local_names, declared_fields
        )
        if not setting:
            return None
        action = _ASSIGNMENT_ACTIONS.get(
            str(operation.get("operator", "")), "set"
        )
    else:
        match = _TARGET_COLLECTION_MUTATION.fullmatch(
            str(operation.get("callee", ""))
        )
        if not match:
            return None
        setting = _target_setting(
            match.group("target"), method, local_names, declared_fields
        )
        if not setting:
            return None
        action = _COLLECTION_ACTIONS[match.group("action")]
    return {
        "setting": setting,
        "operation": action,
        "operand": _operand(operation, setting),
        **_target_applicability(operation),
        **_target_source(method, operation),
    }


def _unclassified_target_mutation(
    operation: dict[str, Any], method: dict[str, Any], local_names: set[str]
) -> dict[str, Any] | None:
    if operation.get("declared_name"):
        return None
    expression = str(
        operation.get("target", "")
        if operation["kind"] == "assignment"
        else operation.get("callee", "")
    )
    if _root_name(expression) in local_names:
        return None
    candidate = _unclassified_mutation(operation)
    if candidate is None:
        return None
    candidate.pop("applicability", None)
    candidate.pop("line", None)
    candidate.update(_target_applicability(operation))
    candidate.update(_target_source(method, operation))
    return candidate


def _project_target_rules_class(rules_class: dict[str, Any]) -> dict[str, Any]:
    reachable = _reachable_method_names(rules_class)
    methods = [
        method for method in rules_class["methods"] if method["name"] in reachable
    ]
    method_names = {method["name"] for method in rules_class["methods"]}
    declared_fields = set(rules_class.get("declared_fields", []))
    mutation_operations: list[dict[str, Any]] = []
    declared: list[dict[str, Any]] = []
    unclassified: list[dict[str, Any]] = []

    for method in methods:
        local_names = _local_names(method)
        excluded_names = local_names | declared_fields
        for operation in method["operations"]:
            known = _target_mutation(
                operation, method, local_names, declared_fields
            )
            if known is not None:
                declared.append(known)
                mutation_operations.append(operation)
                continue
            unknown = _unclassified_target_mutation(
                operation, method, excluded_names
            )
            if unknown is not None:
                unclassified.append(unknown)
                mutation_operations.append(operation)

    unresolved_calls: list[dict[str, Any]] = []
    mutation_operation_ids = {id(operation) for operation in mutation_operations}
    for method in methods:
        excluded_names = _local_names(method) | declared_fields
        receivers = _target_receivers(method)
        for operation in method["operations"]:
            if (
                operation["kind"] != "invocation"
                or id(operation) in mutation_operation_ids
            ):
                continue
            callee = str(operation.get("callee", ""))
            callee_name = callee.split(".")[-1].split("::")[-1]
            if callee_name in method_names or _root_name(callee) in excluded_names:
                continue
            direct_target_call = any(
                callee.startswith(f"{receiver}.") and callee.count(".") == 1
                for receiver in receivers
            )
            if not _BARE_CALL.fullmatch(callee) and not direct_target_call:
                continue
            if any(
                _contains_operation(parent, operation)
                for parent in mutation_operations
            ):
                continue
            unresolved_calls.append(
                {
                    "callee": callee,
                    "arguments": [
                        str(argument.get("expression", ""))
                        for argument in operation.get("arguments", [])
                    ],
                    **_target_applicability(operation),
                    **_target_source(method, operation),
                }
            )

    def source_key(item: dict[str, Any]) -> int:
        return int(item["source"]["line"])

    return {
        "name": rules_class["name"],
        "inheritance": {
            "kind": rules_class.get("base_resolution", "confirmed"),
            "base_types": list(rules_class["base_types"]),
        },
        "declared_mutations": sorted(declared, key=source_key),
        "unclassified_mutations": sorted(unclassified, key=source_key),
        "unresolved_effect_calls": sorted(unresolved_calls, key=source_key),
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
        "ue-itps.target-rule-relations.v1",
        content,
        _target_rules_problems(facts),
        responsibility=(
            "Report declared TargetRules mutations and referenced values from one Target.cs file."
        ),
        boundaries=[
            "Static declarations are not effective UBT build results.",
            "Only constructors and statically reachable same-file helpers contribute mutations.",
            "Conditions and expressions are preserved but are not executed against a Target profile.",
            "Caller conditions are not propagated into mutations inside reachable helpers.",
            "Unclassified mutations are candidates, not confirmed TargetRules members.",
            "Unresolved effect calls identify possible rule changes without inferring their effects.",
            "Filename-matching Target candidates with unresolved bases are local evidence, not inheritance proof.",
            "Output order is deterministic source order, not runtime execution order.",
        ],
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
