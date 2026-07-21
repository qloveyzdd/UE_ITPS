from __future__ import annotations

import re
from typing import Any

from .source_flow import (
    _control_references,
    _loop_local_names,
    _statement_after,
    condition_spans,
    control_spans,
)
from .source_preprocessor import (
    _preprocessor_contexts,
    _registration_preprocessor_contexts,
    preprocessor_conditions,
    preprocessor_control_contexts,
)
from .source_tokens import Token, _ordered_union, _raw_from_values


def _member_chain_start(tokens: list[Token], reverse: dict[int, int], name_index: int, lower: int) -> int:
    start = name_index
    while start - 1 >= lower and tokens[start - 1].value in {".", "::", "->"}:
        operand = start - 2
        if operand < lower:
            break
        if tokens[operand].value == ")" and operand in reverse:
            open_index = reverse[operand]
            callee_name = open_index - 1
            if callee_name >= lower and tokens[callee_name].kind == "identifier":
                start = _member_chain_start(tokens, reverse, callee_name, lower)
                continue
        if tokens[operand].value == "]" and operand in reverse:
            open_index = reverse[operand]
            indexed_name = open_index - 1
            if indexed_name >= lower and tokens[indexed_name].kind == "identifier":
                start = _member_chain_start(tokens, reverse, indexed_name, lower)
                continue
        if tokens[operand].kind == "identifier":
            start = operand
            continue
        break
    return start


