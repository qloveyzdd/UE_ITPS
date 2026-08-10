from __future__ import annotations

from collections import defaultdict
import json
import re
from typing import Any

from .module_entry_callables import (
    _looks_like_delegate,
    _resolve_callback,
    _resolve_invocation,
)
from .module_entry_common import (
    _DELEGATE_BIND_APIS,
    _DELEGATE_UNBIND_APIS,
    _STARTUP_CALLBACK_APIS,
    _callback_kind,
    _callback_target,
    _callee_parts,
    _combine_guards,
    _delegate_source,
    _method_name_from_callee,
    _operation_guard,
    _when_value,
)


_EXPLICIT_UNRESOLVED_EFFECT_CALLEES = {
    "PreLoadingScreen->Init",
    "PreLoadingScreen.Reset",
    "UGameplayTagsManager::Get().AddTagIniSearchPath",
}


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
