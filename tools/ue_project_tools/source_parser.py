from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Iterable

from .common import iter_files, normalized


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    start: int
    end: int
    line: int
    column: int


_MULTI_OPERATORS = tuple(
    sorted(
        (
            "::",
            "->",
            "==",
            "!=",
            "<=",
            ">=",
            "&&",
            "||",
            "+=",
            "-=",
            "*=",
            "/=",
            "??=",
            "=>",
            "++",
            "--",
            "<<",
            ">>",
        ),
        key=len,
        reverse=True,
    )
)


def lex_source(text: str) -> list[Token]:
    """Tokenize the C#/C++ subset used by UE rule and module entry files."""
    tokens: list[Token] = []
    index = 0
    line = 1
    column = 1

    def advance(raw: str) -> None:
        nonlocal line, column
        line_breaks = raw.count("\n")
        if line_breaks:
            line += line_breaks
            column = len(raw.rsplit("\n", 1)[-1]) + 1
        else:
            column += len(raw)

    while index < len(text):
        start = index
        start_line = line
        start_column = column
        if text[index].isspace():
            while index < len(text) and text[index].isspace():
                index += 1
            advance(text[start:index])
            continue
        if text.startswith("//", index):
            end = text.find("\n", index + 2)
            index = len(text) if end < 0 else end
            advance(text[start:index])
            continue
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            index = len(text) if end < 0 else end + 2
            advance(text[start:index])
            continue

        string_prefix = next(
            (
                prefix
                for prefix in ('$@"', '@$"', '@"', '$"', 'TEXT("', 'L"', 'u8"', 'u"', 'U"', '"')
                if text.startswith(prefix, index)
            ),
            None,
        )
        if string_prefix is not None:
            verbatim = "@" in string_prefix
            quote_index = index + string_prefix.rfind('"')
            index = quote_index + 1
            while index < len(text):
                if verbatim and text.startswith('""', index):
                    index += 2
                    continue
                if text[index] == '"':
                    index += 1
                    if string_prefix == 'TEXT("' and index < len(text) and text[index] == ")":
                        index += 1
                    break
                if not verbatim and text[index] == "\\":
                    index = min(len(text), index + 2)
                else:
                    index += 1
            raw = text[start:index]
            tokens.append(Token("string", raw, start, index, start_line, start_column))
            advance(raw)
            continue
        if text[index] == "'":
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    index = min(len(text), index + 2)
                elif text[index] == "'":
                    index += 1
                    break
                else:
                    index += 1
            raw = text[start:index]
            tokens.append(Token("char", raw, start, index, start_line, start_column))
            advance(raw)
            continue
        if text[index].isalpha() or text[index] == "_":
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                index += 1
            raw = text[start:index]
            tokens.append(Token("identifier", raw, start, index, start_line, start_column))
            advance(raw)
            continue
        if text[index].isdigit():
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] in "._"):
                index += 1
            raw = text[start:index]
            tokens.append(Token("number", raw, start, index, start_line, start_column))
            advance(raw)
            continue

        operator = next(
            (candidate for candidate in _MULTI_OPERATORS if text.startswith(candidate, index)),
            None,
        )
        raw = operator or text[index]
        index += len(raw)
        tokens.append(Token("symbol", raw, start, index, start_line, start_column))
        advance(raw)
    return tokens


def token_pairs(tokens: list[Token]) -> tuple[dict[int, int], dict[int, int]]:
    opening = {"(": ")", "[": "]", "{": "}"}
    closing = {value: key for key, value in opening.items()}
    stack: list[tuple[str, int]] = []
    forward: dict[int, int] = {}
    reverse: dict[int, int] = {}
    for index, token in enumerate(tokens):
        if token.value in opening:
            stack.append((token.value, index))
        elif token.value in closing:
            expected = closing[token.value]
            for stack_index in range(len(stack) - 1, -1, -1):
                if stack[stack_index][0] == expected:
                    _, open_index = stack.pop(stack_index)
                    forward[open_index] = index
                    reverse[index] = open_index
                    break
    return forward, reverse


def _raw(text: str, tokens: list[Token], start: int, end: int) -> str:
    if start >= end or start < 0 or end > len(tokens):
        return ""
    return re.sub(r"\s+", " ", text[tokens[start].start : tokens[end - 1].end]).strip()


def _location(first: Token, last: Token | None = None) -> dict[str, int]:
    final = last or first
    return {
        "line": first.line,
        "column": first.column,
        "end_line": final.line,
        "end_column": final.column + len(final.value),
    }


