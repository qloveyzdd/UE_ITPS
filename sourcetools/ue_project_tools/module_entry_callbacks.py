from __future__ import annotations

import re
from typing import Any

from .module_entry_callables import _resolve_callback
from .module_entry_common import (
    _CALLBACK_FACTORY_APIS,
    _DELEGATE_BIND_APIS,
    _DELEGATE_UNBIND_APIS,
    _LAMBDA_BIND_APIS,
    _STARTUP_CALLBACK_APIS,
    _UFUNCTION_BIND_APIS,
    _callback_kind,
    _callback_reference,
    _callback_target,
    _callee_parts,
    _combine_guards,
    _delegate_source,
    _method_name_from_callee,
    _operation_guard,
    _source_evidence,
    _when_value,
)


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
