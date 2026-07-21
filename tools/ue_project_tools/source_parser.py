from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .common import iter_files, normalized
from .source_controls import _registration_preprocessor_contexts
from .source_controls import control_expression_ranges
from .source_declarations import (
    _class_field_names,
    _local_declaration_names,
    parse_classes,
    parse_external_definitions,
    parse_free_functions,
)
from .source_flow import condition_spans, control_spans
from .source_operations import parse_operations
from .source_preprocessor import (
    preprocessor_conditions,
    preprocessor_control_contexts,
)
from .source_tokens import (
    Token,
    _location,
    _raw,
    _split_arguments,
    delimiter_problems,
    lex_source,
    token_pairs,
)


_MODULE_RULE_KINDS = {
    "PublicDependencyModuleNames": "public_dependency",
    "PrivateDependencyModuleNames": "private_dependency",
    "DynamicallyLoadedModuleNames": "dynamic_dependency",
    "PublicIncludePathModuleNames": "public_include_module",
    "PrivateIncludePathModuleNames": "private_include_module",
    "PublicIncludePaths": "public_include_path",
    "PrivateIncludePaths": "private_include_path",
    "PublicSystemIncludePaths": "public_system_include_path",
    "PublicDefinitions": "public_definition",
    "PrivateDefinitions": "private_definition",
}


def _rule_annotation(operation: dict[str, Any]) -> dict[str, str] | None:
    if operation["kind"] == "invocation":
        callee = str(operation.get("callee", ""))
        match = re.search(
            r"(?:^|[.>])(?P<member>[A-Za-z_]\w*)\."
            r"(?P<action>AddRange|Add|Remove|RemoveAll)$",
            callee,
        )
        if match and match.group("member") in _MODULE_RULE_KINDS:
            return {
                "kind": _MODULE_RULE_KINDS[match.group("member")],
                "member": match.group("member"),
                "action": match.group("action"),
            }
    else:
        target = str(operation.get("target", "")).split(".")[-1]
        if target in _MODULE_RULE_KINDS:
            return {
                "kind": _MODULE_RULE_KINDS[target],
                "member": target,
                "action": "assign",
            }
        if target in {"PCHUsage", "PrivatePCHHeaderFile", "SharedPCHHeaderFile"}:
            return {"kind": "pch", "member": target, "action": "assign"}
        if target in {"bEnforceIWYU", "IWYUSupport", "bLegacyPublicIncludePaths"}:
            return {"kind": "iwyu", "member": target, "action": "assign"}
    return None


