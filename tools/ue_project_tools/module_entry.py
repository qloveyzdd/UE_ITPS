from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
import re
from typing import Any

from .common import normalized, result_document
from .source_parser import parse_cpp_file, parse_operations, source_files


_REGISTER_APIS = {
    "AddRaw",
    "AddUObject",
    "AddSP",
    "AddStatic",
    "AddLambda",
    "AddWeakLambda",
    "BindRaw",
    "BindUObject",
    "BindSP",
    "BindStatic",
    "BindLambda",
    "RegisterStartupCallback",
}
_UNREGISTER_APIS = {
    "Remove",
    "RemoveAll",
    "Unbind",
    "Clear",
    "UnRegisterStartupCallback",
    "UnregisterStartupCallback",
}


def _with_path(location: dict[str, Any], path: str) -> dict[str, Any]:
    return {"path": path, **location}


def _method_name_from_callee(callee: str) -> str:
    return callee.rsplit(".", 1)[-1].rsplit("::", 1)[-1]


def _delegate_source(callee: str, api: str) -> str:
    suffix = "." + api
    if callee.endswith(suffix):
        return callee[: -len(suffix)]
    suffix = "::" + api
    if callee.endswith(suffix):
        return callee[: -len(suffix)]
    return callee


def _callback_target(operation: dict[str, Any], class_name: str, method_names: set[str]) -> str | None:
    expressions = [str(argument.get("expression", "")) for argument in operation.get("arguments", [])]
    for expression in expressions:
        match = re.search(r"&\s*(?:(?P<class>[A-Za-z_]\w*)\s*::\s*)?(?P<method>[A-Za-z_]\w*)", expression)
        if not match:
            continue
        owner = match.group("class")
        method = match.group("method")
        if owner == "ThisClass":
            owner = class_name
        if owner:
            return f"{owner}::{method}"
        return f"{class_name}::{method}" if method in method_names else method
    if any("[" in expression and "]" in expression for expression in expressions):
        return "<lambda>"
    return None


def _looks_like_delegate(source: str, api: str, callback: str | None, known_sources: set[str]) -> bool:
    if callback or api in {"RemoveAll", "Unbind", "RegisterStartupCallback", "UnRegisterStartupCallback", "UnregisterStartupCallback"}:
        return True
    if source in known_sources:
        return True
    last = source.rsplit(".", 1)[-1].rsplit("::", 1)[-1]
    return "Delegate" in source or "Callback" in source or bool(re.match(r"On[A-Z_]", last))


def _delegate_operations(
    methods: dict[str, dict[str, Any]],
    reachable: dict[str, set[str]],
    class_name: str,
) -> list[dict[str, Any]]:
    method_names = set(methods)
    preliminary: list[tuple[str, dict[str, Any], str, str, str | None]] = []
    known_sources: set[str] = set()
    for method_name in sorted(reachable):
        for operation in methods[method_name]["operations"]:
            if operation.get("kind") != "invocation":
                continue
            callee = str(operation.get("callee", ""))
            api = _method_name_from_callee(callee)
            if api not in _REGISTER_APIS | _UNREGISTER_APIS:
                continue
            source = _delegate_source(callee, api)
            callback = _callback_target(operation, class_name, method_names)
            action = "register" if api in _REGISTER_APIS else "unregister"
            if action == "register" and callback:
                known_sources.add(source)
            preliminary.append((method_name, operation, action, source, callback))

    results: list[dict[str, Any]] = []
    for method_name, operation, action, source, callback in preliminary:
        api = _method_name_from_callee(str(operation["callee"]))
        if not _looks_like_delegate(source, api, callback, known_sources):
            continue
        results.append(
            {
                "action": action,
                "delegate_source": source,
                "binding_api": api,
                "callback_target": callback,
                "method": method_name,
                "roots": sorted(reachable[method_name]),
                "expression": operation["expression"],
                "conditions": operation["conditions"],
                "location": operation["location"],
            }
        )
    for index, item in enumerate(results):
        item["matching_operation_locations"] = [
            other["location"]
            for other_index, other in enumerate(results)
            if other_index != index
            and other["delegate_source"] == item["delegate_source"]
            and other["action"] != item["action"]
        ]
    return results


