from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .common import normalized, result_document
from .module_entry_callables import (
    _build_callables,
    _build_contexts,
    _known_delegate_sources,
)
from .module_entry_callbacks import _callback_bindings
from .module_entry_common import (
    _registrations_are_conditional_variants,
    _relative_path,
    _with_path,
)
from .module_entry_states import (
    _compress_models,
    _conditional_overrides,
    _state_event,
    _unresolved_effects,
)
from .source_parser import parse_cpp_file, source_files


def _validated_rules_path(rules_path: Path) -> tuple[Path, str]:
    rules = rules_path.resolve()
    if not rules.is_file():
        raise ValueError(f"Module Build.cs is not a file: {rules}")
    if not rules.name.casefold().endswith(".build.cs"):
        raise ValueError(f"Expected a Module Build.cs file: {rules}")
    module_name = rules.name[: -len(".Build.cs")]
    if not module_name:
        raise ValueError(f"Module Build.cs filename has no module name: {rules}")
    return rules, module_name


def _load_module_sources(
    rules: Path,
) -> tuple[
    Path,
    list[Path],
    list[dict[str, Any]],
    dict[str, str],
    list[dict[str, Any]],
]:
    module_root = rules.parent
    module_files = source_files(module_root)
    parsed_files = [parse_cpp_file(path) for path in module_files]
    relative_paths = {
        parsed["path"]: _relative_path(parsed["path"], module_root)
        for parsed in parsed_files
    }
    problems = [
        {
            **problem,
            "path": relative_paths[parsed["path"]],
        }
        for parsed in parsed_files
        for problem in parsed.get("problems", [])
    ]
    return module_root, module_files, parsed_files, relative_paths, problems


def _select_module_class(
    module_name: str,
    parsed_files: list[dict[str, Any]],
    relative_paths: dict[str, str],
    problems: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
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
    conditional_variants = _registrations_are_conditional_variants(
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
    elif conditional_variants:
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
    if len(class_candidates) > 1 and not conditional_variants:
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
    return matching_registrations, module_class


def _analyze_module_class(
    module_class: str | None,
    parsed_files: list[dict[str, Any]],
    relative_paths: dict[str, str],
    problems: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {
        "callback_bindings": [],
        "unmatched_cleanups": [],
        "state_models": [],
        "conditional_overrides": [],
        "unresolved_effects": [],
    }
    if module_class is None:
        return result

    callables, ambiguous = _build_callables(
        parsed_files, relative_paths, module_class
    )
    contexts = _build_contexts(callables, ambiguous, module_class, problems)
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
        and (
            event["evidence"]["path"],
            int(event["evidence"]["line"]),
            event["api"],
        )
        not in callback_operation_keys
    ]
    recognized_locations = {
        (event["evidence"]["path"], int(event["evidence"]["line"]))
        for event in events
    }
    result.update(
        {
            "callback_bindings": callback_bindings,
            "unmatched_cleanups": unmatched_cleanups,
            "state_models": _compress_models(state_events),
            "conditional_overrides": _conditional_overrides(callables, contexts),
            "unresolved_effects": _unresolved_effects(
                callables,
                contexts,
                module_class,
                recognized_locations,
            ),
        }
    )
    return result


def _public_registration(
    matching_registrations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if len(matching_registrations) != 1:
        return None
    selected = matching_registrations[0]
    return {
        "macro": selected["macro"],
        "module_class": selected.get("module_class"),
        "evidence": {
            "path": selected["location"]["path"],
            "line": selected["location"]["line"],
        },
    }


def inspect_module_entry(rules_path: Path) -> dict[str, Any]:
    rules, module_name = _validated_rules_path(rules_path)
    (
        module_root,
        module_files,
        parsed_files,
        relative_paths,
        problems,
    ) = _load_module_sources(rules)
    matching_registrations, module_class = _select_module_class(
        module_name, parsed_files, relative_paths, problems
    )
    analysis = _analyze_module_class(
        module_class, parsed_files, relative_paths, problems
    )

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
            "registration": _public_registration(matching_registrations),
            **analysis,
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