def parse_rule_file(path: Path, required_base_type: str) -> dict[str, Any]:
    resolved = path.resolve()
    text = resolved.read_text(encoding="utf-8-sig", errors="replace")
    tokens = lex_source(text)
    classes, forward, reverse = parse_classes(text, tokens)
    known_bases = {required_base_type}
    selected: list[dict[str, Any]] = []
    base_resolution: dict[str, str] = {}
    pending = list(classes)
    while pending:
        changed = False
        for item in list(pending):
            if any(base.split("<", 1)[0] in known_bases for base in item["base_types"]):
                selected.append(item)
                base_resolution[item["name"]] = "confirmed"
                known_bases.add(item["name"])
                pending.remove(item)
                changed = True
        if not changed:
            break

    if required_base_type == "TargetRules" and resolved.name.casefold().endswith(
        ".target.cs"
    ):
        expected_name = resolved.name[: -len(".Target.cs")] + "Target"
        for item in list(pending):
            has_target_constructor = any(
                member["is_constructor"]
                and re.search(r"\bTargetInfo\b", str(member["parameters"]))
                for member in item["members"]
            )
            if item["name"].casefold() == expected_name.casefold() and has_target_constructor:
                selected.append(item)
                base_resolution[item["name"]] = "unresolved"
                pending.remove(item)

    selected.sort(key=lambda item: int(item["location"]["line"]))

    rules_classes: list[dict[str, Any]] = []
    for item in selected:
        methods: list[dict[str, Any]] = []
        for member in item["members"]:
            operation_items: list[dict[str, Any]] = []
            declared_names: list[str] = []
            if member["body_range"]:
                declared_names = _local_declaration_names(
                    text,
                    tokens,
                    member["body_range"][0],
                    member["body_range"][1],
                )
                operation_items = parse_operations(
                    text,
                    tokens,
                    forward,
                    reverse,
                    member["body_range"][0],
                    member["body_range"][1],
                    include_control_metadata=required_base_type
                    in {"ModuleRules", "TargetRules"},
                )
                if required_base_type == "ModuleRules":
                    for operation in operation_items:
                        annotation = _rule_annotation(operation)
                        if annotation:
                            operation["rule"] = annotation
            methods.append(
                {
                    "name": member["name"],
                    "parameters": member["parameters"],
                    "signature": member["signature"],
                    "is_constructor": member["is_constructor"],
                    "location": member["location"],
                    "declared_names": declared_names,
                    "operations": operation_items,
                }
            )
        method_names = {method["name"] for method in methods}
        calls: list[dict[str, Any]] = []
        for method in methods:
            for operation in method["operations"]:
                if operation["kind"] != "invocation":
                    continue
                callee = str(operation["callee"]).split(".")[-1].split("::")[-1]
                if callee in method_names and callee != method["name"]:
                    calls.append(
                        {
                            "caller": method["name"],
                            "callee": callee,
                            "location": operation["location"],
                        }
                    )
        unique_calls = {
            (call["caller"], call["callee"], call["location"]["line"]): call
            for call in calls
        }
        rules_classes.append(
            {
                "name": item["name"],
                "base_types": item["base_types"],
                "base_resolution": base_resolution[item["name"]],
                "location": item["location"],
                "declared_fields": _class_field_names(
                    text,
                    tokens,
                    item["body_range"][0],
                    item["body_range"][1],
                ),
                "methods": methods,
                "same_file_calls": sorted(
                    unique_calls.values(),
                    key=lambda value: (value["caller"], value["callee"], value["location"]["line"]),
                ),
            }
        )
    return {"path": normalized(resolved), "rules_classes": rules_classes}


def registration_macros(text: str, tokens: list[Token]) -> list[dict[str, Any]]:
    forward, _ = token_pairs(tokens)
    preprocessor = _registration_preprocessor_contexts(text)
    results: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if not token.value.startswith("IMPLEMENT_") or not token.value.endswith("MODULE"):
            continue
        if index + 1 >= len(tokens) or tokens[index + 1].value != "(" or index + 1 not in forward:
            continue
        conditions = preprocessor.get(token.line, [])
        if any(condition["active"] is False for condition in conditions):
            continue
        close = forward[index + 1]
        ranges = _split_arguments(tokens, index + 2, close)
        arguments = [_raw(text, tokens, start, end) for start, end in ranges]
        item: dict[str, Any] = {
            "macro": token.value,
            "module_class": arguments[0] if arguments else None,
            "module_name": arguments[1] if len(arguments) > 1 else None,
            "arguments": arguments,
            "location": _location(token, tokens[close]),
        }
        if conditions:
            item["preprocessor_conditions"] = [
                {
                    key: condition[key]
                    for key in ("group_line", "arm", "branch", "expression")
                }
                for condition in conditions
            ]
        results.append(item)
    return results


def parse_cpp_file(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    text = resolved.read_text(encoding="utf-8-sig", errors="replace")
    tokens = lex_source(text)
    classes, forward, reverse = parse_classes(text, tokens)
    external = parse_external_definitions(text, tokens, forward)
    free_functions = parse_free_functions(text, tokens, forward)
    return {
        "path": normalized(resolved),
        "text": text,
        "tokens": tokens,
        "forward": forward,
        "reverse": reverse,
        "classes": classes,
        "external_definitions": external,
        "free_functions": free_functions,
        "registration_macros": registration_macros(text, tokens),
        "problems": delimiter_problems(tokens),
    }


def source_files(module_dir: Path) -> list[Path]:
    suffixes = (".h", ".hpp", ".cpp", ".cc")
    return sorted(
        {
            path.resolve()
            for suffix in suffixes
            for path in iter_files(module_dir, suffix)
        },
        key=lambda path: normalized(path).casefold(),
    )
