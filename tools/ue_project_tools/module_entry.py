from __future__ import annotations

from collections import defaultdict, deque
import json
from pathlib import Path
import re
from typing import Any, Iterable

from .common import normalized, result_document
from .source_parser import lex_source, parse_cpp_file, parse_operations, source_files


_DELEGATE_BIND_APIS = frozenset(
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
    }
)
_DELEGATE_UNBIND_APIS = frozenset(
    {"Clear", "Remove", "RemoveAll", "RemoveDynamic", "Unbind"}
)
_STARTUP_CALLBACK_APIS = frozenset(
    {"RegisterStartupCallback", "UnRegisterStartupCallback", "UnregisterStartupCallback"}
)
_CALLBACK_FACTORY_APIS = frozenset(
    {
        "CreateLambda",
        "CreateRaw",
        "CreateSP",
        "CreateStatic",
        "CreateThreadSafeSP",
        "CreateUObject",
        "CreateWeakLambda",
    }
)
_LAMBDA_BIND_APIS = frozenset(
    {"AddLambda", "AddWeakLambda", "BindLambda", "BindWeakLambda"}
)
_UFUNCTION_BIND_APIS = frozenset({"AddUFunction", "BindUFunction"})
_MAX_CONTEXTS_PER_CALLABLE = 32


def _with_path(location: dict[str, Any], path: str) -> dict[str, Any]:
    return {"path": path, **location}


def _source_evidence(location: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(location["path"]),
        "line": int(location["line"]),
    }


def _relative_path(path: str | Path, root: Path) -> str:
    return Path(path).resolve().relative_to(root).as_posix()


def _registrations_mutually_exclusive(
    left: dict[str, Any], right: dict[str, Any]
) -> bool:
    left_arms = {
        int(condition["group_line"]): int(condition["arm"])
        for condition in left.get("preprocessor_conditions", [])
    }
    return any(
        int(condition["group_line"]) in left_arms
        and left_arms[int(condition["group_line"])] != int(condition["arm"])
        for condition in right.get("preprocessor_conditions", [])
    )


def _registrations_are_conditional_variants(
    registrations: list[dict[str, Any]],
) -> bool:
    return len(registrations) > 1 and all(
        _registrations_mutually_exclusive(left, right)
        for index, left in enumerate(registrations)
        for right in registrations[index + 1 :]
    )


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


def _callback_target(
    operation: dict[str, Any],
    class_name: str,
    method_names: set[str],
) -> str | None:
    expressions = [
        str(argument.get("expression", ""))
        for argument in operation.get("arguments", [])
    ]
    api = _method_name_from_callee(str(operation.get("callee", "")))
    if api in _UFUNCTION_BIND_APIS:
        arguments = operation.get("arguments", [])
        if len(arguments) > 1:
            target_argument = arguments[1]
            literal_values = target_argument.get("evaluation", {}).get(
                "literal_values", []
            )
            if len(literal_values) == 1:
                return str(literal_values[0])
            expression = str(target_argument.get("expression", "")).strip()
            return expression or "<unresolved>"
        return "<unresolved>"
    if any(re.search(r"\[[^\]]*\].*\{", expression) for expression in expressions):
        return "<lambda>"
    for expression in expressions:
        match = re.search(
            r"&\s*(?:(?P<class>[A-Za-z_]\w*)\s*::\s*)?(?P<method>[A-Za-z_]\w*)",
            expression,
        )
        if not match:
            continue
        owner = match.group("class")
        method = match.group("method")
        if owner == "ThisClass":
            owner = class_name
        if owner:
            return f"{owner}::{method}"
        return f"{class_name}::{method}" if method in method_names else method
    return None


def _callback_kind(operation: dict[str, Any], target: str | None) -> str | None:
    api = _method_name_from_callee(str(operation.get("callee", "")))
    if api in _UFUNCTION_BIND_APIS:
        return "ufunction"
    if target == "<lambda>":
        return "lambda"
    if _callback_reference(operation):
        return "function"
    return None


def _condition_expression(condition: dict[str, Any]) -> str | None:
    expression = str(condition.get("expression", "")).strip()
    if not expression:
        return None
    branch = str(condition.get("branch", "then"))
    if branch == "else":
        return f"!({expression})"
    if branch not in {"then", "body"}:
        return f"{branch}: {expression}"
    return expression


def _operation_guard(operation: dict[str, Any]) -> tuple[str, ...]:
    values = [
        expression
        for condition in operation.get("conditions", [])
        if (expression := _condition_expression(condition))
    ]
    values.extend(
        str(control["guard"])
        for control in operation.get("control_details", [])
        if str(control.get("guard", "")).strip()
    )
    return tuple(dict.fromkeys(values))


def _combine_guards(*groups: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for group in groups for value in group))


def _minimize_guards(guards: Iterable[tuple[str, ...]]) -> list[tuple[str, ...]]:
    unique = sorted(set(guards), key=lambda item: (len(item), item))
    result: list[tuple[str, ...]] = []
    for guard in unique:
        guard_set = set(guard)
        if any(set(existing).issubset(guard_set) for existing in result):
            continue
        result.append(guard)
    return result


def _when_value(guards: Iterable[tuple[str, ...]]) -> list[list[str]]:
    minimized = _minimize_guards(guards)
    if any(not guard for guard in minimized):
        return []
    return [list(guard) for guard in minimized]


def _identifier_names(expression: str) -> set[str]:
    return set(re.findall(r"\b[A-Za-z_]\w*\b", expression))


def _returned_names(
    tokens: list[Any],
    body_range: tuple[int, int],
) -> set[str]:
    start, end = body_range
    names: set[str] = set()
    for index in range(start, end - 1):
        if tokens[index].value != "return":
            continue
        cursor = index + 1
        while cursor < end and tokens[cursor].value != ";":
            if tokens[cursor].kind == "identifier":
                names.add(tokens[cursor].value)
            cursor += 1
    return names


def _reference_parameter_names(parameters: str) -> set[str]:
    names: set[str] = set()
    for parameter in parameters.split(","):
        if "&" not in parameter:
            continue
        identifiers = re.findall(r"\b[A-Za-z_]\w*\b", parameter)
        if identifiers:
            names.add(identifiers[-1])
    return names


def _parameter_token_groups(parameters: str) -> list[list[str]]:
    tokens = lex_source(parameters)
    groups: list[list[str]] = []
    current: list[str] = []
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    angle_depth = 0
    in_default = False

    for token in tokens:
        value = token.value
        if value == "," and not any(
            (paren_depth, bracket_depth, brace_depth, angle_depth)
        ):
            groups.append(current)
            current = []
            in_default = False
            continue
        if value == "=" and not any(
            (paren_depth, bracket_depth, brace_depth, angle_depth)
        ):
            in_default = True
            continue

        if not in_default:
            current.append(value)
        if value == "(":
            paren_depth += 1
        elif value == ")":
            paren_depth = max(0, paren_depth - 1)
        elif value == "[":
            bracket_depth += 1
        elif value == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif value == "{":
            brace_depth += 1
        elif value == "}":
            brace_depth = max(0, brace_depth - 1)
        elif value == "<" and not in_default:
            angle_depth += 1
        elif value == ">" and not in_default:
            angle_depth = max(0, angle_depth - 1)
        elif value == ">>" and not in_default:
            angle_depth = max(0, angle_depth - 2)

    if current or tokens:
        groups.append(current)
    return groups