def _reachable(graph: dict[str, set[str]], roots: list[str], marker: str | None = None) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for root in roots:
        label = marker or root
        queue: deque[str] = deque([root])
        visited: set[str] = set()
        while queue:
            method = queue.popleft()
            if method in visited:
                continue
            visited.add(method)
            result[method].add(label)
            queue.extend(sorted(graph.get(method, set())))
    return result


def inspect_module_entry(rules_path: Path) -> dict[str, Any]:
    rules = rules_path.resolve()
    module_name = rules.name[: -len(".Build.cs")] if rules.name.casefold().endswith(".build.cs") else rules.stem
    module_root = rules.parent
    parsed_files = [parse_cpp_file(path) for path in source_files(module_root)]
    registrations = [
        {**macro, "location": _with_path(macro["location"], parsed["path"])}
        for parsed in parsed_files
        for macro in parsed["registration_macros"]
    ]
    matching_registrations = [
        item for item in registrations if str(item.get("module_name", "")).casefold() == module_name.casefold()
    ]
    problems: list[dict[str, Any]] = []
    if not matching_registrations:
        problems.append(
            {
                "severity": "warning",
                "code": "module-registration-not-found",
                "module_name": module_name,
                "message": f"No matching IMPLEMENT_*_MODULE declaration was found for {module_name}",
            }
        )
    elif len(matching_registrations) > 1:
        problems.append(
            {
                "severity": "warning",
                "code": "module-registration-ambiguous",
                "module_name": module_name,
                "locations": [item["location"] for item in matching_registrations],
                "message": f"Multiple matching IMPLEMENT_*_MODULE declarations were found for {module_name}",
            }
        )

    class_parts: dict[str, dict[str, Any]] = {}
    for parsed in parsed_files:
        for class_item in parsed["classes"]:
            part = class_parts.setdefault(
                class_item["name"],
                {"base_types": set(), "declarations": [], "method_parts": []},
            )
            part["base_types"].update(class_item["base_types"])
            part["declarations"].append(_with_path(class_item["location"], parsed["path"]))
            for member in class_item["members"]:
                operations: list[dict[str, Any]] = []
                if member["body_range"]:
                    operations = parse_operations(
                        parsed["text"],
                        parsed["tokens"],
                        parsed["forward"],
                        parsed["reverse"],
                        member["body_range"][0],
                        member["body_range"][1],
                    )
                    for operation in operations:
                        operation["location"] = _with_path(operation["location"], parsed["path"])
                part["method_parts"].append(
                    {
                        "name": member["name"],
                        "parameters": member["parameters"],
                        "signature": member["signature"],
                        "declaration": _with_path(member["location"], parsed["path"]),
                        "definition": _with_path(member["location"], parsed["path"]) if member["has_body"] else None,
                        "operations": operations,
                    }
                )
        for definition in parsed["external_definitions"]:
            part = class_parts.setdefault(
                definition["class_name"],
                {"base_types": set(), "declarations": [], "method_parts": []},
            )
            operations = parse_operations(
                parsed["text"],
                parsed["tokens"],
                parsed["forward"],
                parsed["reverse"],
                definition["body_range"][0],
                definition["body_range"][1],
            )
            for operation in operations:
                operation["location"] = _with_path(operation["location"], parsed["path"])
            part["method_parts"].append(
                {
                    "name": definition["name"],
                    "parameters": definition["parameters"],
                    "signature": definition["signature"],
                    "declaration": None,
                    "definition": _with_path(definition["location"], parsed["path"]),
                    "operations": operations,
                }
            )

    macro_class_names = {
        str(item["module_class"])
        for item in matching_registrations
        if item.get("module_class")
    }
    inferred_class_names = {
        name
        for name, part in class_parts.items()
        if any(base.endswith("ModuleInterface") or base.endswith("GameModuleImpl") for base in part["base_types"])
    }
    module_class_names = sorted(macro_class_names | inferred_class_names)
    output_classes: list[dict[str, Any]] = []
    for class_name in module_class_names:
        if class_name not in class_parts:
            if class_name not in {"FDefaultModuleImpl", "FDefaultGameModuleImpl"}:
                problems.append(
                    {
                        "severity": "warning",
                        "code": "module-class-definition-not-found",
                        "module_class": class_name,
                        "message": f"Module class {class_name} was registered but not declared in the module source tree",
                    }
                )
            continue
        part = class_parts[class_name]
        merged: dict[str, dict[str, Any]] = {}
        for method_part in part["method_parts"]:
            method = merged.setdefault(
                method_part["name"],
                {
                    "name": method_part["name"],
                    "parameters": set(),
                    "signatures": set(),
                    "declarations": [],
                    "definitions": [],
                    "operations": [],
                },
            )
            method["parameters"].add(method_part["parameters"])
            method["signatures"].add(method_part["signature"])
            if method_part["declaration"]:
                method["declarations"].append(method_part["declaration"])
            if method_part["definition"]:
                method["definitions"].append(method_part["definition"])
            method["operations"].extend(method_part["operations"])
        methods: dict[str, dict[str, Any]] = {}
        for name, method in merged.items():
            methods[name] = {
                "name": name,
                "parameters": sorted(method["parameters"]),
                "signatures": sorted(method["signatures"]),
                "declarations": method["declarations"],
                "definitions": method["definitions"],
                "operations": sorted(
                    method["operations"],
                    key=lambda item: (
                        item["location"]["path"],
                        item["location"]["line"],
                    ),
                ),
            }
        graph: dict[str, set[str]] = defaultdict(set)
        for method_name, method in methods.items():
            for operation in method["operations"]:
                if operation.get("kind") != "invocation":
                    continue
                callee = _method_name_from_callee(str(operation.get("callee", "")))
                if callee in methods and callee != method_name:
                    graph[method_name].add(callee)
        lifecycle_roots = [name for name in ("StartupModule", "ShutdownModule") if name in methods]
        reachable = _reachable(graph, lifecycle_roots)
        first_pass_delegate_operations = _delegate_operations(methods, reachable, class_name)
        callback_methods = sorted(
            {
                callback.rsplit("::", 1)[-1]
                for item in first_pass_delegate_operations
                if item["action"] == "register"
                and (callback := item.get("callback_target"))
                and callback != "<lambda>"
                and callback.rsplit("::", 1)[-1] in methods
            }
        )
        callback_reachable = _reachable(graph, callback_methods, "bound-callback")
        for method_name, roots in callback_reachable.items():
            reachable[method_name].update(roots)
        delegate_operations = _delegate_operations(methods, reachable, class_name)
        output_classes.append(
            {
                "name": class_name,
                "base_types": sorted(part["base_types"]),
                "declarations": part["declarations"],
                "methods": [methods[name] for name in sorted(methods)],
                "lifecycle_methods": lifecycle_roots,
                "lifecycle_reachability": [
                    {"method": name, "roots": sorted(roots)}
                    for name, roots in sorted(reachable.items())
                ],
                "same_file_calls": [
                    {"caller": caller, "callee": callee}
                    for caller in sorted(graph)
                    for callee in sorted(graph[caller])
                ],
                "delegate_operations": delegate_operations,
            }
        )

    return result_document(
        "ue-itps.module-entry-source.v1",
        {
            "module_name": module_name,
            "build_rules_path": normalized(rules),
            "module_root": normalized(module_root),
            "source_files": [normalized(path) for path in source_files(module_root)],
            "registration_macros": registrations,
            "module_classes": output_classes,
        },
        problems,
        responsibility="Inspect module registration, lifecycle methods, and lifecycle-bound delegates for one module.",
        boundaries=[
            "The selected Build.cs parent directory defines the module source boundary.",
            "Only lifecycle helpers and callbacks bound by reachable lifecycle code are followed.",
            "No general C++ class graph or project-wide call graph is produced.",
            "Conditions and delegate operations are static source facts and are not runtime behavior evidence.",
        ],
    )
