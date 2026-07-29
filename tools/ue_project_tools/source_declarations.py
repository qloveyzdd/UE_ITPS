from __future__ import annotations

from typing import Any

from .source_declarators import (
    _MEMBER_ANNOTATION_MACROS,
    _classify_declaration,
    _member_declaration_prefix,
    _member_start,
)
from .source_tokens import (
    Token,
    _base_types,
    _location,
    _ordered_union,
    _raw,
    token_pairs,
)


_FIELD_MODIFIERS = {
    "const",
    "event",
    "extern",
    "internal",
    "new",
    "private",
    "protected",
    "public",
    "readonly",
    "required",
    "static",
    "unsafe",
    "volatile",
}


def _field_type_start(
    tokens: list[Token],
    forward: dict[int, int],
    start: int,
    end: int,
) -> int:
    cursor = start
    while cursor < end:
        if (
            cursor + 1 < end
            and tokens[cursor].value
            in {"public", "protected", "private"}
            and tokens[cursor + 1].value == ":"
        ):
            cursor += 2
            continue
        if tokens[cursor].value in _FIELD_MODIFIERS:
            cursor += 1
            continue
        if (
            tokens[cursor].value == "["
            and cursor in forward
            and forward[cursor] < end
        ):
            cursor = forward[cursor] + 1
            continue
        if (
            cursor + 1 < end
            and tokens[cursor].value in _MEMBER_ANNOTATION_MACROS
            and tokens[cursor + 1].value == "("
            and cursor + 1 in forward
            and forward[cursor + 1] < end
        ):
            cursor = forward[cursor + 1] + 1
            continue
        break
    return cursor


