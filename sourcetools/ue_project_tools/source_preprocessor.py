from __future__ import annotations

from typing import Any

from .source_flow import _control_references
from .source_tokens import _ordered_union, lex_source


def _preprocessor_directive(line: str) -> tuple[str, str, str] | None:
    stripped = line.strip()
    prefixes = (
        ("#ifdef ", "ifdef"),
        ("#ifndef ", "ifndef"),
        ("#elif ", "elif"),
        ("#if ", "if"),
    )
    for prefix, kind in prefixes:
        if not stripped.startswith(prefix):
            continue
        raw_expression = stripped[len(prefix) :].strip()
        condition_expression = raw_expression
        if kind == "ifdef":
            condition_expression = f"defined({raw_expression})"
        elif kind == "ifndef":
            condition_expression = f"!defined({raw_expression})"
        return kind, raw_expression, condition_expression
    if stripped.startswith("#else"):
        return "else", "", ""
    if stripped.startswith("#endif"):
        return "endif", "", ""
    return None


def _preprocessor_literal_value(expression: str) -> bool | None:
    value = "".join(expression.split())
    while value.startswith("(") and value.endswith(")"):
        value = value[1:-1]
    negated = False
    while value.startswith("!"):
        negated = not negated
        value = value[1:]
    literals = {"0": False, "1": True, "false": False, "true": True}
    result = literals.get(value.casefold())
    return None if result is None else result != negated


def _branch_active(
    previous_values: list[bool | None],
    condition_value: bool | None,
) -> bool | None:
    if condition_value is False or any(value is True for value in previous_values):
        return False
    if all(value is False for value in previous_values):
        return condition_value
    return None


def _preprocessor_contexts(
    text: str,
) -> tuple[
    dict[int, list[dict[str, Any]]],
    dict[int, list[dict[str, Any]]],
    dict[int, list[dict[str, Any]]],
]:
    condition_stack: list[dict[str, Any]] = []
    registration_stack: list[dict[str, Any]] = []
    control_stack: list[dict[str, Any]] = []
    condition_result: dict[int, list[dict[str, Any]]] = {}
    registration_result: dict[int, list[dict[str, Any]]] = {}
    control_result: dict[int, list[dict[str, Any]]] = {}

    for line_number, line in enumerate(text.splitlines(), start=1):
        directive = _preprocessor_directive(line)
        if directive is not None:
            kind, raw_expression, condition_expression = directive
            if kind in {"if", "ifdef", "ifndef"}:
                condition_stack.append(
                    {
                        "kind": "preprocessor",
                        "expression": condition_expression,
                        "branch": "then",
                        "start_line": line_number,
                    }
                )
                condition_value = _preprocessor_literal_value(condition_expression)
                registration_stack.append(
                    {
                        "group_line": line_number,
                        "arm": 0,
                        "branch": kind,
                        "expression": condition_expression,
                        "condition_value": condition_value,
                        "previous_values": [],
                        "active": condition_value,
                    }
                )
                control_stack.append(
                    {
                        "start_line": line_number,
                        "kind": "preprocessor",
                        "references": _control_references(
                            lex_source(raw_expression)
                        ),
                    }
                )
            elif kind == "elif":
                if condition_stack:
                    condition_stack[-1] = {
                        **condition_stack[-1],
                        "expression": condition_expression,
                        "branch": "elif",
                    }
                if registration_stack:
                    frame = registration_stack[-1]
                    previous_values = [
                        *frame["previous_values"],
                        frame["condition_value"],
                    ]
                    condition_value = _preprocessor_literal_value(
                        condition_expression
                    )
                    frame.update(
                        {
                            "arm": int(frame["arm"]) + 1,
                            "branch": "elif",
                            "expression": condition_expression,
                            "condition_value": condition_value,
                            "previous_values": previous_values,
                            "active": _branch_active(
                                previous_values, condition_value
                            ),
                        }
                    )
                if control_stack:
                    references = _control_references(lex_source(raw_expression))
                    control_stack[-1]["references"] = _ordered_union(
                        control_stack[-1]["references"], references
                    )
            elif kind == "else":
                if condition_stack:
                    condition_stack[-1] = {
                        **condition_stack[-1],
                        "branch": "else",
                    }
                if registration_stack:
                    frame = registration_stack[-1]
                    previous_values = [
                        *frame["previous_values"],
                        frame["condition_value"],
                    ]
                    frame.update(
                        {
                            "arm": int(frame["arm"]) + 1,
                            "branch": "else",
                            "expression": "",
                            "condition_value": True,
                            "previous_values": previous_values,
                            "active": _branch_active(previous_values, True),
                        }
                    )
            elif kind == "endif":
                if condition_stack:
                    condition_stack.pop()
                if registration_stack:
                    registration_stack.pop()
                if control_stack:
                    control_stack.pop()

        condition_result[line_number] = [dict(item) for item in condition_stack]
        registration_result[line_number] = [
            {
                key: frame[key]
                for key in ("group_line", "arm", "branch", "expression", "active")
            }
            for frame in registration_stack
        ]
        control_result[line_number] = [dict(item) for item in control_stack]

    return condition_result, registration_result, control_result


def preprocessor_conditions(text: str) -> dict[int, list[dict[str, Any]]]:
    conditions, _, _ = _preprocessor_contexts(text)
    return conditions


def _registration_preprocessor_contexts(
    text: str,
) -> dict[int, list[dict[str, Any]]]:
    _, registrations, _ = _preprocessor_contexts(text)
    return registrations


def preprocessor_control_contexts(text: str) -> dict[int, list[dict[str, Any]]]:
    _, _, controls = _preprocessor_contexts(text)
    return controls
