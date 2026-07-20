from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
import re
from typing import Any

from .common import normalized, result_document
from .source_parser import parse_cpp_file, parse_operations, source_files


_REGISTER_APIS = frozenset(
    {
        "Add",
        "AddDynamic",
        "AddLambda",
        "AddRaw",
        "AddSP",
        "AddStatic",
        "AddThreadSafeSP",
        "AddUFunction",
        "AddUnique",
        "AddUniqueDynamic",
        "AddUObject",
        "AddWeakLambda",
        "Bind",
        "BindDynamic",
        "BindLambda",
        "BindRaw",
        "BindSP",
        "BindStatic",
        "BindThreadSafeSP",
        "BindUFunction",
        "BindUObject",
        "BindWeakLambda",
        "RegisterStartupCallback",
    }
)
_UNREGISTER_APIS = frozenset(
    {
        "Clear",
        "Remove",
        "RemoveAll",
        "RemoveDynamic",
        "Unbind",
        "UnRegisterStartupCallback",
        "UnregisterStartupCallback",
    }
)


def _with_path(location: dict[str, Any], path: str) -> dict[str, Any]:
    return {"path": path, **location}


def _relative_path(path: str | Path, root: Path) -> str:
    return Path(path).resolve().relative_to(root).as_posix()


def _callee_parts(callee: str) -> tuple[str | None, str]:
    matches = [
        (callee.rfind(separator), separator)
        for separator in (".", "::", "->")
        if separator in callee
    ]
    if not matches:
        return None, callee
    index, separator = max(matches, key=lambda item: item[0])
    return callee[:index], callee[index + len(separator) :]


def _method_name_from_callee(callee: str) -> str:
    return _callee_parts(callee)[1]


def _self_method_name(callee: str, class_name: str) -> str | None:
    receiver, method = _callee_parts(callee)
    if receiver is None or receiver in {"this", "ThisClass", class_name}:
        return method
    return None


def _delegate_source(callee: str, api: str) -> str:
    receiver, method = _callee_parts(callee)
    return receiver if receiver is not None and method == api else callee


def _delegate_action(api: str) -> str | None:
    if api in _REGISTER_APIS:
        return "register"
    if api in _UNREGISTER_APIS:
        return "unregister"
    return None


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


def _local_callback_method(
    callback: str | None,
    class_name: str,
    method_names: set[str],
) -> str | None:
    if not callback or callback == "<lambda>":
        return None
    if "::" not in callback:
        return callback if callback in method_names else None
    owner, method = callback.rsplit("::", 1)
    return method if owner == class_name and method in method_names else None


def _source_looks_like_delegate(source: str) -> bool:
    last = _callee_parts(source)[1]
    return "Delegate" in source or "Callback" in source or bool(re.match(r"On[A-Z_]", last))


def _looks_like_delegate(source: str, api: str, callback: str | None, known_sources: set[str]) -> bool:
    if source in known_sources:
        return True
    if _source_looks_like_delegate(source):
        return True
    return callback is not None and api not in {"Add", "Remove", "Clear"}


def _assigned_target(
    method: dict[str, Any],
    invocation: dict[str, Any],
) -> str | None:
    def contains(
        assignment_location: dict[str, Any],
        invocation_location: dict[str, Any],
    ) -> bool:
        return (
            assignment_location.get("path") == invocation_location.get("path")
            and int(assignment_location.get("line", 0))
            <= int(invocation_location.get("line", 0))
            and int(assignment_location.get("end_line", 0))
            >= int(invocation_location.get("end_line", 0))
        )

    invocation_expression = str(invocation.get("expression", ""))
    invocation_location = invocation.get("location", {})
    candidates = [
        str(operation.get("target", ""))
        for operation in method["operations"]
        if operation.get("kind") == "assignment"
        and operation.get("operator") == "="
        and contains(operation.get("location", {}), invocation_location)
        and invocation_expression
        and invocation_expression in str(operation.get("value_expression", ""))
    ]
    unique = sorted({candidate for candidate in candidates if candidate})
    return unique[0] if len(unique) == 1 else None