def _without_parameter_name(tokens: list[str]) -> tuple[str, ...]:
    if not tokens or tokens == ["void"]:
        return tuple(tokens)

    for index in range(1, len(tokens) - 1):
        if (
            re.match(r"^[A-Za-z_]\w*$", tokens[index])
            and tokens[index - 1] in {"*", "&", "&&"}
            and tokens[index + 1] == ")"
        ):
            return tuple(tokens[:index] + tokens[index + 1 :])

    for index in range(1, len(tokens) - 1):
        if (
            re.match(r"^[A-Za-z_]\w*$", tokens[index])
            and tokens[index + 1] == "["
        ):
            return tuple(tokens[:index] + tokens[index + 1 :])

    if not re.match(r"^[A-Za-z_]\w*$", tokens[-1]):
        return tuple(tokens)
    if len(tokens) > 1 and tokens[-2] == "::":
        return tuple(tokens)

    non_type_prefixes = {"class", "const", "enum", "struct", "typename", "volatile"}
    has_type_prefix = any(
        re.match(r"^[A-Za-z_]\w*$", value) and value not in non_type_prefixes
        for value in tokens[:-1]
    ) or any(value in {"*", "&", "&&", ">", ">>", "]", ")"} for value in tokens[:-1])
    return tuple(tokens[:-1]) if has_type_prefix else tuple(tokens)


def _parameter_signature(parameters: str) -> tuple[tuple[str, ...], ...]:
    signature = tuple(
        _without_parameter_name(group)
        for group in _parameter_token_groups(parameters)
    )
    return () if signature == (("void",),) else signature


def _observable_names(callable_item: dict[str, Any]) -> set[str]:
    operations = callable_item["operations"]
    local_names = {
        str(operation["declared_name"])
        for operation in operations
        if operation.get("declared_name")
    }
    observable = set(callable_item["returned_names"])
    observable.update(callable_item["reference_parameters"])
    changed = True
    while changed:
        changed = False
        for operation in operations:
            if operation.get("kind") != "assignment":
                continue
            target = str(operation.get("target", ""))
            target_root = re.split(r"\.|->|::", target, maxsplit=1)[0]
            if target_root not in observable:
                continue
            dependencies = _identifier_names(str(operation.get("value_expression", "")))
            for dependency in dependencies.intersection(local_names):
                if dependency not in observable:
                    observable.add(dependency)
                    changed = True
    return observable


def _parse_callable_body(
    parsed: dict[str, Any],
    body_range: tuple[int, int],
    relative_path: str,
) -> tuple[list[dict[str, Any]], set[str]]:
    operations = parse_operations(
        parsed["text"],
        parsed["tokens"],
        parsed["forward"],
        parsed["reverse"],
        body_range[0],
        body_range[1],
        include_control_metadata=True,
    )
    for operation in operations:
        operation["location"] = _with_path(operation["location"], relative_path)
    return operations, _returned_names(parsed["tokens"], body_range)


def _callable_declaration(
    signature: str,
    location: dict[str, Any],
    relative_path: str,
    *,
    priority: int,
    owner: str | None = None,
) -> dict[str, Any]:
    normalized_signature = " ".join(signature.split())
    normalized_signature = re.sub(
        r"^(?:(?:public|protected|private)\s*:\s*)+",
        "",
        normalized_signature,
    )
    if owner:
        normalized_signature = normalized_signature.replace(f"{owner}::", "", 1)
    return {
        "declaration": normalized_signature.rstrip(";") + ";",
        "evidence": {
            "path": relative_path,
            "line": int(location["line"]),
        },
        "priority": priority,
        "is_static": bool(re.match(r"^static\b", normalized_signature)),
        "is_virtual": bool(
            re.match(r"^virtual\b", normalized_signature)
            or re.search(r"\b(?:override|final)\b", normalized_signature)
        ),
    }


