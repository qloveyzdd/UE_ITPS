from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Iterable


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