def _delegate_relationship(
    first: dict[str, Any],
    second: dict[str, Any],
    handle_use_counts: dict[tuple[str, str], tuple[int, int]],
) -> str:
    register = first if first["action"] == "register" else second
    unregister = second if register is first else first
    register_arguments = register["_argument_expressions"]
    unregister_arguments = unregister["_argument_expressions"]

    if (
        register["result_target"]
        and unregister_arguments
        and register["result_target"] == unregister_arguments[0]
    ):
        counts = handle_use_counts.get(
            (register["delegate_source"], register["result_target"]),
            (0, 0),
        )
        return "exact-handle" if counts == (1, 1) else "same-handle-candidate"
    if (
        unregister["binding_api"] == "RemoveDynamic"
        and register_arguments
        and unregister_arguments
        and register_arguments[0] == unregister_arguments[0]
        and register.get("callback_target")
        and register.get("callback_target") == unregister.get("callback_target")
    ):
        return "callback-specific"
    if (
        unregister["binding_api"] == "RemoveAll"
        and register_arguments
        and unregister_arguments
        and register_arguments[0] == unregister_arguments[0]
    ):
        return "object-wide"
    if unregister["binding_api"] in {"Unbind", "Clear"}:
        return "source-wide"
    return "same-source-candidate"