def _decode_string(token: Token) -> str | None:
    raw = token.value
    if raw.startswith('TEXT("') and raw.endswith('")'):
        raw = raw[5:-1]
    prefixes = ('$@"', '@$"', '@"', '$"', 'u8"', 'L"', 'u"', 'U"', '"')
    prefix = next((item for item in prefixes if raw.startswith(item)), None)
    if prefix is None or not raw.endswith('"'):
        return None
    content = raw[len(prefix) : -1]
    if "@" in prefix:
        return content.replace('""', '"')
    replacements = {
        '\\"': '"',
        "\\\\": "\\",
        "\\n": "\n",
        "\\r": "\r",
        "\\t": "\t",
    }
    for old, new in replacements.items():
        content = content.replace(old, new)
    return content


def _evaluation(tokens: list[Token]) -> dict[str, Any]:
    literals = [
        decoded
        for token in tokens
        if token.kind == "string" and (decoded := _decode_string(token)) is not None
    ]
    if not literals:
        return {"status": "unresolved", "literal_values": []}
    ignored_identifiers = {"new", "string", "String", "TEXT"}
    unresolved_identifiers = [
        token.value
        for token in tokens
        if token.kind == "identifier"
        and token.value not in ignored_identifiers
        and token.value not in {"true", "false", "null"}
    ]
    unsupported_symbols = [
        token.value
        for token in tokens
        if token.kind == "symbol" and token.value not in {",", "{", "}", "[", "]", "(", ")"}
    ]
    interpolated = any(
        token.kind == "string" and "$" in token.value[: token.value.find('"')]
        for token in tokens
    )
    status = "partial" if unresolved_identifiers or unsupported_symbols or interpolated else "literal"
    return {"status": status, "literal_values": literals}


def _split_arguments(tokens: list[Token], start: int, end: int) -> list[tuple[int, int]]:
    arguments: list[tuple[int, int]] = []
    depth = 0
    item_start = start
    for index in range(start, end):
        value = tokens[index].value
        if value in {"(", "[", "{"}:
            depth += 1
        elif value in {")",
            "]",
            "}",
        }:
            depth = max(0, depth - 1)
        elif value == "," and depth == 0:
            if item_start < index:
                arguments.append((item_start, index))
            item_start = index + 1
    if item_start < end:
        arguments.append((item_start, end))
    return arguments


def _base_types(text: str, tokens: list[Token], start: int, end: int) -> list[str]:
    segments = _split_arguments(tokens, start, end)
    results: list[str] = []
    for segment_start, segment_end in segments:
        values = [
            token.value
            for token in tokens[segment_start:segment_end]
            if token.value not in {"public", "private", "protected", "virtual"}
        ]
        value = "".join(values).strip()
        if value:
            results.append(value)
    return results


def _member_start(tokens: list[Token], lower: int, index: int) -> int:
    cursor = index - 1
    while cursor >= lower:
        if tokens[cursor].value in {";", "{", "}"}:
            return cursor + 1
        cursor -= 1
    return lower


def parse_classes(text: str, tokens: list[Token]) -> tuple[list[dict[str, Any]], dict[int, int], dict[int, int]]:
    forward, reverse = token_pairs(tokens)
    classes: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if token.value not in {"class", "struct"}:
            continue
        brace = next(
            (cursor for cursor in range(index + 1, len(tokens)) if tokens[cursor].value in {"{", ";"}),
            None,
        )
        if brace is None or tokens[brace].value != "{" or brace not in forward:
            continue
        colon = next(
            (cursor for cursor in range(index + 1, brace) if tokens[cursor].value == ":"),
            None,
        )
        name_end = colon if colon is not None else brace
        name_candidates = [
            cursor
            for cursor in range(index + 1, name_end)
            if tokens[cursor].kind == "identifier" and tokens[cursor].value not in {"final"}
        ]
        if not name_candidates:
            continue
        name_index = name_candidates[-1]
        bases = _base_types(text, tokens, colon + 1, brace) if colon is not None else []
        body_end = forward[brace]
        members = _class_members(text, tokens, forward, reverse, tokens[name_index].value, brace + 1, body_end)
        classes.append(
            {
                "name": tokens[name_index].value,
                "kind": token.value,
                "base_types": bases,
                "location": _location(token, tokens[body_end]),
                "members": members,
                "body_range": (brace + 1, body_end),
            }
        )
    return classes, forward, reverse