def _conditions_for(
    token_index: int,
    token: Token,
    spans: list[dict[str, Any]],
    preprocessor: dict[int, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    contextual = [
        span
        for span in spans
        if span["start"] <= token_index < span["end"]
    ]
    controls = [dict(item) for item in preprocessor.get(token.line, [])]
    controls.extend(
        {
            **dict(span["condition"]),
            "start_line": span["start_line"],
            "span_width": span["end"] - span["start"],
        }
        for span in contextual
    )
    controls.sort(
        key=lambda item: (
            int(item.get("start_line", 0)),
            -int(item.get("span_width", 0)),
        )
    )
    return controls


def _control_metadata_for(
    token_index: int,
    token: Token,
    spans: list[dict[str, Any]],
    preprocessor: dict[int, list[dict[str, Any]]],
) -> dict[str, Any]:
    contextual = [
        span for span in spans if span["start"] <= token_index < span["end"]
    ]
    contextual.extend(preprocessor.get(token.line, []))
    contextual.sort(key=lambda item: item["start_line"])
    flattened = [item for item in contextual if item.get("kind") != "case"]
    path = [str(item["kind"]) for item in flattened]
    references = _ordered_union(
        *(item.get("references", []) for item in flattened)
    )
    result: dict[str, Any] = {
        "applicability": "conditional" if path else "direct"
    }
    if path:
        result["control_path"] = path
        result["control_details"] = [
            {
                key: value
                for key, value in item.items()
                if key
                in {
                    "kind",
                    "expression",
                    "branch",
                    "guard",
                    "references",
                    "start_line",
                }
            }
            for item in contextual
        ]
    if references:
        result["related_symbols"] = references
    return result


def _merge_control_metadata(
    metadata: dict[str, Any], controls: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    items = list(controls)
    if not items:
        return metadata
    path = [*metadata.get("control_path", [])]
    path.extend(str(item["kind"]) for item in items)
    references = _ordered_union(
        metadata.get("related_symbols", []),
        *(item.get("references", []) for item in items),
    )
    result = {**metadata, "applicability": "conditional", "control_path": path}
    details = [*metadata.get("control_details", [])]
    details.extend(dict(item) for item in items)
    if details:
        result["control_details"] = details
    if references:
        result["related_symbols"] = references
    return result


def control_expression_ranges(
    tokens: list[Token], forward: dict[int, int], start: int, end: int
) -> list[dict[str, Any]]:
    """Locate expressions evaluated by control constructs without treating bodies as headers."""
    ranges: list[dict[str, Any]] = []

    def add_range(
        lower: int,
        upper: int,
        controls: Iterable[dict[str, Any]] = (),
        excluded_targets: Iterable[str] = (),
    ) -> None:
        if lower < upper:
            ranges.append(
                {
                    "start": lower,
                    "end": upper,
                    "controls": [dict(item) for item in controls],
                    "excluded_targets": set(excluded_targets),
                }
            )

    def split_for_header(lower: int, upper: int) -> list[tuple[int, int]]:
        separators: list[int] = []
        depth = 0
        for index in range(lower, upper):
            value = tokens[index].value
            if value in {"(", "[", "{"}:
                depth += 1
            elif value in {")", "]", "}"}:
                depth = max(0, depth - 1)
            elif value == ";" and depth == 0:
                separators.append(index)
        boundaries = [lower, *separators, upper]
        return [
            (boundaries[index] + (1 if index else 0), boundaries[index + 1])
            for index in range(len(boundaries) - 1)
        ]

    def parse_if(
        index: int,
        upper: int,
        prior_references: Iterable[str] = (),
        is_else_if: bool = False,
    ) -> int:
        if (
            index + 1 >= upper
            or tokens[index + 1].value != "("
            or index + 1 not in forward
        ):
            return index + 1
        condition_close = forward[index + 1]
        prior = list(prior_references)
        controls = (
            [{"kind": "if", "references": prior}]
            if is_else_if
            else []
        )
        add_range(index + 2, condition_close, controls)
        current_references = _ordered_union(
            prior,
            _control_references(tokens[index + 2 : condition_close]),
        )
        then_start, then_end, after_then = _statement_after(
            tokens, forward, condition_close + 1, upper
        )
        walk(then_start, then_end)
        if after_then >= upper or tokens[after_then].value != "else":
            return max(after_then, condition_close + 1)
        branch_start = after_then + 1
        if branch_start < upper and tokens[branch_start].value == "if":
            return parse_if(branch_start, upper, current_references, True)
        else_start, else_end, after_else = _statement_after(
            tokens, forward, branch_start, upper
        )
        walk(else_start, else_end)
        return max(after_else, branch_start)

    def walk(lower: int, upper: int) -> None:
        index = lower
        while index < upper:
            value = tokens[index].value
            if value == "if":
                index = parse_if(index, upper)
                continue
            if value == "do":
                body_start, body_end, after_body = _statement_after(
                    tokens, forward, index + 1, upper
                )
                cursor = after_body
                if (
                    cursor + 1 < upper
                    and tokens[cursor].value == "while"
                    and tokens[cursor + 1].value == "("
                    and cursor + 1 in forward
                ):
                    condition_close = forward[cursor + 1]
                    walk(body_start, body_end)
                    add_range(cursor + 2, condition_close)
                    index = condition_close + 1
                    if index < upper and tokens[index].value == ";":
                        index += 1
                    continue
            if (
                value in {"for", "foreach", "while", "switch"}
                and index + 1 < upper
                and tokens[index + 1].value == "("
                and index + 1 in forward
            ):
                header_close = forward[index + 1]
                header_start = index + 2
                header = tokens[header_start:header_close]
                excluded = _loop_local_names(value, header)
                if value == "for":
                    segments = split_for_header(header_start, header_close)
                    if segments:
                        add_range(*segments[0], excluded_targets=excluded)
                    if len(segments) > 1:
                        add_range(*segments[1], excluded_targets=excluded)
                    if len(segments) > 2:
                        condition_references = _control_references(
                            tokens[segments[1][0] : segments[1][1]], excluded
                        )
                        add_range(
                            *segments[2],
                            controls=[
                                {
                                    "kind": "for",
                                    "references": condition_references,
                                }
                            ],
                            excluded_targets=excluded,
                        )
                elif value == "foreach":
                    in_index = next(
                        (
                            cursor
                            for cursor in range(header_start, header_close)
                            if tokens[cursor].value == "in"
                        ),
                        header_start - 1,
                    )
                    add_range(
                        in_index + 1,
                        header_close,
                        excluded_targets=excluded,
                    )
                else:
                    add_range(header_start, header_close)
                body_start, body_end, after_body = _statement_after(
                    tokens, forward, header_close + 1, upper
                )
                walk(body_start, body_end)
                index = max(after_body, header_close + 1)
                continue
            if value == "catch":
                cursor = index + 1
                if cursor < upper and tokens[cursor].value == "(" and cursor in forward:
                    cursor = forward[cursor] + 1
                if (
                    cursor + 1 < upper
                    and tokens[cursor].value == "when"
                    and tokens[cursor + 1].value == "("
                    and cursor + 1 in forward
                ):
                    filter_close = forward[cursor + 1]
                    add_range(
                        cursor + 2,
                        filter_close,
                        controls=[{"kind": "catch", "references": []}],
                    )
                    cursor = filter_close + 1
                body_start, body_end, after_body = _statement_after(
                    tokens, forward, cursor, upper
                )
                walk(body_start, body_end)
                index = max(after_body, cursor)
                continue
            if value == "{" and index in forward:
                close = min(forward[index], upper)
                walk(index + 1, close)
                index = close + 1
                continue
            index += 1

    walk(start, end)
    return ranges


def _expression_gate_controls(
    tokens: list[Token],
    forward: dict[int, int],
    start: int,
    operation_index: int,
    end: int,
) -> list[dict[str, Any]]:
    def top_level_indices(
        lower: int, upper: int, values: set[str]
    ) -> list[int]:
        result: list[int] = []
        depth = 0
        for cursor in range(lower, upper):
            value = tokens[cursor].value
            if value in {"(", "[", "{"}:
                depth += 1
            elif value in {")", "]", "}"}:
                depth = max(0, depth - 1)
            elif depth == 0 and value in values:
                result.append(cursor)
        return result

    def rendered(lower: int, upper: int) -> str:
        expression = _raw_from_values(tokens[lower:upper])
        return re.sub(
            r"\s*(&&|\|\||\?\?)\s*", r" \1 ", expression
        ).strip()

    def control(
        kind: str, operator_index: int, lower: int, guard: str
    ) -> dict[str, Any]:
        return {
            "kind": kind,
            "references": _control_references(tokens[lower:operator_index]),
            "expression": rendered(lower, operator_index),
            "guard": guard,
            "start_line": tokens[operator_index].line,
        }

    def matching_ternary_colon(
        question_index: int, upper: int
    ) -> int | None:
        nested = 0
        for cursor in top_level_indices(
            question_index + 1, upper, {"?", ":"}
        ):
            if tokens[cursor].value == "?":
                nested += 1
            elif nested:
                nested -= 1
            else:
                return cursor
        return None

    def visit(lower: int, upper: int) -> list[dict[str, Any]]:
        while (
            lower < upper
            and tokens[lower].value in {"(", "[", "{"}
            and forward.get(lower) == upper - 1
        ):
            lower += 1
            upper -= 1
        if not (lower <= operation_index < upper):
            return []
        if tokens[lower].value in {"return", "co_return"}:
            lower += 1

        commas = top_level_indices(lower, upper, {","})
        if commas:
            boundaries = [lower, *(index + 1 for index in commas), upper]
            for index in range(len(boundaries) - 1):
                segment_start = boundaries[index]
                segment_end = (
                    commas[index] if index < len(commas) else boundaries[index + 1]
                )
                if segment_start <= operation_index < segment_end:
                    return visit(segment_start, segment_end)

        assignments = top_level_indices(
            lower, upper, {"=", "+=", "-=", "*=", "/=", "??="}
        )
        if assignments:
            assignment = assignments[-1]
            return visit(
                assignment + 1 if operation_index > assignment else lower,
                upper if operation_index > assignment else assignment,
            )

        questions = top_level_indices(lower, upper, {"?"})
        if questions:
            question = questions[0]
            colon = matching_ternary_colon(question, upper)
            if colon is not None:
                condition = rendered(lower, question)
                if operation_index < question:
                    return visit(lower, question)
                if operation_index < colon:
                    return [
                        control("ternary", question, lower, condition),
                        *visit(question + 1, colon),
                    ]
                return [
                    control("ternary", question, lower, f"!({condition})"),
                    *visit(colon + 1, upper),
                ]

        for operator in ("??", "||", "&&"):
            operators = top_level_indices(lower, upper, {operator})
            if not operators:
                continue
            operator_index = operators[0] if operator == "??" else operators[-1]
            if operation_index < operator_index:
                return visit(lower, operator_index)
            expression = rendered(lower, operator_index)
            guard = {
                "&&": expression,
                "||": f"!({expression})",
                "??": f"({expression}) == null",
            }[operator]
            return [
                control("short_circuit", operator_index, lower, guard),
                *visit(operator_index + 1, upper),
            ]

        containing = [
            (open_index, close_index)
            for open_index, close_index in forward.items()
            if lower <= open_index < operation_index < close_index < upper
        ]
        if containing:
            open_index, close_index = max(containing)
            return visit(open_index + 1, close_index)
        return []

    return visit(start, end)