def _build_callables(
    parsed_files: list[dict[str, Any]],
    relative_paths: dict[str, str],
    class_name: str,
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    parts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for parsed in parsed_files:
        relative_path = relative_paths[parsed["path"]]
        for class_item in parsed["classes"]:
            if class_item["name"] != class_name:
                continue
            for member in class_item["members"]:
                operations: list[dict[str, Any]] = []
                returned: set[str] = set()
                if member["body_range"]:
                    operations, returned = _parse_callable_body(
                        parsed, member["body_range"], relative_path
                    )
                parts[f"method:{member['name']}"].append(
                    {
                        "kind": "method",
                        "name": member["name"],
                        "parameters": member["parameters"],
                        "definition": bool(member["has_body"]),
                        "operations": operations,
                        "returned_names": returned,
                        "declaration": _callable_declaration(
                            str(member["signature"]),
                            member["location"],
                            relative_path,
                            priority=0,
                        ),
                    }
                )
        for definition in parsed["external_definitions"]:
            if definition["class_name"] != class_name:
                continue
            operations, returned = _parse_callable_body(
                parsed, definition["body_range"], relative_path
            )
            parts[f"method:{definition['name']}"].append(
                {
                    "kind": "method",
                    "name": definition["name"],
                    "parameters": definition["parameters"],
                    "definition": True,
                    "operations": operations,
                    "returned_names": returned,
                    "declaration": _callable_declaration(
                        str(definition["signature"]),
                        definition["location"],
                        relative_path,
                        priority=1,
                        owner=class_name,
                    ),
                }
            )
        for function in parsed.get("free_functions", []):
            operations, returned = _parse_callable_body(
                parsed, function["body_range"], relative_path
            )
            declaration = _callable_declaration(
                str(function["signature"]),
                function["location"],
                relative_path,
                priority=0,
            )
            parts[f"free:{function['name']}"].append(
                {
                    "kind": "free",
                    "name": function["name"],
                    "parameters": function["parameters"],
                    "definition": True,
                    "operations": operations,
                    "returned_names": returned,
                    "declaration": declaration,
                }
            )

    callables: dict[str, dict[str, Any]] = {}
    ambiguous: set[str] = set()
    for key, items in sorted(parts.items()):
        parameters = {str(item["parameters"]) for item in items}
        parameter_signatures = {
            _parameter_signature(str(item["parameters"])) for item in items
        }
        definitions = sum(1 for item in items if item["definition"])
        if len(parameter_signatures) > 1 or definitions > 1:
            ambiguous.add(key)
        merged = {
            "key": key,
            "kind": items[0]["kind"],
            "name": items[0]["name"],
            "parameters": sorted(parameters),
            "operations": [
                operation
                for item in items
                for operation in item["operations"]
            ],
            "returned_names": set().union(
                *(item["returned_names"] for item in items)
            ),
            "reference_parameters": set().union(
                *(
                    _reference_parameter_names(str(item["parameters"]))
                    for item in items
                )
            ),
            "declarations": sorted(
                (item["declaration"] for item in items),
                key=lambda declaration: (
                    declaration["priority"],
                    declaration["evidence"]["path"],
                    declaration["evidence"]["line"],
                    declaration["declaration"],
                ),
            ),
        }
        merged["static_declarations"] = [
            declaration
            for declaration in merged["declarations"]
            if declaration["is_static"]
        ]
        merged["is_virtual"] = any(
            declaration["is_virtual"] for declaration in merged["declarations"]
        )
        merged["operations"].sort(
            key=lambda operation: (
                operation["location"]["path"],
                operation["location"]["line"],
            )
        )
        merged["observable_names"] = _observable_names(merged)
        callables[key] = merged
    return callables, ambiguous


def _resolve_invocation(
    operation: dict[str, Any],
    current: dict[str, Any],
    callables: dict[str, dict[str, Any]],
    class_name: str,
) -> str | None:
    callee = str(operation.get("callee", ""))
    method = _self_method_name(callee, class_name)
    method_key = f"method:{method}" if method else None
    receiver, bare_name = _callee_parts(callee)
    free_key = f"free:{bare_name}"
    if current["kind"] == "method" and method_key in callables:
        return method_key
    if receiver is None and free_key in callables:
        return free_key
    if method_key in callables and receiver in {"this", "ThisClass", class_name}:
        return method_key
    return None


def _resolve_callback(
    callback: str | None,
    callables: dict[str, dict[str, Any]],
    class_name: str,
) -> str | None:
    if not callback or callback == "<lambda>":
        return None
    if "::" in callback:
        owner, name = callback.rsplit("::", 1)
        key = f"method:{name}"
        return key if owner == class_name and key in callables else None
    free_key = f"free:{callback}"
    if free_key in callables:
        return free_key
    method_key = f"method:{callback}"
    return method_key if method_key in callables else None


def _looks_like_delegate(
    source: str,
    api: str,
    callback: str | None,
    known_sources: set[str],
) -> bool:
    if source in known_sources or callback:
        return True
    if api in {"Bind", "Unbind", "Clear"}:
        return True
    last = _callee_parts(source)[1]
    return "Delegate" in source or "Callback" in source or bool(
        re.match(r"On[A-Z_]", last)
    )


def _known_delegate_sources(
    callables: dict[str, dict[str, Any]],
    class_name: str,
) -> set[str]:
    method_names = {
        item["name"] for item in callables.values() if item["kind"] == "method"
    }
    sources: set[str] = set()
    for callable_item in callables.values():
        for operation in callable_item["operations"]:
            if operation.get("kind") != "invocation":
                continue
            callee = str(operation.get("callee", ""))
            api = _method_name_from_callee(callee)
            if api not in _DELEGATE_BIND_APIS:
                continue
            callback = _callback_target(operation, class_name, method_names)
            if callback:
                sources.add(_delegate_source(callee, api))
    return sources


def _build_contexts(
    callables: dict[str, dict[str, Any]],
    ambiguous: set[str],
    class_name: str,
    problems: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    contexts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[Any, ...]] = set()
    queue: deque[
        tuple[
            str,
            dict[str, str],
            tuple[str, ...],
            tuple[str, ...],
            tuple[tuple[str, int], ...],
            dict[str, Any] | None,
        ]
    ] = deque()
    truncated: set[str] = set()
    unresolved_ambiguous: set[str] = set()
    known_sources = _known_delegate_sources(callables, class_name)
    method_names = {
        item["name"] for item in callables.values() if item["kind"] == "method"
    }

    def enqueue(
        key: str,
        trigger: dict[str, str],
        via: tuple[str, ...],
        guard: tuple[str, ...],
        route: tuple[tuple[str, int], ...],
        virtual_target: dict[str, Any] | None,
    ) -> None:
        if key in ambiguous:
            unresolved_ambiguous.add(key)
            return
        target_key = (
            None
            if virtual_target is None
            else (
                virtual_target["name"],
                virtual_target["path"],
                virtual_target["line"],
            )
        )
        signature = (
            key,
            trigger["kind"],
            trigger["name"],
            via,
            guard,
            route,
            target_key,
        )
        if signature in seen:
            return
        if len(contexts[key]) >= _MAX_CONTEXTS_PER_CALLABLE:
            truncated.add(key)
            return
        seen.add(signature)
        context = {
            "trigger": trigger,
            "via": via,
            "guard": guard,
            "route": route,
            "virtual_target": virtual_target,
        }
        contexts[key].append(context)
        queue.append((key, trigger, via, guard, route, virtual_target))

    for root in ("StartupModule", "ShutdownModule"):
        key = f"method:{root}"
        if key in callables:
            enqueue(
                key,
                {"kind": "lifecycle", "name": root},
                (root,),
                (),
                (),
                None,
            )

    while queue:
        key, trigger, via, guard, route, virtual_target = queue.popleft()
        callable_item = callables[key]
        for operation in callable_item["operations"]:
            if operation.get("kind") != "invocation":
                continue
            local_guard = _operation_guard(operation)
            effective_guard = _combine_guards(guard, local_guard)
            callee_key = _resolve_invocation(
                operation, callable_item, callables, class_name
            )
            if callee_key:
                call_site = (
                    str(operation["location"]["path"]),
                    int(operation["location"]["line"]),
                )
                next_virtual_target = virtual_target
                if next_virtual_target is None and callable_item["is_virtual"]:
                    next_virtual_target = {
                        "name": callable_item["name"],
                        "path": call_site[0],
                        "line": call_site[1],
                    }
                enqueue(
                    callee_key,
                    trigger,
                    (*via, callables[callee_key]["name"]),
                    effective_guard,
                    (*route, call_site),
                    next_virtual_target,
                )
                continue

            callee = str(operation.get("callee", ""))
            api = _method_name_from_callee(callee)
            if api not in _DELEGATE_BIND_APIS and api != "RegisterStartupCallback":
                continue
            source = _delegate_source(callee, api)
            callback = _callback_target(operation, class_name, method_names)
            if api in _DELEGATE_BIND_APIS and not _looks_like_delegate(
                source, api, callback, known_sources
            ):
                continue
            callback_key = (
                _resolve_callback(callback, callables, class_name)
                if _callback_kind(operation, callback) == "function"
                else None
            )
            if callback_key:
                callback_name = callables[callback_key]["name"]
                if (
                    callback_key not in ambiguous
                    and callables[callback_key]["kind"] == "free"
                    and callables[callback_key]["static_declarations"]
                ):
                    continue
                enqueue(
                    callback_key,
                    {"kind": "callback", "name": callback_name},
                    (callback_name,),
                    effective_guard,
                    (
                        (
                            str(operation["location"]["path"]),
                            int(operation["location"]["line"]),
                        ),
                    ),
                    None,
                )

    if unresolved_ambiguous:
        problems.append(
            {
                "severity": "warning",
                "code": "module-call-target-overload-unresolved",
                "callables": [
                    callables[key]["name"] for key in sorted(unresolved_ambiguous)
                ],
                "message": "Overloaded local call targets were not followed.",
            }
        )
    if truncated:
        problems.append(
            {
                "severity": "warning",
                "code": "condition-path-truncated",
                "callables": [callables[key]["name"] for key in sorted(truncated)],
                "limit": _MAX_CONTEXTS_PER_CALLABLE,
                "message": "Some callable condition paths exceeded the deterministic limit.",
            }
        )
    return contexts


def _callback_reference(operation: dict[str, Any]) -> str | None:
    for argument in operation.get("arguments", []):
        expression = str(argument.get("expression", ""))
        match = re.search(
            r"&\s*(?:(?P<class>[A-Za-z_]\w*)\s*::\s*)?(?P<method>[A-Za-z_]\w*)",
            expression,
        )
        if not match:
            continue
        owner = match.group("class")
        method = match.group("method")
        return f"&{owner}::{method}" if owner else f"&{method}"
    return None


def _callback_factory_api(operation: dict[str, Any]) -> str | None:
    for argument in operation.get("arguments", []):
        expression = str(argument.get("expression", ""))
        for api in sorted(_CALLBACK_FACTORY_APIS):
            if re.search(rf"(?:\.|::|->){re.escape(api)}\s*\(", expression):
                return api
    return None


def _normalized_expression(expression: str) -> str:
    return "".join(expression.split())


def _first_argument(operation: dict[str, Any]) -> str | None:
    arguments = operation.get("arguments", [])
    if not arguments:
        return None
    expression = str(arguments[0].get("expression", "")).strip()
    return expression or None


def _binding_owner(
    operation: dict[str, Any], callback_kind: str, reference: str | None
) -> str | None:
    api = _method_name_from_callee(str(operation.get("callee", "")))
    if callback_kind == "ufunction" or api in {
        "AddWeakLambda",
        "BindWeakLambda",
        "CreateWeakLambda",
    }:
        return _first_argument(operation)
    if callback_kind == "lambda":
        return None
    if not reference:
        return None
    for index, argument in enumerate(operation.get("arguments", [])):
        if _normalized_expression(reference) not in _normalized_expression(
            str(argument.get("expression", ""))
        ):
            continue
        if index == 0:
            return None
        owner = str(operation["arguments"][0].get("expression", "")).strip()
        return owner or None
    return None


def _assigned_handle(
    callable_item: dict[str, Any],
    operation: dict[str, Any],
) -> str | None:
    call_expression = str(operation.get("expression", ""))
    if not call_expression:
        return None
    line = int(operation["location"]["line"])
    for candidate in callable_item["operations"]:
        if candidate.get("kind") != "assignment":
            continue
        candidate_start = int(candidate["location"]["line"])
        candidate_end = int(candidate["location"].get("end_line", candidate_start))
        if not candidate_start <= line <= candidate_end:
            continue
        if call_expression not in str(candidate.get("value_expression", "")):
            continue
        target = str(candidate.get("target", "")).strip()
        return target or None
    return None


def _callback_source(callee: str, api: str) -> str:
    receiver, _ = _callee_parts(callee)
    if api in _STARTUP_CALLBACK_APIS:
        return f"{receiver or callee} startup callback"
    return _delegate_source(callee, api)


def _callback_description(
    operation: dict[str, Any],
    callables: dict[str, dict[str, Any]],
    ambiguous: set[str],
    class_name: str,
) -> dict[str, Any]:
    reference = _callback_reference(operation)
    method_names = {
        item["name"] for item in callables.values() if item["kind"] == "method"
    }
    target = _callback_target(operation, class_name, method_names)
    kind = _callback_kind(operation, target)
    callback_key = (
        _resolve_callback(target, callables, class_name)
        if kind == "function"
        else None
    )
    callback: dict[str, Any] = {
        "kind": kind or "function",
        "target": target or (reference[1:] if reference else "<unresolved>"),
    }
    if callback_key and callback_key not in ambiguous:
        declaration = callables[callback_key]["declarations"][0]
        declaration_text = str(declaration["declaration"])
        if target and "::" in target:
            owner, name = target.rsplit("::", 1)
            declaration_text = re.sub(
                rf"\b{re.escape(name)}\s*\(",
                f"{owner}::{name}(",
                declaration_text,
                count=1,
            )
        callback["declaration"] = declaration_text
        callback["evidence"] = declaration["evidence"]
    elif kind == "function":
        callback["declaration"] = callback["target"]
    else:
        callback["evidence"] = _source_evidence(operation["location"])
    return callback


def _cleanup_applies(binding: dict[str, Any], cleanup: dict[str, Any]) -> bool:
    if binding["source"] != cleanup["source"]:
        return False
    api = cleanup["api"]
    if api in {"Unbind", "Clear"}:
        return True
    if api == "RemoveAll":
        return bool(
            binding.get("owner")
            and cleanup.get("argument")
            and _normalized_expression(str(binding["owner"]))
            == _normalized_expression(str(cleanup["argument"]))
        )
    if api == "RemoveDynamic":
        if binding.get("callback_target") != cleanup.get("callback_target"):
            return False
        cleanup_owner = cleanup.get("argument")
        return not binding.get("owner") or (
            cleanup_owner
            and _normalized_expression(str(binding["owner"]))
            == _normalized_expression(str(cleanup_owner))
        )
    if api == "Remove":
        return bool(
            binding.get("handle")
            and cleanup.get("argument")
            and _normalized_expression(str(binding["handle"]))
            == _normalized_expression(str(cleanup["argument"]))
        )
    if api in {"UnRegisterStartupCallback", "UnregisterStartupCallback"}:
        return bool(
            binding.get("handle")
            and cleanup.get("argument")
            and _normalized_expression(str(binding["handle"]))
            == _normalized_expression(str(cleanup["argument"]))
        )
    return False


def _public_virtual_targets(
    targets: list[dict[str, Any]],
    base_path: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for target in targets:
        item: dict[str, Any] = {"name": target["name"]}
        if str(target["path"]) != base_path:
            item["path"] = target["path"]
        item["line"] = int(target["line"])
        results.append(item)
    return results


def _public_cleanup(cleanup: dict[str, Any], base_path: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "api": cleanup["api"],
        "in": cleanup["in"],
        "when": _when_value(cleanup["guards"]),
    }
    if not cleanup["in_is_virtual"]:
        result["virtual_targets"] = _public_virtual_targets(
            cleanup["virtual_targets"], base_path
        )
    if str(cleanup["evidence"]["path"]) != base_path:
        result["path"] = cleanup["evidence"]["path"]
    result["line"] = int(cleanup["evidence"]["line"])
    return result


def _callback_bindings(
    callables: dict[str, dict[str, Any]],
    contexts: dict[str, list[dict[str, Any]]],
    ambiguous: set[str],
    class_name: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    method_names = {
        item["name"] for item in callables.values() if item["kind"] == "method"
    }
    outer_binding_ranges: list[tuple[str, str, int, int, str, str]] = []
    for key in contexts:
        for operation in callables[key]["operations"]:
            if operation.get("kind") != "invocation":
                continue
            api = _method_name_from_callee(str(operation.get("callee", "")))
            if api in _DELEGATE_BIND_APIS or api == "RegisterStartupCallback":
                target = _callback_target(operation, class_name, method_names)
                kind = _callback_kind(operation, target)
                if not kind:
                    continue
                outer_binding_ranges.append(
                    (
                        key,
                        str(operation["location"]["path"]),
                        int(operation["location"]["line"]),
                        int(
                            operation["location"].get(
                                "end_line", operation["location"]["line"]
                            )
                        ),
                        kind,
                        target or "<unresolved>",
                    )
                )

    binding_groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    cleanup_groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for key, callable_contexts in contexts.items():
        callable_item = callables[key]
        for operation in callable_item["operations"]:
            if operation.get("kind") != "invocation":
                continue
            callee = str(operation.get("callee", ""))
            api = _method_name_from_callee(callee)
            reference = _callback_reference(operation)
            callback_target = _callback_target(operation, class_name, method_names)
            callback_kind = _callback_kind(operation, callback_target)
            is_binding = bool(
                callback_kind
                and (
                    api in _DELEGATE_BIND_APIS
                    or api == "RegisterStartupCallback"
                    or api in _CALLBACK_FACTORY_APIS
                )
            )
            if is_binding and api in _CALLBACK_FACTORY_APIS:
                operation_line = int(operation["location"]["line"])
                if any(
                    outer_key == key
                    and outer_path == str(operation["location"]["path"])
                    and start_line <= operation_line <= end_line
                    and outer_kind == callback_kind
                    and outer_target == (callback_target or "<unresolved>")
                    for (
                        outer_key,
                        outer_path,
                        start_line,
                        end_line,
                        outer_kind,
                        outer_target,
                    ) in outer_binding_ranges
                ):
                    continue
            if is_binding:
                callback = _callback_description(
                    operation, callables, ambiguous, class_name
                )
                source = _callback_source(callee, api)
                group_key = (
                    source,
                    callback["kind"],
                    callback["target"],
                    api,
                    callable_item["name"],
                    operation["location"]["path"],
                    int(operation["location"]["line"]),
                )
                group = binding_groups.setdefault(
                    group_key,
                    {
                        "source": source,
                        "callback": callback,
                        "callback_target": callback["target"],
                        "api": api,
                        "factory_api": _callback_factory_api(operation),
                        "in": callable_item["name"],
                        "in_is_virtual": callable_item["is_virtual"],
                        "evidence": _source_evidence(operation["location"]),
                        "owner": _binding_owner(
                            operation, str(callback["kind"]), reference
                        ),
                        "handle": _assigned_handle(callable_item, operation),
                        "guards": [],
                        "virtual_targets": [],
                    },
                )
                for context in callable_contexts:
                    group["guards"].append(
                        _combine_guards(context["guard"], _operation_guard(operation))
                    )
                    if context["virtual_target"] is not None:
                        group["virtual_targets"].append(context["virtual_target"])
                continue

            if api not in _DELEGATE_UNBIND_APIS and api not in {
                "UnRegisterStartupCallback",
                "UnregisterStartupCallback",
            }:
                continue
            source = _callback_source(callee, api)
            group_key = (
                source,
                callback_target,
                api,
                callable_item["name"],
                operation["location"]["path"],
                int(operation["location"]["line"]),
            )
            group = cleanup_groups.setdefault(
                group_key,
                {
                    "source": source,
                    "callback_target": callback_target,
                    "api": api,
                    "in": callable_item["name"],
                    "in_is_virtual": callable_item["is_virtual"],
                    "evidence": _source_evidence(operation["location"]),
                    "argument": _first_argument(operation),
                    "guards": [],
                    "virtual_targets": [],
                },
            )
            for context in callable_contexts:
                group["guards"].append(
                    _combine_guards(context["guard"], _operation_guard(operation))
                )
                if context["virtual_target"] is not None:
                    group["virtual_targets"].append(context["virtual_target"])

    cleanups = list(cleanup_groups.values())
    results: list[dict[str, Any]] = []
    matched_cleanup_ids: set[int] = set()
    for binding in binding_groups.values():
        matched = [
            cleanup for cleanup in cleanups if _cleanup_applies(binding, cleanup)
        ]
        matched_cleanup_ids.update(id(cleanup) for cleanup in matched)
        base_path = str(binding["evidence"]["path"])
        callback: dict[str, Any] = {
            "kind": binding["callback"]["kind"],
            "target": binding["callback"]["target"],
        }
        if binding["callback"].get("declaration"):
            callback["declaration"] = binding["callback"]["declaration"]
        callback_evidence = binding["callback"].get("evidence")
        if callback_evidence:
            if str(callback_evidence["path"]) != base_path:
                callback["path"] = callback_evidence["path"]
            callback["line"] = int(callback_evidence["line"])
        bind: dict[str, Any] = {
            "api": binding["api"],
            "in": binding["in"],
            "when": _when_value(binding["guards"]),
        }
        if not binding["in_is_virtual"]:
            bind["virtual_targets"] = _public_virtual_targets(
                binding["virtual_targets"], base_path
            )
        if binding.get("factory_api"):
            bind["factory"] = binding["factory_api"]
        bind["line"] = int(binding["evidence"]["line"])
        unbinds: list[dict[str, Any]] = []
        for cleanup in sorted(
            matched,
            key=lambda item: (
                item["evidence"]["path"],
                item["evidence"]["line"],
                item["api"],
            ),
        ):
            unbinds.append(_public_cleanup(cleanup, base_path))
        results.append(
            {
                "path": base_path,
                "delegate": binding["source"],
                "callback": callback,
                "bind": bind,
                "unbind": unbinds,
            }
        )
    results.sort(
        key=lambda item: (
            item["path"],
            item["bind"]["line"],
            item["delegate"],
        )
    )
    unmatched = [
        {
            "path": str(cleanup["evidence"]["path"]),
            "delegate": cleanup["source"],
            "cleanup": _public_cleanup(
                cleanup, str(cleanup["evidence"]["path"])
            ),
            "reason": "matching-binding-not-found",
        }
        for cleanup in cleanups
        if id(cleanup) not in matched_cleanup_ids
    ]
    unmatched.sort(
        key=lambda item: (
            item["path"],
            item["cleanup"]["line"],
            item["delegate"],
        )
    )
    return results, unmatched


def _argument_identity(operation: dict[str, Any]) -> str:
    arguments = operation.get("arguments", [])
    if not arguments:
        return ""
    expression = str(arguments[0].get("expression", ""))
    identifiers = re.findall(r"\b[A-Za-z_]\w*\b", expression)
    return identifiers[0] if identifiers else ""


def _split_camel(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", value).strip()


def _cleanup_mechanism(api: str) -> str:
    if api == "Remove":
        return "handle"
    if api == "RemoveAll":
        return "object-wide"
    if api in {"Unbind", "Clear"}:
        return "source-wide"
    return "explicit-api"


def _state_event(
    operation: dict[str, Any],
    callable_item: dict[str, Any],
    context: dict[str, Any],
    callables: dict[str, dict[str, Any]],
    class_name: str,
    known_sources: set[str],
) -> dict[str, Any] | None:
    if operation.get("kind") != "invocation":
        return None
    if _resolve_invocation(operation, callable_item, callables, class_name):
        return None
    callee = str(operation.get("callee", ""))
    receiver, api = _callee_parts(callee)
    source = _delegate_source(callee, api)
    method_names = {
        item["name"] for item in callables.values() if item["kind"] == "method"
    }
    callback = _callback_target(operation, class_name, method_names)
    callback_key = (
        _resolve_callback(callback, callables, class_name)
        if _callback_kind(operation, callback) == "function"
        else None
    )
    activates = callables[callback_key]["name"] if callback_key else None
    guard = _combine_guards(context["guard"], _operation_guard(operation))
    base = {
        "trigger": context["trigger"],
        "via": context["via"],
        "guard": guard,
        "evidence": operation["location"],
        "activates": activates,
        "api": api,
    }

    if api in _STARTUP_CALLBACK_APIS:
        state = "registered" if api == "RegisterStartupCallback" else "unregistered"
        return {
            **base,
            "subject_key": f"registration:startup-callback:{source}",
            "kind": "registration",
            "label": f"{source} startup callback",
            "sets_state": state,
            "certainty": "confirmed",
            "mechanism": _cleanup_mechanism(api),
        }

    if api in _DELEGATE_BIND_APIS | _DELEGATE_UNBIND_APIS and _looks_like_delegate(
        source, api, callback, known_sources
    ):
        return {
            **base,
            "subject_key": f"delegate:{source}",
            "kind": "delegate",
            "label": source,
            "sets_state": "bound" if api in _DELEGATE_BIND_APIS else "unbound",
            "certainty": "confirmed",
            "mechanism": _cleanup_mechanism(api),
        }

    register_match = re.match(r"^Register(.+)$", api)
    unregister_match = re.match(r"^(?:UnRegister|Unregister)(.+)$", api)
    if register_match or unregister_match:
        stem = (register_match or unregister_match).group(1)
        identity = _argument_identity(operation) or (receiver or "")
        return {
            **base,
            "subject_key": f"registration:{stem}:{identity}",
            "kind": "registration",
            "label": _split_camel(stem),
            "sets_state": "registered" if register_match else "unregistered",
            "certainty": "confirmed",
            "mechanism": "explicit-api",
        }

    if api in {"Initialize", "Shutdown"} and receiver:
        return {
            **base,
            "subject_key": f"service:{receiver}",
            "kind": "service",
            "label": receiver,
            "sets_state": "initialized" if api == "Initialize" else "shutdown",
            "certainty": "inferred",
            "mechanism": "paired-lifecycle-api",
        }

    receiver_root = re.split(r"\.|->|::", receiver or "", maxsplit=1)[0]
    if receiver_root in callable_item["observable_names"]:
        if api in {"Empty", "Clear"}:
            state = "cleared"
        elif api in {"Add", "AddUnique", "Append"}:
            state = "populated"
        else:
            state = ""
        if state:
            return {
                **base,
                "subject_key": f"collection:{callable_item['key']}:{receiver_root}",
                "kind": "collection",
                "label": f"{callable_item['name']} output {receiver_root}",
                "sets_state": state,
                "certainty": "confirmed",
                "mechanism": "collection-api",
            }

    if api == "ExtendMenu":
        return {
            **base,
            "subject_key": "menu:ToolMenus",
            "kind": "menu",
            "label": "editor menu",
            "sets_state": "extended",
            "certainty": "confirmed",
            "mechanism": "explicit-api",
        }
    return None


_EXPLICIT_UNRESOLVED_EFFECT_CALLEES = {
    "PreLoadingScreen->Init",
    "PreLoadingScreen.Reset",
    "UGameplayTagsManager::Get().AddTagIniSearchPath",
}


def _stateful_external_call(callee: str) -> bool:
    normalized_callee = "".join(callee.split())
    api = _method_name_from_callee(normalized_callee)
    return bool(
        normalized_callee in _EXPLICIT_UNRESOLVED_EFFECT_CALLEES
        or re.match(r"^(Set|Reset|Modify|Update)[A-Z_]", api)
        or re.match(r"^On[A-Z_].*(Begun|Ended|Updated)$", api)
    )


def _trigger_order(trigger: dict[str, str]) -> tuple[int, str]:
    name = trigger["name"]
    if trigger["kind"] == "lifecycle" and name == "StartupModule":
        return (0, name)
    if trigger["kind"] == "lifecycle" and name == "ShutdownModule":
        return (2, name)
    return (1, name)


def _transition_key(event: dict[str, Any]) -> tuple[Any, ...]:
    return (
        event["sets_state"],
        event["trigger"]["kind"],
        event["trigger"]["name"],
        tuple(event["via"]),
        event["certainty"],
        event["mechanism"],
    )


def _build_transitions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[_transition_key(event)].append(event)
    results: list[dict[str, Any]] = []
    for key, items in grouped.items():
        evidence = sorted(
            {
                (item["evidence"]["path"], int(item["evidence"]["line"]))
                for item in items
            }
        )
        results.append(
            {
                "sets_state": key[0],
                "trigger": {"kind": key[1], "name": key[2]},
                "via": list(key[3]),
                "when": _when_value(item["guard"] for item in items),
                "certainty": key[4],
                "evidence": [
                    {"path": path, "line": line} for path, line in evidence
                ],
                "_mechanism": key[5],
            }
        )
    results.sort(
        key=lambda item: (
            _trigger_order(item["trigger"]),
            item["evidence"][0]["path"],
            item["evidence"][0]["line"],
            item["sets_state"],
        )
    )
    return results


def _closure(kind: str, events: list[dict[str, Any]]) -> dict[str, str] | None:
    pairs = {
        "delegate": ("bound", "unbound"),
        "registration": ("registered", "unregistered"),
        "service": ("initialized", "shutdown"),
        "menu": ("extended", "restored"),
    }
    if kind not in pairs:
        return None
    active_state, cleanup_state = pairs[kind]
    active = [event for event in events if event["sets_state"] == active_state]
    cleanup = [event for event in events if event["sets_state"] == cleanup_state]
    if not active:
        return {
            "status": "unresolved",
            "pairing": "none",
            "reason": "activation-not-observed",
        }
    if not cleanup:
        return {
            "status": "open",
            "pairing": "none",
            "reason": "cleanup-not-observed",
        }
    covered = all(
        any(set(candidate["guard"]).issubset(set(event["guard"])) for candidate in cleanup)
        for event in active
    )
    cleanup_mechanisms = sorted({event["mechanism"] for event in cleanup})
    return {
        "status": "closed" if covered else "conditional",
        "pairing": cleanup_mechanisms[0] if len(cleanup_mechanisms) == 1 else "mixed",
        "reason": "cleanup-covers-activation" if covered else "cleanup-condition-differs",
    }


def _compact_when(when: list[list[str]]) -> list[str]:
    return [" && ".join(branch) for branch in when]


def _compact_via(transition: dict[str, Any]) -> list[str]:
    via = list(transition["via"])
    trigger_name = str(transition["trigger"]["name"])
    if via and via[0] == trigger_name:
        via = via[1:]
    return via


def _model_signature(model: dict[str, Any]) -> str:
    value = {
        "kind": model["subject"]["kind"],
        "transitions": [
            {
                "state": transition["sets_state"],
                "on": transition["trigger"]["name"],
                "via": _compact_via(transition),
                "when": _compact_when(transition["when"]),
                "certainty": transition["certainty"],
            }
            for transition in model["transitions"]
        ],
        "closure": {
            key: value
            for key, value in model.get("closure", {}).items()
            if key != "pairing"
        },
    }
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _compact_state_model(model: dict[str, Any]) -> dict[str, Any]:
    evidence_paths = sorted(
        {
            str(evidence["path"])
            for transition in model["transitions"]
            for evidence in transition["evidence"]
        }
    )
    common_path = evidence_paths[0] if len(evidence_paths) == 1 else None
    result: dict[str, Any] = {"subject": model["subject"]}
    if common_path:
        result["path"] = common_path

    transitions: list[dict[str, Any]] = []
    for transition in model["transitions"]:
        compact: dict[str, Any] = {
            "state": transition["sets_state"],
            "on": transition["trigger"]["name"],
        }
        via = _compact_via(transition)
        if via:
            compact["via"] = via
        compact["when"] = _compact_when(transition["when"])
        if transition["certainty"] != "confirmed":
            compact["certainty"] = transition["certainty"]

        evidence = transition["evidence"]
        if common_path and all(str(item["path"]) == common_path for item in evidence):
            lines = sorted({int(item["line"]) for item in evidence})
            if len(lines) == 1:
                compact["line"] = lines[0]
            else:
                compact["lines"] = lines
        else:
            compact["evidence"] = evidence
        transitions.append(compact)
    result["transitions"] = transitions

    closure = model.get("closure")
    if closure:
        result["closure"] = {
            "status": closure["status"],
            "reason": closure["reason"],
        }
    return result


def _compress_models(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_subject: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_subject[event["subject_key"]].append(event)
    models: list[dict[str, Any]] = []
    for subject_key, subject_events in sorted(by_subject.items()):
        first = subject_events[0]
        transitions = _build_transitions(subject_events)
        for transition in transitions:
            transition.pop("_mechanism", None)
        member = {"name": first["label"]}
        activations = sorted(
            {str(event["activates"]) for event in subject_events if event["activates"]}
        )
        if activations:
            member["activates"] = activations[0] if len(activations) == 1 else activations
        model: dict[str, Any] = {
            "subject": {
                "kind": first["kind"],
                "label": first["label"],
                "_member": member,
            },
            "transitions": transitions,
        }
        closure = _closure(first["kind"], subject_events)
        if closure:
            model["closure"] = closure
        models.append(model)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for model in models:
        grouped[_model_signature(model)].append(model)
    compressed: list[dict[str, Any]] = []
    for grouped_models in grouped.values():
        base = grouped_models[0]
        if len(grouped_models) == 1:
            base["subject"].pop("_member", None)
            compressed.append(base)
            continue
        members = [model["subject"].pop("_member") for model in grouped_models]
        base["subject"] = {
            "kind": f"{base['subject']['kind']}_group",
            "label": f"{len(members)} {base['subject']['kind']} subjects with identical transitions",
            "members": sorted(members, key=lambda item: item["name"]),
        }
        for index, transition in enumerate(base["transitions"]):
            combined = {
                (evidence["path"], evidence["line"])
                for model in grouped_models
                for evidence in model["transitions"][index]["evidence"]
            }
            transition["evidence"] = [
                {"path": path, "line": line} for path, line in sorted(combined)
            ]
        compressed.append(base)
    compressed.sort(
        key=lambda model: (
            model["subject"]["kind"],
            model["subject"]["label"],
        )
    )
    return [_compact_state_model(model) for model in compressed]


def _conditional_overrides(
    callables: dict[str, dict[str, Any]],
    contexts: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    candidates: dict[
        tuple[str, str, str, str, tuple[str, ...]], list[dict[str, Any]]
    ] = defaultdict(list)
    for key, callable_contexts in contexts.items():
        callable_item = callables[key]
        assignments: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for operation in callable_item["operations"]:
            if operation.get("kind") != "assignment":
                continue
            target = str(operation.get("target", ""))
            if target in callable_item["observable_names"]:
                assignments[target].append(operation)
        for name, items in assignments.items():
            defaults = [item for item in items if not _operation_guard(item)]
            overrides = [item for item in items if _operation_guard(item)]
            if not defaults or not overrides:
                continue
            default = min(defaults, key=lambda item: item["location"]["line"])
            for context in callable_contexts:
                for override in overrides:
                    if override["location"]["line"] <= default["location"]["line"]:
                        continue
                    group_key = (
                        key,
                        name,
                        context["trigger"]["kind"],
                        context["trigger"]["name"],
                        context["via"],
                    )
                    candidates[group_key].append(
                        {
                            "callable": callable_item,
                            "context": context,
                            "default": default,
                            "override": override,
                            "guard": _combine_guards(
                                context["guard"], _operation_guard(override)
                            ),
                        }
                    )

    results: list[dict[str, Any]] = []
    for (key, name, trigger_kind, trigger_name, via), items in sorted(candidates.items()):
        callable_item = items[0]["callable"]
        kind = "output" if name in callable_item["reference_parameters"] else "return"
        label = (
            f"{callable_item['name']} output {name}"
            if kind == "output"
            else f"{callable_item['name']} result"
        )
        override_evidence = sorted(
            {
                (
                    item["override"]["location"]["path"],
                    int(item["override"]["location"]["line"]),
                )
                for item in items
            }
        )
        results.append(
            {
                "subject": {"kind": kind, "label": label},
                "summary": ["default", "overridden"],
                "trigger": {
                    "kind": trigger_kind,
                    "name": trigger_name,
                },
                "via": list(via),
                "when": _when_value(item["guard"] for item in items),
                "certainty": "confirmed",
                "evidence": {
                    "default": {
                        "path": items[0]["default"]["location"]["path"],
                        "line": items[0]["default"]["location"]["line"],
                    },
                    "override": [
                        {"path": path, "line": line}
                        for path, line in override_evidence
                    ],
                },
            }
        )
    return results


def _unresolved_effects(
    callables: dict[str, dict[str, Any]],
    contexts: dict[str, list[dict[str, Any]]],
    class_name: str,
    recognized_locations: set[tuple[str, int]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[tuple[str, ...]]] = defaultdict(list)
    for key, callable_contexts in contexts.items():
        callable_item = callables[key]
        for operation in callable_item["operations"]:
            if operation.get("kind") != "invocation":
                continue
            if _resolve_invocation(operation, callable_item, callables, class_name):
                continue
            location_key = (
                operation["location"]["path"],
                int(operation["location"]["line"]),
            )
            if location_key in recognized_locations:
                continue
            callee = str(operation.get("callee", ""))
            if not _stateful_external_call(callee):
                continue
            for context in callable_contexts:
                group_key = (
                    context["trigger"]["kind"],
                    context["trigger"]["name"],
                    context["via"],
                    callee,
                    operation["location"]["path"],
                    int(operation["location"]["line"]),
                )
                grouped[group_key].append(
                    _combine_guards(context["guard"], _operation_guard(operation))
                )
    results = [
        {
            "trigger": {"kind": key[0], "name": key[1]},
            "via": list(key[2]),
            "call": key[3],
            "when": _when_value(guards),
            "reason": "callee-state-not-visible",
            "evidence": {"path": key[4], "line": key[5]},
        }
        for key, guards in grouped.items()
    ]
    results.sort(
        key=lambda item: (
            _trigger_order(item["trigger"]),
            item["evidence"]["path"],
            item["evidence"]["line"],
        )
    )
    return results


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
    problems: list[dict[str, Any]] = [
        {
            **problem,
            "path": relative_paths[parsed["path"]],
        }
        for parsed in parsed_files
        for problem in parsed.get("problems", [])
    ]
    registrations = [
        {
            **macro,
            "location": _with_path(
                macro["location"], relative_paths[parsed["path"]]
            ),
        }
        for parsed in parsed_files
        for macro in parsed["registration_macros"]
    ]
    matching_registrations = [
        item
        for item in registrations
        if str(item.get("module_name", "")).casefold() == module_name.casefold()
    ]
    class_bases: dict[str, set[str]] = defaultdict(set)
    for parsed in parsed_files:
        for class_item in parsed["classes"]:
            class_bases[class_item["name"]].update(class_item["base_types"])

    class_candidates = sorted(
        {
            str(item["module_class"])
            for item in matching_registrations
            if item.get("module_class")
        }
    )
    conditional_registration_variants = _registrations_are_conditional_variants(
        matching_registrations
    )
    if not matching_registrations:
        problems.append(
            {
                "severity": "warning",
                "code": "module-registration-not-found",
                "module_name": module_name,
                "message": f"No matching IMPLEMENT_*_MODULE declaration was found for {module_name}",
            }
        )
        class_candidates = sorted(
            name
            for name, bases in class_bases.items()
            if any(
                base.endswith("ModuleInterface") or base.endswith("GameModuleImpl")
                for base in bases
            )
        )
    elif conditional_registration_variants:
        problems.append(
            {
                "severity": "warning",
                "code": "module-registration-conditional-variants",
                "module_name": module_name,
                "locations": [item["location"] for item in matching_registrations],
                "candidates": class_candidates,
                "message": (
                    "Mutually exclusive preprocessor branches select different "
                    "module classes; state analysis was skipped."
                    if len(class_candidates) > 1
                    else "Mutually exclusive preprocessor branches contain multiple "
                    "matching module registrations."
                ),
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

    module_class = class_candidates[0] if len(class_candidates) == 1 else None
    if len(class_candidates) > 1 and not conditional_registration_variants:
        problems.append(
            {
                "severity": "warning",
                "code": "module-class-ambiguous",
                "candidates": class_candidates,
                "message": "Multiple module class candidates were found; state analysis was skipped.",
            }
        )
    if module_class and module_class not in class_bases:
        if module_class not in {"FDefaultModuleImpl", "FDefaultGameModuleImpl"}:
            problems.append(
                {
                    "severity": "warning",
                    "code": "module-class-definition-not-found",
                    "module_class": module_class,
                    "message": f"Module class {module_class} was registered but not declared in the module source tree",
                }
            )
        module_class = None

    state_models: list[dict[str, Any]] = []
    callback_bindings: list[dict[str, Any]] = []
    unmatched_cleanups: list[dict[str, Any]] = []
    conditional_overrides: list[dict[str, Any]] = []
    unresolved_effects: list[dict[str, Any]] = []
    if module_class:
        callables, ambiguous = _build_callables(
            parsed_files, relative_paths, module_class
        )
        contexts = _build_contexts(
            callables, ambiguous, module_class, problems
        )
        callback_bindings, unmatched_cleanups = _callback_bindings(
            callables, contexts, ambiguous, module_class
        )
        known_sources = _known_delegate_sources(callables, module_class)
        events: list[dict[str, Any]] = []
        for key, callable_contexts in contexts.items():
            callable_item = callables[key]
            for context in callable_contexts:
                for operation in callable_item["operations"]:
                    event = _state_event(
                        operation,
                        callable_item,
                        context,
                        callables,
                        module_class,
                        known_sources,
                    )
                    if event:
                        events.append(event)
        callback_operation_keys = {
            (
                binding["bind"].get("path", binding["path"]),
                int(binding["bind"]["line"]),
                binding["bind"]["api"],
            )
            for binding in callback_bindings
        }
        callback_operation_keys.update(
            (
                unbind.get("path", binding["path"]),
                int(unbind["line"]),
                unbind["api"],
            )
            for binding in callback_bindings
            for unbind in binding["unbind"]
        )
        callback_operation_keys.update(
            (
                item["cleanup"].get("path", item["path"]),
                int(item["cleanup"]["line"]),
                item["cleanup"]["api"],
            )
            for item in unmatched_cleanups
        )
        state_events = [
            event
            for event in events
            if event["kind"] != "delegate"
            and not (
                (
                    event["evidence"]["path"],
                    int(event["evidence"]["line"]),
                    event["api"],
                )
                in callback_operation_keys
            )
        ]
        state_models = _compress_models(state_events)
        conditional_overrides = _conditional_overrides(callables, contexts)
        recognized_locations = {
            (event["evidence"]["path"], int(event["evidence"]["line"]))
            for event in events
        }
        unresolved_effects = _unresolved_effects(
            callables,
            contexts,
            module_class,
            recognized_locations,
        )

    registration = None
    if len(matching_registrations) == 1:
        selected = matching_registrations[0]
        registration = {
            "macro": selected["macro"],
            "module_class": selected.get("module_class"),
            "evidence": {
                "path": selected["location"]["path"],
                "line": selected["location"]["line"],
            },
        }

    return result_document(
        "ue-itps.module-entry-state.v12",
        {
            "module": {
                "name": module_name,
                "class": module_class,
                "root": normalized(module_root),
                "build_rules": _relative_path(rules, module_root),
                "scanned_file_count": len(module_files),
            },
            "registration": registration,
            "callback_bindings": callback_bindings,
            "unmatched_cleanups": unmatched_cleanups,
            "state_models": state_models,
            "conditional_overrides": conditional_overrides,
            "unresolved_effects": unresolved_effects,
        },
        problems,
        responsibility="Report callback binding facts and non-callback state transitions caused by one module's lifecycle.",
        boundaries=[
            "The selected Build.cs parent directory defines the module source boundary.",
            "Callback bindings require a recognized binding API and a supported function, lambda, or UFunction target.",
            "Lambda and UFunction callback bodies are not followed.",
            "Bound top-level static callback bodies are not followed; their declarations are reported with the binding facts.",
            "Unbind pairing uses delegate source plus supported object, callback, or handle identities.",
            "An unmatched cleanup is reachable source evidence, not proof of an invalid runtime cleanup.",
            "Virtual targets follow ordinary same-module calls and report call sites inside virtual functions; callback registration is not a call edge.",
            "A conditional override default means the value before this module's first observed override.",
            "Changed values and right-hand-side expressions are intentionally omitted.",
            "Opaque external calls are not interpreted as concrete state changes.",
            "Results are static source evidence and not runtime behavior proof.",
        ],
    )