def _class_members(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
    reverse: dict[int, int],
    class_name: str,
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    index = start
    nested_braces = 0
    while index < end:
        value = tokens[index].value
        if value == "{":
            nested_braces += 1
            index += 1
            continue
        if value == "}":
            nested_braces = max(0, nested_braces - 1)
            index += 1
            continue
        if value != "(" or nested_braces or index not in forward:
            index += 1
            continue
        close = forward[index]
        name_index = index - 1
        if name_index < start or tokens[name_index].kind != "identifier":
            index = close + 1
            continue
        member_start = _member_start(tokens, start, name_index)
        if any(token.value == "=" for token in tokens[member_start:index]):
            index = close + 1
            continue
        cursor = close + 1
        while cursor < end and tokens[cursor].value not in {"{", ";"}:
            if tokens[cursor].value == ":" and cursor + 1 < end:
                cursor += 1
            cursor += 1
        if cursor >= end:
            break
        has_body = tokens[cursor].value == "{" and cursor in forward
        final_index = forward[cursor] if has_body else cursor
        members.append(
            {
                "name": tokens[name_index].value,
                "parameters": _raw(text, tokens, index + 1, close),
                "signature": _raw(text, tokens, member_start, cursor),
                "location": _location(tokens[member_start], tokens[final_index]),
                "has_body": has_body,
                "is_constructor": tokens[name_index].value == class_name,
                "body_range": (cursor + 1, final_index) if has_body else None,
            }
        )
        index = final_index + 1
    return members


def parse_external_definitions(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index in range(1, len(tokens) - 3):
        if tokens[index].value != "::":
            continue
        if tokens[index - 1].kind != "identifier" or tokens[index + 1].kind != "identifier":
            continue
        open_index = index + 2
        if tokens[open_index].value != "(" or open_index not in forward:
            continue
        close = forward[open_index]
        cursor = close + 1
        while cursor < len(tokens) and tokens[cursor].value not in {"{", ";"}:
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor].value != "{" or cursor not in forward:
            continue
        body_end = forward[cursor]
        signature_start = _member_start(tokens, 0, index - 1)
        results.append(
            {
                "class_name": tokens[index - 1].value,
                "name": tokens[index + 1].value,
                "parameters": _raw(text, tokens, open_index + 1, close),
                "signature": _raw(text, tokens, signature_start, cursor),
                "location": _location(tokens[signature_start], tokens[body_end]),
                "body_range": (cursor + 1, body_end),
            }
        )
    return results


def _statement_after(tokens: list[Token], forward: dict[int, int], start: int, end: int) -> tuple[int, int, int]:
    if start >= end:
        return start, start, start
    if tokens[start].value == "{" and start in forward:
        close = min(forward[start], end)
        return start + 1, close, close + 1
    depth = 0
    cursor = start
    while cursor < end:
        value = tokens[cursor].value
        if value in {"(", "[", "{"}:
            depth += 1
        elif value in {")",
            "]",
            "}",
        }:
            if depth == 0:
                break
            depth -= 1
        elif value == ";" and depth == 0:
            return start, cursor + 1, cursor + 1
        cursor += 1
    return start, cursor, cursor


def condition_spans(tokens: list[Token], forward: dict[int, int], start: int, end: int) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []

    def walk(lower: int, upper: int) -> None:
        index = lower
        while index < upper:
            if tokens[index].value == "if" and index + 1 < upper and tokens[index + 1].value == "(" and index + 1 in forward:
                condition_close = forward[index + 1]
                then_start, then_end, after_then = _statement_after(tokens, forward, condition_close + 1, upper)
                expression = _raw_from_values(tokens[index + 2 : condition_close])
                spans.append(
                    {
                        "start": then_start,
                        "end": then_end,
                        "condition": {"kind": "if", "expression": expression, "branch": "then"},
                    }
                )
                walk(then_start, then_end)
                if after_then < upper and tokens[after_then].value == "else":
                    else_start, else_end, after_else = _statement_after(tokens, forward, after_then + 1, upper)
                    spans.append(
                        {
                            "start": else_start,
                            "end": else_end,
                            "condition": {"kind": "if", "expression": expression, "branch": "else"},
                        }
                    )
                    walk(else_start, else_end)
                    index = max(after_else, after_then + 1)
                else:
                    index = max(after_then, condition_close + 1)
                continue
            if tokens[index].value == "{" and index in forward:
                close = min(forward[index], upper)
                walk(index + 1, close)
                index = close + 1
                continue
            index += 1

    walk(start, end)
    return spans


def _raw_from_values(tokens: Iterable[Token]) -> str:
    values = [token.value for token in tokens]
    if not values:
        return ""
    rendered = " ".join(values)
    rendered = re.sub(r"\s*([.(),\[\]{}])\s*", r"\1", rendered)
    rendered = re.sub(r"\s*(::|->)\s*", r"\1", rendered)
    rendered = re.sub(r"([!~])\s+", r"\1", rendered)
    rendered = re.sub(r"\s+", " ", rendered)
    return rendered.strip()


def preprocessor_conditions(text: str) -> dict[int, list[dict[str, str]]]:
    active: list[dict[str, str]] = []
    result: dict[int, list[dict[str, str]]] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#if "):
            active.append({"kind": "preprocessor", "expression": stripped[4:].strip(), "branch": "then"})
        elif stripped.startswith("#ifdef "):
            active.append({"kind": "preprocessor", "expression": f"defined({stripped[7:].strip()})", "branch": "then"})
        elif stripped.startswith("#ifndef "):
            active.append({"kind": "preprocessor", "expression": f"!defined({stripped[8:].strip()})", "branch": "then"})
        elif stripped.startswith("#elif ") and active:
            active[-1] = {"kind": "preprocessor", "expression": stripped[6:].strip(), "branch": "elif"}
        elif stripped.startswith("#else") and active:
            active[-1] = {**active[-1], "branch": "else"}
        elif stripped.startswith("#endif") and active:
            active.pop()
        result[line_number] = [dict(item) for item in active]
    return result


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
        if tokens[operand].kind == "identifier":
            start = operand
            continue
        break
    return start


def _conditions_for(
    token_index: int,
    token: Token,
    spans: list[dict[str, Any]],
    preprocessor: dict[int, list[dict[str, str]]],
) -> list[dict[str, str]]:
    contextual = [
        span
        for span in spans
        if span["start"] <= token_index < span["end"]
    ]
    contextual.sort(key=lambda span: (-(span["end"] - span["start"]), span["start"]))
    return [*preprocessor.get(token.line, []), *[dict(span["condition"]) for span in contextual]]


def parse_operations(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
    reverse: dict[int, int],
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    spans = condition_spans(tokens, forward, start, end)
    pp_context = preprocessor_conditions(text)
    operations: list[tuple[int, dict[str, Any]]] = []
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
        elif value == "{" and paren_depth == 0 and bracket_depth == 0:
            brace_depth += 1
            statement_start = cursor + 1
        elif value == "}" and paren_depth == 0 and bracket_depth == 0:
            brace_depth = max(0, brace_depth - 1)
            statement_start = cursor + 1
        elif value == ";":
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
                )
            )
            statement_start = cursor + 1
    return [item for _, item in sorted(operations, key=lambda pair: pair[0])]