def _class_field_details(
    text: str,
    tokens: list[Token],
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    forward, _ = token_pairs(tokens)
    fields: list[dict[str, Any]] = []
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
        elif value == "}" and paren_depth == 0 and bracket_depth == 0:
            brace_depth = max(0, brace_depth - 1)
            if brace_depth == 0:
                statement_start = cursor + 1
        elif (
            value == ";"
            and brace_depth == 0
            and paren_depth == 0
            and bracket_depth == 0
        ):
            classification = _classify_declaration(
                tokens,
                forward,
                statement_start,
                cursor,
            )
            if classification["kind"] == "variable":
                name_index = int(classification["name_index"])
                type_start = _field_type_start(
                    tokens,
                    forward,
                    statement_start,
                    name_index,
                )
                fields.append(
                    {
                        "name": classification["name"],
                        "type_expression": " ".join(
                            _raw(
                                text,
                                tokens,
                                type_start,
                                name_index,
                            ).split()
                        ),
                        "location": _location(
                            tokens[type_start],
                            tokens[cursor],
                        ),
                    }
                )
            statement_start = cursor + 1
    return fields


def _class_field_names(
    text: str,
    tokens: list[Token],
    start: int,
    end: int,
) -> list[str]:
    return _ordered_union(
        item["name"]
        for item in _class_field_details(text, tokens, start, end)
    )


_LOCAL_DECLARATION_MODIFIERS = {
    "await",
    "const",
    "ref",
    "scoped",
    "using",
}


def _local_declaration_details(
    text: str,
    tokens: list[Token],
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    variables: list[dict[str, Any]] = []
    forward, _ = token_pairs(tokens)
    statement_start = start
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
        elif (
            value in {"{", "}"}
            and paren_depth == 0
            and bracket_depth == 0
        ):
            statement_start = cursor + 1
        elif value == ";" and paren_depth == 0 and bracket_depth == 0:
            assignment = next(
                (
                    index
                    for index in range(statement_start, cursor)
                    if tokens[index].value
                    in {"=", "+=", "-=", "*=", "/=", "??="}
                ),
                cursor,
            )
            classification = _classify_declaration(
                tokens,
                forward,
                statement_start,
                assignment,
            )
            if classification["kind"] == "variable":
                name_index = int(classification["name_index"])
                if (
                    name_index > statement_start
                    and tokens[name_index - 1].value
                    in {".", "->", "::"}
                ):
                    statement_start = cursor + 1
                    continue
                type_start = statement_start
                while (
                    type_start < name_index
                    and tokens[type_start].value
                    in _LOCAL_DECLARATION_MODIFIERS
                ):
                    type_start += 1
                if type_start < name_index:
                    variables.append(
                        {
                            "name": str(classification["name"]),
                            "type_expression": " ".join(
                                _raw(
                                    text,
                                    tokens,
                                    type_start,
                                    name_index,
                                ).split()
                            ),
                            "location": _location(
                                tokens[type_start],
                                tokens[cursor],
                            ),
                        }
                    )
            statement_start = cursor + 1
    return variables


def _local_declaration_names(
    text: str,
    tokens: list[Token],
    start: int,
    end: int,
) -> list[str]:
    return _ordered_union(
        item["name"]
        for item in _local_declaration_details(
            text,
            tokens,
            start,
            end,
        )
    )


def _class_definition_brace(
    tokens: list[Token],
    forward: dict[int, int],
    class_index: int,
) -> int | None:
    if (
        class_index > 0
        and tokens[class_index - 1].value == "enum"
    ):
        return None
    cursor = class_index + 1
    while cursor < len(tokens):
        value = tokens[cursor].value
        if value == ";":
            return None
        if value == "{":
            return cursor if cursor in forward else None
        if value in {"class", "enum", "struct", "=", ")"}:
            return None
        if value == "(":
            if (
                cursor > class_index + 1
                and tokens[cursor - 1].value
                in {"alignas", "decltype"}
                and cursor in forward
            ):
                cursor = forward[cursor] + 1
                continue
            return None
        cursor += 1
    return None


def parse_classes(
    text: str,
    tokens: list[Token],
) -> tuple[
    list[dict[str, Any]],
    dict[int, int],
    dict[int, int],
]:
    forward, reverse = token_pairs(tokens)
    classes: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if token.value not in {"class", "struct"}:
            continue
        brace = _class_definition_brace(tokens, forward, index)
        if brace is None:
            continue
        colon = next(
            (
                cursor
                for cursor in range(index + 1, brace)
                if tokens[cursor].value == ":"
            ),
            None,
        )
        name_end = colon if colon is not None else brace
        name_candidates = [
            cursor
            for cursor in range(index + 1, name_end)
            if tokens[cursor].kind == "identifier"
            and tokens[cursor].value not in {"final"}
        ]
        if not name_candidates:
            continue
        specialization_open = next(
            (
                cursor
                for cursor in range(index + 1, name_end)
                if tokens[cursor].value == "<"
                and cursor > index + 1
                and tokens[cursor - 1].kind == "identifier"
            ),
            None,
        )
        name_index = (
            specialization_open - 1
            if specialization_open is not None
            else name_candidates[-1]
        )
        bases = (
            _base_types(text, tokens, colon + 1, brace)
            if colon is not None
            else []
        )
        body_end = forward[brace]
        members = _class_members(
            text,
            tokens,
            forward,
            reverse,
            tokens[name_index].value,
            brace + 1,
            body_end,
        )
        classes.append(
            {
                "name": tokens[name_index].value,
                "kind": token.value,
                "base_types": bases,
                "location": _location(token, tokens[body_end]),
                "members": members,
                "body_range": (brace + 1, body_end),
                "_token_range": (index, body_end + 1),
            }
        )
    for item in classes:
        owner = _type_owner_at(
            classes,
            int(item["_token_range"][0]),
            item,
        )
        item["owner"] = owner["qualified_name"] if owner else None
        item["qualified_name"] = (
            f"{item['owner']}::{item['name']}"
            if item["owner"]
            else item["name"]
        )
    return classes, forward, reverse


def _type_owner_at(
    classes: list[dict[str, Any]],
    token_index: int,
    selected: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    owners = [
        item
        for item in classes
        if item is not selected
        and int(item["body_range"][0])
        <= token_index
        < int(item["body_range"][1])
    ]
    if not owners:
        return None
    return min(
        owners,
        key=lambda item: (
            int(item["body_range"][1])
            - int(item["body_range"][0])
        ),
    )


def _inside_template_parameters(
    tokens: list[Token],
    index: int,
) -> bool:
    depth = 0
    cursor = index - 1
    while (
        cursor >= 0
        and tokens[cursor].value not in {";", "{", "}"}
    ):
        value = tokens[cursor].value
        if value in {">", ">>"}:
            depth += 2 if value == ">>" else 1
        elif value == "<":
            if depth:
                depth -= 1
            else:
                return (
                    cursor > 0
                    and tokens[cursor - 1].value == "template"
                )
        cursor -= 1
    return False


def parse_type_forward_declarations(
    tokens: list[Token],
    classes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Read class, struct, and enum declarations without bodies."""
    results: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if token.value not in {"class", "struct", "enum"}:
            continue
        if (
            token.value in {"class", "struct"}
            and index > 0
            and tokens[index - 1].value == "enum"
        ):
            continue
        if _inside_template_parameters(tokens, index):
            continue

        cursor = index + 1
        scoped = False
        if (
            token.value == "enum"
            and cursor < len(tokens)
            and tokens[cursor].value in {"class", "struct"}
        ):
            scoped = True
            cursor += 1
        terminator = next(
            (
                candidate
                for candidate in range(cursor, len(tokens))
                if tokens[candidate].value in {"{", ";"}
            ),
            None,
        )
        if (
            terminator is None
            or tokens[terminator].value != ";"
        ):
            continue
        colon = next(
            (
                candidate
                for candidate in range(cursor, terminator)
                if tokens[candidate].value == ":"
            ),
            None,
        )
        name_end = colon if colon is not None else terminator
        candidates = [
            candidate
            for candidate in range(cursor, name_end)
            if tokens[candidate].kind == "identifier"
            and tokens[candidate].value not in {"final"}
        ]
        if not candidates:
            continue
        name_index = candidates[-1]
        if any(
            int(item["_token_range"][0]) == index
            for item in classes
        ):
            continue
        owner = _type_owner_at(classes, index)
        owner_name = owner["qualified_name"] if owner else None
        item: dict[str, Any] = {
            "kind": token.value,
            "name": tokens[name_index].value,
            "owner": owner_name,
            "qualified_name": (
                f"{owner_name}::{tokens[name_index].value}"
                if owner_name
                else tokens[name_index].value
            ),
            "location": _location(token, tokens[terminator]),
            "_token_range": (index, terminator + 1),
        }
        if token.value == "enum":
            item["scoped"] = scoped
        results.append(item)
    return results


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
        if (
            name_index < start
            or tokens[name_index].kind != "identifier"
        ):
            index = close + 1
            continue
        member_start = _member_start(tokens, start, name_index)
        cursor = close + 1
        while (
            cursor < end
            and tokens[cursor].value not in {"{", ";"}
        ):
            cursor += 1
        if cursor >= end:
            break
        classification = _classify_declaration(
            tokens,
            forward,
            member_start,
            cursor,
        )
        if (
            classification["kind"] != "callable"
            or classification.get("name_index") != name_index
            or classification.get("parameter_open") != index
        ):
            index = close + 1
            continue
        declaration_start, macros = _member_declaration_prefix(
            text,
            tokens,
            forward,
            member_start,
            name_index,
        )
        has_body = (
            tokens[cursor].value == "{"
            and cursor in forward
        )
        final_index = forward[cursor] if has_body else cursor
        members.append(
            {
                "name": tokens[name_index].value,
                "parameters": _raw(
                    text,
                    tokens,
                    index + 1,
                    close,
                ),
                "signature": _raw(
                    text,
                    tokens,
                    declaration_start,
                    cursor,
                ),
                "location": _location(
                    tokens[declaration_start],
                    tokens[final_index],
                ),
                "has_body": has_body,
                "is_constructor": (
                    tokens[name_index].value == class_name
                ),
                "body_range": (
                    (cursor + 1, final_index)
                    if has_body
                    else None
                ),
                "_macros": macros,
            }
        )
        index = final_index + 1
    return members
