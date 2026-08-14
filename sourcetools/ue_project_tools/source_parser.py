from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .common import iter_files, normalized
from .syntax_tree import parse_csharp_model, parse_csharp_syntax


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


def parse_csharp_file(
    path: Path,
    *,
    include_operations: bool = True,
) -> dict[str, Any]:
    resolved = path.resolve()
    if resolved.suffix.casefold() != ".cs":
        raise ValueError(f"Expected a .cs file: {resolved}")
    text = resolved.read_text(encoding="utf-8-sig", errors="replace")
    model = parse_csharp_model(text)
    classes = model["classes"]
    if not include_operations:
        classes = [
            {
                **item,
                "methods": [{**method, "operations": []} for method in item["methods"]],
            }
            for item in classes
        ]
    syntax_tree = parse_csharp_syntax(text)
    problems: list[dict[str, Any]] = []
    if syntax_tree["parse_error_count"]:
        problems.append(
            {
                "severity": "error",
                "code": "csharp-syntax-tree-errors",
                "path": normalized(resolved),
                "count": syntax_tree["parse_error_count"],
                "message": "Tree-sitter reported incomplete C# syntax regions",
            }
        )
    return {
        "path": normalized(resolved),
        "classes": classes,
        "syntax_tree": syntax_tree,
        "problems": problems,
    }


def parse_rule_file(path: Path, required_base_type: str) -> dict[str, Any]:
    parsed = parse_csharp_file(path, include_operations=True)
    resolved = Path(parsed["path"])
    classes = parsed["classes"]
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
                method["is_constructor"]
                and any(
                    parameter["type_expression"] == "TargetInfo"
                    for parameter in method.get("parameter_variables", [])
                )
                for method in item["methods"]
            )
            if (
                item["name"].casefold() == expected_name.casefold()
                and has_target_constructor
            ):
                selected.append(item)
                base_resolution[item["name"]] = "unresolved"
                pending.remove(item)

    selected.sort(key=lambda item: int(item["location"]["line"]))
    rules_classes: list[dict[str, Any]] = []
    for item in selected:
        methods = item["methods"]
        if required_base_type == "ModuleRules":
            for method in methods:
                for operation in method["operations"]:
                    annotation = _rule_annotation(operation)
                    if annotation:
                        operation["rule"] = annotation
        method_names = {method["name"] for method in methods}
        calls = []
        for method in methods:
            for operation in method["operations"]:
                if operation["kind"] != "invocation":
                    continue
                callee = str(operation["callee"]).split(".")[-1]
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
                **item,
                "base_resolution": base_resolution[item["name"]],
                "same_file_calls": sorted(
                    unique_calls.values(),
                    key=lambda value: (
                        value["caller"],
                        value["callee"],
                        value["location"]["line"],
                    ),
                ),
            }
        )
    return {
        "path": normalized(resolved),
        "rules_classes": rules_classes,
        "syntax_tree": parsed["syntax_tree"],
        "problems": list(parsed["problems"]),
    }


def source_files(module_dir: Path) -> list[Path]:
    return sorted(
        {
            path.resolve()
            for suffix in (".h", ".hpp", ".cpp", ".cc")
            for path in iter_files(module_dir, suffix)
        },
        key=lambda path: normalized(path).casefold(),
    )