def _delegate_operations(
    methods: dict[str, dict[str, Any]],
    reachable: dict[str, set[str]],
    class_name: str,
) -> list[dict[str, Any]]:
    method_names = set(methods)
    preliminary: list[
        tuple[str, dict[str, Any], str, str, str | None, str | None]
    ] = []
    known_sources: set[str] = set()
    for method_name in sorted(reachable):
        for operation in methods[method_name]["operations"]:
            if operation.get("kind") != "invocation":
                continue
            callee = str(operation.get("callee", ""))
            api = _method_name_from_callee(callee)
            if _self_method_name(callee, class_name) in method_names:
                continue
            action = _delegate_action(api)
            if action is None:
                continue
            source = _delegate_source(callee, api)
            callback = _callback_target(operation, class_name, method_names)
            if action == "register" and (callback or _source_looks_like_delegate(source)):
                known_sources.add(source)
            preliminary.append(
                (
                    method_name,
                    operation,
                    action,
                    source,
                    callback,
                    _assigned_target(methods[method_name], operation),
                )
            )

    results: list[dict[str, Any]] = []
    for method_name, operation, action, source, callback, result_target in preliminary:
        api = _method_name_from_callee(str(operation["callee"]))
        if not _looks_like_delegate(source, api, callback, known_sources):
            continue
        results.append(
            {
                "action": action,
                "delegate_source": source,
                "binding_api": api,
                "callback_target": callback,
                "result_target": result_target,
                "method": method_name,
                "roots": sorted(reachable[method_name]),
                "expression": operation["expression"],
                "conditions": operation["conditions"],
                "location": operation["location"],
                "_argument_expressions": [
                    str(argument.get("expression", ""))
                    for argument in operation.get("arguments", [])
                ],
            }
        )
    handle_counts: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for operation in results:
        if operation["action"] == "register" and operation["result_target"]:
            handle_counts[
                (operation["delegate_source"], operation["result_target"])
            ][0] += 1
        elif operation["action"] == "unregister" and operation[
            "_argument_expressions"
        ]:
            handle_counts[
                (
                    operation["delegate_source"],
                    operation["_argument_expressions"][0],
                )
            ][1] += 1
    frozen_handle_counts = {
        key: (counts[0], counts[1]) for key, counts in handle_counts.items()
    }

    for index, item in enumerate(results):
        item["related_operations"] = [
            {
                "action": other["action"],
                "binding_api": other["binding_api"],
                "relationship": _delegate_relationship(
                    item,
                    other,
                    frozen_handle_counts,
                ),
                "location": other["location"],
            }
            for other_index, other in enumerate(results)
            if other_index != index
            and other["delegate_source"] == item["delegate_source"]
            and other["action"] != item["action"]
        ]
    for item in results:
        item.pop("_argument_expressions", None)
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
    if not rules.is_file():
        raise ValueError(f"Module Build.cs is not a file: {rules}")
    if not rules.name.casefold().endswith(".build.cs"):
        raise ValueError(f"Expected a Module Build.cs file: {rules}")
    module_name = rules.name[: -len(".Build.cs")]
    if not module_name:
        raise ValueError(f"Module Build.cs filename has no module name: {rules}")
    module_root = rules.parent
    module_files = source_files(module_root)
    parsed_files = [parse_cpp_file(path) for path in module_files]
    relative_paths = {
        parsed["path"]: _relative_path(parsed["path"], module_root)
        for parsed in parsed_files
    }
    registrations = [
        {
            **macro,
            "location": _with_path(macro["location"], relative_paths[parsed["path"]]),
        }
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
        relative_path = relative_paths[parsed["path"]]
        for class_item in parsed["classes"]:
            part = class_parts.setdefault(
                class_item["name"],
                {"base_types": set(), "declarations": [], "method_parts": []},
            )
            part["base_types"].update(class_item["base_types"])
            part["declarations"].append(_with_path(class_item["location"], relative_path))
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
                        operation["location"] = _with_path(operation["location"], relative_path)
                part["method_parts"].append(
                    {
                        "name": member["name"],
                        "parameters": member["parameters"],
                        "signature": member["signature"],
                        "declaration": _with_path(member["location"], relative_path),
                        "definition": _with_path(member["location"], relative_path) if member["has_body"] else None,
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
                operation["location"] = _with_path(operation["location"], relative_path)
            part["method_parts"].append(
                {
                    "name": definition["name"],
                    "parameters": definition["parameters"],
                    "signature": definition["signature"],
                    "declaration": None,
                    "definition": _with_path(definition["location"], relative_path),
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
    module_class_names = sorted(
        macro_class_names if matching_registrations else inferred_class_names
    )
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
        ambiguous_methods = {
            name
            for name, method in methods.items()
            if len(method["parameters"]) > 1 or len(method["definitions"]) > 1
        }
        unresolved_overload_uses: dict[str, list[dict[str, Any]]] = defaultdict(list)
        graph: dict[str, set[str]] = defaultdict(set)
        for method_name, method in methods.items():
            for operation in method["operations"]:
                if operation.get("kind") != "invocation":
                    continue
                callee_expression = str(operation.get("callee", ""))
                callee = _self_method_name(callee_expression, class_name)
                if callee not in methods or callee == method_name:
                    continue
                if callee in ambiguous_methods:
                    unresolved_overload_uses[callee].append(
                        {
                            "kind": "call",
                            "caller": method_name,
                            "expression": operation["expression"],
                            "location": operation["location"],
                        }
                    )
                    continue
                graph[method_name].add(callee)
        lifecycle_roots: list[str] = []
        for name in ("StartupModule", "ShutdownModule"):
            if name not in methods:
                continue
            if name in ambiguous_methods:
                unresolved_overload_uses[name].append({"kind": "lifecycle-root"})
                continue
            lifecycle_roots.append(name)
        reachable = _reachable(graph, lifecycle_roots)
        followed_callbacks: set[str] = set()
        while True:
            delegate_operations = _delegate_operations(methods, reachable, class_name)
            callback_methods: set[str] = set()
            for item in delegate_operations:
                if item["action"] != "register":
                    continue
                callback = _local_callback_method(
                    item.get("callback_target"),
                    class_name,
                    set(methods),
                )
                if callback is None or callback in followed_callbacks:
                    continue
                if callback in ambiguous_methods:
                    unresolved_overload_uses[callback].append(
                        {
                            "kind": "bound-callback",
                            "expression": item["expression"],
                            "location": item["location"],
                        }
                    )
                    followed_callbacks.add(callback)
                    continue
                callback_methods.add(callback)
            if not callback_methods:
                break
            followed_callbacks.update(callback_methods)
            callback_reachable = _reachable(
                graph,
                sorted(callback_methods),
                "bound-callback",
            )
            for method_name, roots in callback_reachable.items():
                reachable[method_name].update(roots)
        delegate_operations = _delegate_operations(methods, reachable, class_name)
        if unresolved_overload_uses:
            problems.append(
                {
                    "severity": "warning",
                    "code": "module-method-overload-unresolved",
                    "module_class": class_name,
                    "methods": [
                        {
                            "method": name,
                            "parameters": methods[name]["parameters"],
                            "signatures": methods[name]["signatures"],
                            "uses": uses,
                        }
                        for name, uses in sorted(unresolved_overload_uses.items())
                    ],
                    "message": "Overloaded module methods were not followed because their call targets could not be resolved statically",
                }
            )
        output_classes.append(
            {
                "name": class_name,
                "base_types": sorted(part["base_types"]),
                "declarations": part["declarations"],
                "methods": [methods[name] for name in sorted(methods)],
                "lifecycle": {
                    "roots": lifecycle_roots,
                    "reachability": [
                        {"method": name, "roots": sorted(roots)}
                        for name, roots in sorted(reachable.items())
                    ],
                },
                "same_class_calls": [
                    {"caller": caller, "callee": callee}
                    for caller in sorted(graph)
                    for callee in sorted(graph[caller])
                ],
                "delegate_operations": delegate_operations,
            }
        )

    return result_document(
        "ue-itps.module-entry-source.v6",
        {
            "module_name": module_name,
            "build_rules_path": _relative_path(rules, module_root),
            "module_root": normalized(module_root),
            "source_files": [_relative_path(path, module_root) for path in module_files],
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
