from __future__ import annotations

from typing import Any

from .source_controls import (
    _conditions_for,
    _control_metadata_for,
    _expression_gate_controls,
    _member_chain_start,
    _merge_control_metadata,
    _preprocessor_contexts,
    condition_spans,
    control_expression_ranges,
    control_spans,
)
from .source_declarations import _declaration_name
from .source_tokens import (
    Token,
    _evaluation,
    _location,
    _raw,
    _raw_from_values,
    _split_arguments,
)


def _assignment_value_end(
    tokens: list[Token], start: int, assignment_index: int, end: int
) -> int:
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    for index in range(start, assignment_index):
        value = tokens[index].value
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
    initial = (paren_depth, bracket_depth, brace_depth)
    for index in range(assignment_index + 1, end):
        value = tokens[index].value
        if value == ")" and paren_depth == initial[0] and initial[0] > 0:
            return index
        if value == "]" and bracket_depth == initial[1] and initial[1] > 0:
            return index
        if value == "}" and brace_depth == initial[2] and initial[2] > 0:
            return index
        if value in {";", ","} and (paren_depth, bracket_depth, brace_depth) == initial:
            return index
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
    return end


def _expression_operations(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
    reverse: dict[int, int],
    expression_range: dict[str, Any],
    spans: list[dict[str, Any]],
    pp_context: dict[int, list[dict[str, str]]],
    flow_spans: list[dict[str, Any]],
    pp_flow: dict[int, list[dict[str, Any]]],
) -> list[tuple[int, dict[str, Any]]]:
    start = int(expression_range["start"])
    end = int(expression_range["end"])
    excluded_targets = set(expression_range.get("excluded_targets", set()))
    base_controls = list(expression_range.get("controls", []))
    results: list[tuple[int, dict[str, Any]]] = []

    for assignment_index in range(start, end):
        operator = tokens[assignment_index].value
        if operator not in {"=", "+=", "-=", "*=", "/=", "??="}:
            continue
        name_index = assignment_index - 1
        while name_index >= start and tokens[name_index].kind != "identifier":
            name_index -= 1
        if name_index < start:
            continue
        target_start = _member_chain_start(tokens, reverse, name_index, start)
        target = _raw(text, tokens, target_start, assignment_index)
        target_root = target.split(".", 1)[0]
        if target_root in excluded_targets:
            continue
        value_end = _assignment_value_end(tokens, start, assignment_index, end)
        if value_end <= assignment_index + 1:
            continue
        metadata = _control_metadata_for(
            assignment_index,
            tokens[assignment_index],
            flow_spans,
            pp_flow,
        )
        metadata = _merge_control_metadata(metadata, base_controls)
        metadata = _merge_control_metadata(
            metadata,
            _expression_gate_controls(tokens, forward, start, target_start, end),
        )
        operation: dict[str, Any] = {
            "kind": "assignment",
            "target": target,
            "operator": operator,
            "value_expression": _raw(
                text, tokens, assignment_index + 1, value_end
            ),
            "expression": _raw(text, tokens, target_start, value_end),
            "evaluation": _evaluation(tokens[assignment_index + 1 : value_end]),
            "conditions": _conditions_for(
                assignment_index,
                tokens[assignment_index],
                spans,
                pp_context,
            ),
            "location": _location(tokens[target_start], tokens[value_end - 1]),
            **metadata,
        }
        results.append((assignment_index, operation))

    for update_index in range(start, end):
        operator = tokens[update_index].value
        if operator not in {"++", "--"}:
            continue
        prefix = update_index + 1 < end and tokens[update_index + 1].kind == "identifier"
        if prefix:
            target_start = update_index + 1
            target_end = target_start + 1
            while (
                target_end + 1 < end
                and tokens[target_end].value in {".", "::", "->"}
                and tokens[target_end + 1].kind == "identifier"
            ):
                target_end += 2
            expression_start = update_index
            expression_end = target_end
        else:
            name_index = update_index - 1
            if name_index < start or tokens[name_index].kind != "identifier":
                continue
            target_start = _member_chain_start(tokens, reverse, name_index, start)
            target_end = update_index
            expression_start = target_start
            expression_end = update_index + 1
        target = _raw(text, tokens, target_start, target_end)
        if target.split(".", 1)[0] in excluded_targets:
            continue
        metadata = _control_metadata_for(
            update_index, tokens[update_index], flow_spans, pp_flow
        )
        metadata = _merge_control_metadata(metadata, base_controls)
        metadata = _merge_control_metadata(
            metadata,
            _expression_gate_controls(tokens, forward, start, expression_start, end),
        )
        operation = {
            "kind": "assignment",
            "target": target,
            "operator": operator,
            "value_expression": operator,
            "expression": _raw(text, tokens, expression_start, expression_end),
            "evaluation": {"status": "unresolved", "literal_values": []},
            "conditions": _conditions_for(
                update_index, tokens[update_index], spans, pp_context
            ),
            "location": _location(
                tokens[expression_start], tokens[expression_end - 1]
            ),
            **metadata,
        }
        results.append((update_index, operation))

    excluded_calls = {
        "alignof",
        "catch",
        "decltype",
        "for",
        "foreach",
        "if",
        "new",
        "sizeof",
        "switch",
        "while",
    }
    for open_index in range(start, end):
        if tokens[open_index].value != "(" or open_index not in forward:
            continue
        close = forward[open_index]
        if close >= end or open_index == start:
            continue
        name_index = open_index - 1
        if (
            tokens[name_index].kind != "identifier"
            or tokens[name_index].value in excluded_calls
        ):
            continue
        callee_start = _member_chain_start(tokens, reverse, name_index, start)
        if callee_start > start and tokens[callee_start - 1].value == "new":
            continue
        argument_ranges = _split_arguments(tokens, open_index + 1, close)
        arguments = [
            {
                "expression": _raw(text, tokens, argument_start, argument_end),
                "evaluation": _evaluation(tokens[argument_start:argument_end]),
            }
            for argument_start, argument_end in argument_ranges
        ]
        evaluation_tokens = [
            token
            for argument_start, argument_end in argument_ranges
            for token in tokens[argument_start:argument_end]
        ]
        metadata = _control_metadata_for(
            name_index, tokens[name_index], flow_spans, pp_flow
        )
        metadata = _merge_control_metadata(metadata, base_controls)
        metadata = _merge_control_metadata(
            metadata,
            _expression_gate_controls(tokens, forward, start, callee_start, end),
        )
        operation = {
            "kind": "invocation",
            "callee": _raw_from_values(tokens[callee_start:open_index]),
            "arguments": arguments,
            "expression": _raw(text, tokens, callee_start, close + 1),
            "evaluation": _evaluation(evaluation_tokens),
            "conditions": _conditions_for(
                name_index, tokens[name_index], spans, pp_context
            ),
            "location": _location(tokens[callee_start], tokens[close]),
            **metadata,
        }
        results.append((open_index, operation))
    return results