def _statement_operations(
    text: str,
    tokens: list[Token],
    forward: dict[int, int],
    reverse: dict[int, int],
    start: int,
    end: int,
    spans: list[dict[str, Any]],
    pp_context: dict[int, list[dict[str, str]]],
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
        if any(token.value in {"bool", "int", "string", "var", "auto"} for token in tokens[start:assignment_index]):
            identifiers = [
                index
                for index in range(start, assignment_index)
                if tokens[index].kind == "identifier"
            ]
            if identifiers:
                target_start = identifiers[-1]
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
        results.append((open_index, operation))
    return results


_MODULE_RULE_KINDS = {
    "PublicDependencyModuleNames": "public_dependency",
    "PrivateDependencyModuleNames": "private_dependency",
    "DynamicallyLoadedModuleNames": "dynamic_dependency",
    "PublicIncludePathModuleNames": "public_include_module",
    "PrivateIncludePathModuleNames": "private_include_module",
    "PublicIncludePaths": "public_include_path",
    "PrivateIncludePaths": "private_include_path",
    "PublicSystemIncludePaths": "public_system_include_path",
    "PublicDefinitions": "public_definition",
    "PrivateDefinitions": "private_definition",
}


def _rule_annotation(operation: dict[str, Any]) -> dict[str, str] | None:
    if operation["kind"] == "invocation":
        callee = str(operation.get("callee", ""))
        match = re.search(r"(?:^|[.>])(?P<member>[A-Za-z_]\w*)\.(?P<action>AddRange|Add|Remove|RemoveAll)$", callee)
        if match and match.group("member") in _MODULE_RULE_KINDS:
            return {
                "kind": _MODULE_RULE_KINDS[match.group("member")],
                "member": match.group("member"),
                "action": match.group("action"),
            }
    else:
        target = str(operation.get("target", "")).split(".")[-1]
        if target in {"PCHUsage", "PrivatePCHHeaderFile", "SharedPCHHeaderFile"}:
            return {"kind": "pch", "member": target, "action": "assign"}
        if target in {"bEnforceIWYU", "IWYUSupport", "bLegacyPublicIncludePaths"}:
            return {"kind": "iwyu", "member": target, "action": "assign"}
    return None


def parse_rule_file(path: Path, required_base_type: str) -> dict[str, Any]:
    resolved = path.resolve()
    text = resolved.read_text(encoding="utf-8-sig", errors="replace")
    tokens = lex_source(text)
    classes, forward, reverse = parse_classes(text, tokens)
    known_bases = {required_base_type}
    selected: list[dict[str, Any]] = []
    pending = list(classes)
    while pending:
        changed = False
        for item in list(pending):
            if any(base.split("<", 1)[0] in known_bases for base in item["base_types"]):
                selected.append(item)
                known_bases.add(item["name"])
                pending.remove(item)
                changed = True
        if not changed:
            break

    rules_classes: list[dict[str, Any]] = []
    for item in selected:
        methods: list[dict[str, Any]] = []
        for member in item["members"]:
            operation_items: list[dict[str, Any]] = []
            if member["body_range"]:
                operation_items = parse_operations(
                    text,
                    tokens,
                    forward,
                    reverse,
                    member["body_range"][0],
                    member["body_range"][1],
                )
                if required_base_type == "ModuleRules":
                    for operation in operation_items:
                        annotation = _rule_annotation(operation)
                        if annotation:
                            operation["rule"] = annotation
            methods.append(
                {
                    "name": member["name"],
                    "parameters": member["parameters"],
                    "signature": member["signature"],
                    "is_constructor": member["is_constructor"],
                    "location": member["location"],
                    "operations": operation_items,
                }
            )
        method_names = {method["name"] for method in methods}
        calls: list[dict[str, Any]] = []
        for method in methods:
            for operation in method["operations"]:
                if operation["kind"] != "invocation":
                    continue
                callee = str(operation["callee"]).split(".")[-1].split("::")[-1]
                if callee in method_names and callee != method["name"]:
                    calls.append(
                        {
                            "caller": method["name"],
                            "callee": callee,
                            "location": operation["location"],
                        }
                    )
        unique_calls = {
            (call["caller"], call["callee"], call["location"]["line"], call["location"]["column"]): call
            for call in calls
        }
        rules_classes.append(
            {
                "name": item["name"],
                "base_types": item["base_types"],
                "location": item["location"],
                "methods": methods,
                "same_file_calls": sorted(
                    unique_calls.values(),
                    key=lambda value: (value["caller"], value["callee"], value["location"]["line"]),
                ),
            }
        )
    return {"path": normalized(resolved), "rules_classes": rules_classes}


def registration_macros(text: str, tokens: list[Token]) -> list[dict[str, Any]]:
    forward, _ = token_pairs(tokens)
    results: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if not token.value.startswith("IMPLEMENT_") or not token.value.endswith("MODULE"):
            continue
        if index + 1 >= len(tokens) or tokens[index + 1].value != "(" or index + 1 not in forward:
            continue
        close = forward[index + 1]
        ranges = _split_arguments(tokens, index + 2, close)
        arguments = [_raw(text, tokens, start, end) for start, end in ranges]
        results.append(
            {
                "macro": token.value,
                "module_class": arguments[0] if arguments else None,
                "module_name": arguments[1] if len(arguments) > 1 else None,
                "arguments": arguments,
                "location": _location(token, tokens[close]),
            }
        )
    return results


def find_registration_macros(module_dir: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in iter_files(module_dir, ".cpp"):
        try:
            text = path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for item in registration_macros(text, lex_source(text)):
            results.append({"path": normalized(path), **item})
    return sorted(results, key=lambda item: (item["path"].casefold(), item["location"]["line"]))


def parse_cpp_file(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    text = resolved.read_text(encoding="utf-8-sig", errors="replace")
    tokens = lex_source(text)
    classes, forward, reverse = parse_classes(text, tokens)
    external = parse_external_definitions(text, tokens, forward)
    return {
        "path": normalized(resolved),
        "text": text,
        "tokens": tokens,
        "forward": forward,
        "reverse": reverse,
        "classes": classes,
        "external_definitions": external,
        "registration_macros": registration_macros(text, tokens),
    }


def source_files(module_dir: Path) -> list[Path]:
    suffixes = (".h", ".hpp", ".cpp", ".cc")
    return sorted(
        {
            path.resolve()
            for suffix in suffixes
            for path in iter_files(module_dir, suffix)
        },
        key=lambda path: normalized(path).casefold(),
    )
