from __future__ import annotations

from collections import defaultdict, deque
import json
from pathlib import Path
import re
from typing import Any, Iterable

from .common import normalized, result_document
from .source_parser import parse_cpp_file, parse_operations, source_files


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
_MAX_CONTEXTS_PER_CALLABLE = 32


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


def _callback_target(
    operation: dict[str, Any],
    class_name: str,
    method_names: set[str],
) -> str | None:
    expressions = [
        str(argument.get("expression", ""))
        for argument in operation.get("arguments", [])
    ]
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
    if any("[" in expression and "]" in expression for expression in expressions):
        return "<lambda>"
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
    )
    for operation in operations:
        operation["location"] = _with_path(operation["location"], relative_path)
    return operations, _returned_names(parsed["tokens"], body_range)


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
                }
            )
        for function in parsed.get("free_functions", []):
            operations, returned = _parse_callable_body(
                parsed, function["body_range"], relative_path
            )
            parts[f"free:{function['name']}"].append(
                {
                    "kind": "free",
                    "name": function["name"],
                    "parameters": function["parameters"],
                    "definition": True,
                    "operations": operations,
                    "returned_names": returned,
                }
            )

    callables: dict[str, dict[str, Any]] = {}
    ambiguous: set[str] = set()
    for key, items in sorted(parts.items()):
        parameters = {str(item["parameters"]) for item in items}
        definitions = sum(1 for item in items if item["definition"])
        if len(parameters) > 1 or definitions > 1:
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
        }
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
    seen: set[tuple[str, str, str, tuple[str, ...], tuple[str, ...]]] = set()
    queue: deque[tuple[str, dict[str, str], tuple[str, ...], tuple[str, ...]]] = deque()
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
    ) -> None:
        if key in ambiguous:
            unresolved_ambiguous.add(key)
            return
        signature = (key, trigger["kind"], trigger["name"], via, guard)
        if signature in seen:
            return
        if len(contexts[key]) >= _MAX_CONTEXTS_PER_CALLABLE:
            truncated.add(key)
            return
        seen.add(signature)
        context = {"trigger": trigger, "via": via, "guard": guard}
        contexts[key].append(context)
        queue.append((key, trigger, via, guard))

    for root in ("StartupModule", "ShutdownModule"):
        key = f"method:{root}"
        if key in callables:
            enqueue(key, {"kind": "lifecycle", "name": root}, (root,), ())

    while queue:
        key, trigger, via, guard = queue.popleft()
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
                enqueue(
                    callee_key,
                    trigger,
                    (*via, callables[callee_key]["name"]),
                    effective_guard,
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
            callback_key = _resolve_callback(callback, callables, class_name)
            if callback_key:
                callback_name = callables[callback_key]["name"]
                enqueue(
                    callback_key,
                    {"kind": "callback", "name": callback_name},
                    (callback_name,),
                    effective_guard,
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
    callback_key = _resolve_callback(callback, callables, class_name)
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


def _stateful_external_call(api: str) -> bool:
    return bool(
        re.match(r"^(Set|Reset|Modify|Update)[A-Z_]", api)
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


def _summary(kind: str, events: list[dict[str, Any]]) -> list[str]:
    order = {
        "bound": 0,
        "registered": 0,
        "initialized": 0,
        "cleared": 0,
        "extended": 0,
        "populated": 1,
        "unbound": 2,
        "unregistered": 2,
        "shutdown": 2,
        "restored": 2,
    }
    states = sorted(
        {event["sets_state"] for event in events},
        key=lambda state: (order.get(state, 1), state),
    )
    return ["default", *states]


def _model_signature(model: dict[str, Any]) -> str:
    value = {
        "kind": model["subject"]["kind"],
        "summary": model["summary"],
        "transitions": [
            {key: value for key, value in transition.items() if key != "evidence"}
            for transition in model["transitions"]
        ],
        "closure": model.get("closure"),
    }
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


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
            "summary": _summary(first["kind"], subject_events),
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
    return compressed


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
            api = _method_name_from_callee(str(operation.get("callee", "")))
            if not _stateful_external_call(api):
                continue
            for context in callable_contexts:
                group_key = (
                    context["trigger"]["kind"],
                    context["trigger"]["name"],
                    context["via"],
                    str(operation.get("callee", "")),
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
    problems: list[dict[str, Any]] = []
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
    if len(class_candidates) > 1:
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
    conditional_overrides: list[dict[str, Any]] = []
    unresolved_effects: list[dict[str, Any]] = []
    if module_class:
        callables, ambiguous = _build_callables(
            parsed_files, relative_paths, module_class
        )
        contexts = _build_contexts(
            callables, ambiguous, module_class, problems
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
        state_models = _compress_models(events)
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
            "evidence": {
                "path": selected["location"]["path"],
                "line": selected["location"]["line"],
            },
        }

    return result_document(
        "ue-itps.module-entry-state.v7",
        {
            "module": {
                "name": module_name,
                "class": module_class,
                "root": normalized(module_root),
                "build_rules": _relative_path(rules, module_root),
                "scanned_file_count": len(module_files),
            },
            "registration": registration,
            "state_models": state_models,
            "conditional_overrides": conditional_overrides,
            "unresolved_effects": unresolved_effects,
        },
        problems,
        responsibility="Report state transitions caused by one module's lifecycle and bound callbacks.",
        boundaries=[
            "The selected Build.cs parent directory defines the module source boundary.",
            "Default means the state before this module's first observed mutation.",
            "Changed values and right-hand-side expressions are intentionally omitted.",
            "Opaque external calls are not interpreted as concrete state changes.",
            "Results are static source evidence and not runtime behavior proof.",
        ],
    )