def _lambda_body_openings(
    tokens: list[Token],
    forward: dict[int, int],
    reverse: dict[int, int],
    start: int,
    end: int,
) -> set[int]:
    openings: set[int] = set()
    for capture_close in range(start, end):
        if tokens[capture_close].value != "]" or capture_close not in reverse:
            continue
        capture_open = reverse[capture_close]
        if capture_open < start:
            continue
        if capture_open > start:
            before = tokens[capture_open - 1]
            if before.kind in {"identifier", "number", "string"} or before.value in {
                ")",
                "]",
            }:
                continue
        for cursor in range(capture_close + 1, end):
            if tokens[cursor].value == ";":
                break
            if tokens[cursor].value == "{" and cursor in forward:
                openings.add(cursor)
                break
    return openings


def parse_operations(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
    reverse: dict[int, int],
    start: int,
    end: int,
    include_control_metadata: bool = False,
) -> list[dict[str, Any]]:
    spans = condition_spans(tokens, forward, start, end)
    pp_context, _, discovered_pp_flow = _preprocessor_contexts(text)
    flow_spans = control_spans(tokens, forward, start, end) if include_control_metadata else []
    pp_flow = discovered_pp_flow if include_control_metadata else {}
    operations: list[tuple[int, dict[str, Any]]] = []
    lambda_openings = _lambda_body_openings(
        tokens, forward, reverse, start, end
    )
    lambda_closings = {forward[index] for index in lambda_openings}
    lambda_ranges = [(index, forward[index]) for index in lambda_openings]
    if include_control_metadata:
        for expression_range in control_expression_ranges(
            tokens, forward, start, end
        ):
            operations.extend(
                _expression_operations(
                    text,
                    tokens,
                    forward,
                    reverse,
                    expression_range,
                    spans,
                    pp_context,
                    flow_spans,
                    pp_flow,
                )
            )
    statement_start = start
    brace_depth = 0
    paren_depth = 0
    bracket_depth = 0
    for cursor in range(start, end):
        value = tokens[cursor].value
        if value == "(":
            paren_depth += 1
        elif value == ")":
            paren_depth = max(0, paren_depth - 1)
        elif value == "[":
            bracket_depth += 1
        elif value == "]":
            bracket_depth = max(0, bracket_depth - 1)
        elif value == "{" and cursor in lambda_openings:
            brace_depth += 1
        elif value == "}" and cursor in lambda_closings:
            brace_depth = max(0, brace_depth - 1)
        elif value == "{" and paren_depth == 0 and bracket_depth == 0:
            brace_depth += 1
            statement_start = cursor + 1
        elif value == "}" and paren_depth == 0 and bracket_depth == 0:
            brace_depth = max(0, brace_depth - 1)
            statement_start = cursor + 1
        elif (
            value == ":"
            and paren_depth == 0
            and bracket_depth == 0
            and statement_start < cursor
            and tokens[statement_start].value in {"case", "default"}
        ):
            statement_start = cursor + 1
        elif value == ";" and paren_depth == 0 and bracket_depth == 0:
            segment_start = statement_start
            while segment_start < cursor and tokens[segment_start].value in {"else"}:
                segment_start += 1
            if segment_start < cursor and tokens[segment_start].value == "if" and segment_start + 1 in forward:
                segment_start = forward[segment_start + 1] + 1
            operations.extend(
                _statement_operations(
                    text,
                    tokens,
                    forward,
                    reverse,
                    segment_start,
                    cursor,
                    spans,
                    pp_context,
                    flow_spans,
                    pp_flow,
                    include_control_metadata,
                )
            )
            statement_start = cursor + 1
    return [
        item
        for index, item in sorted(operations, key=lambda pair: pair[0])
        if not any(open_index < index < close_index for open_index, close_index in lambda_ranges)
    ]


