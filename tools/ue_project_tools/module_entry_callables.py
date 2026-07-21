from __future__ import annotations

from collections import defaultdict, deque
import re
from typing import Any

from .module_entry_common import (
    _DELEGATE_BIND_APIS,
    _MAX_CONTEXTS_PER_CALLABLE,
    _callee_parts,
    _callback_kind,
    _callback_target,
    _combine_guards,
    _delegate_source,
    _method_name_from_callee,
    _operation_guard,
    _self_method_name,
    _with_path,
)
from .source_parser import lex_source, parse_operations


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