def _statement_operations(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
    reverse: dict[int, int],
    start: int,
    end: int,
    spans: list[dict[str, Any]],
    pp_context: dict[int, list[dict[str, str]]],
    flow_spans: list[dict[str, Any]],
    pp_flow: dict[int, list[dict[str, Any]]],
    include_control_metadata: bool,
) -> list[tuple[int, dict[str, Any]]]:
    if start >= end:
        return []
    results: list[tuple[int, dict[str, Any]]] = []
    depth = 0
    assignment_index: int | None = None
    for index in range(start, end):
        value = tokens[index].value
        if value in {"(", "[", "{"}:
            depth += 1
        elif value in {")",
            "]",
            "}",
        }:
            depth = max(0, depth - 1)
        elif depth == 0 and value in {"=", "+=", "-=", "*=", "/=", "??="}:
            assignment_index = index
            break
    if assignment_index is not None and assignment_index > start:
        target_start = start
        declaration_name = _declaration_name(
            text, tokens, start, assignment_index
        )
        if declaration_name is not None:
            target_start = assignment_index - 1
        value_tokens = tokens[assignment_index + 1 : end]
        operation: dict[str, Any] = {
            "kind": "assignment",
            "target": _raw(text, tokens, target_start, assignment_index),
            "operator": tokens[assignment_index].value,
            "value_expression": _raw(text, tokens, assignment_index + 1, end),
            "expression": _raw(text, tokens, target_start, end),
            "evaluation": _evaluation(value_tokens),
            "conditions": _conditions_for(assignment_index, tokens[assignment_index], spans, pp_context),
            "location": _location(tokens[target_start], tokens[end - 1]),
        }
        if declaration_name is not None:
            operation["declared_name"] = declaration_name
        if include_control_metadata:
            metadata = _control_metadata_for(
                assignment_index,
                tokens[assignment_index],
                flow_spans,
                pp_flow,
            )
            metadata = _merge_control_metadata(
                metadata,
                _expression_gate_controls(
                    tokens, forward, start, target_start, end
                ),
            )
            operation.update(metadata)
        results.append((assignment_index, operation))

    excluded = {"if", "for", "foreach", "while", "switch", "catch", "sizeof", "decltype", "alignof", "new", "base"}
    for open_index in range(start, end):
        if tokens[open_index].value != "(" or open_index not in forward:
            continue
        close = forward[open_index]
        if close > end or open_index == start:
            continue
        name_index = open_index - 1
        if tokens[name_index].kind != "identifier" or tokens[name_index].value in excluded:
            continue
        callee_start = _member_chain_start(tokens, reverse, name_index, start)
        callee = _raw_from_values(tokens[callee_start:open_index])
        argument_ranges = _split_arguments(tokens, open_index + 1, close)
        arguments = [
            {
                "expression": _raw(text, tokens, argument_start, argument_end),
                "evaluation": _evaluation(tokens[argument_start:argument_end]),
            }
            for argument_start, argument_end in argument_ranges
        ]
        evaluation_tokens = [
            token
            for argument_start, argument_end in argument_ranges
            for token in tokens[argument_start:argument_end]
        ]
        operation = {
            "kind": "invocation",
            "callee": callee,
            "arguments": arguments,
            "expression": _raw(text, tokens, callee_start, close + 1),
            "evaluation": _evaluation(evaluation_tokens),
            "conditions": _conditions_for(name_index, tokens[name_index], spans, pp_context),
            "location": _location(tokens[callee_start], tokens[close]),
        }
        if include_control_metadata:
            metadata = _control_metadata_for(
                name_index, tokens[name_index], flow_spans, pp_flow
            )
            metadata = _merge_control_metadata(
                metadata,
                _expression_gate_controls(
                    tokens, forward, start, callee_start, end
                ),
            )
            operation.update(metadata)
        results.append((open_index, operation))
    return results
