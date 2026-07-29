from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .source_includes import rooted_path
from .source_namespaces import (
    namespace_at,
    observed_namespace_names,
    resolve_observed_namespace,
)
from .source_declarations import (
    _callable_has_initializer_expression,
    _classify_declaration,
    _declaration_assignment,
)
from .source_tokens import (
    Token,
    _raw,
    _raw_from_values,
    _split_arguments,
)


_SOURCE_MACROS = {
    "UCLASS",
    "USTRUCT",
    "UENUM",
    "UINTERFACE",
    "UPROPERTY",
    "UFUNCTION",
    "GENERATED_BODY",
    "GENERATED_IINTERFACE_BODY",
    "GENERATED_UCLASS_BODY",
    "GENERATED_UINTERFACE_BODY",
    "GENERATED_USTRUCT_BODY",
}
_SOURCE_MACRO_PREFIXES = ("DECLARE_", "IMPLEMENT_")


def _file_evidence(
    path: Path,
    line: int,
    project_root: Path,
    engine_root: Path | None,
    *,
    end_line: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        **rooted_path(path, project_root, engine_root),
        "line": line,
    }
    if end_line is not None and end_line != line:
        result["end_line"] = end_line
    return result


def _public_location(
    path: Path,
    location: dict[str, Any],
    project_root: Path,
    engine_root: Path | None,
) -> dict[str, Any]:
    return _file_evidence(
        path,
        int(location["line"]),
        project_root,
        engine_root,
        end_line=int(location.get("end_line", location["line"])),
    )


def _source_macros(parsed: dict[str, Any], path: Path, project_root: Path, engine_root: Path | None) -> list[dict[str, Any]]:
    text = parsed["text"]
    tokens: list[Token] = parsed["tokens"]
    forward: dict[int, int] = parsed["forward"]
    macros: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if token.kind != "identifier":
            continue
        if token.value not in _SOURCE_MACROS and not token.value.startswith(
            _SOURCE_MACRO_PREFIXES
        ):
            continue
        item: dict[str, Any] = {
            "name": token.value,
            "evidence": _file_evidence(
                path, token.line, project_root, engine_root
            ),
            "_expression": token.value,
            "_path": path,
            "_token_index": index,
            "_close_index": index,
        }
        if index + 1 < len(tokens) and tokens[index + 1].value == "(" and index + 1 in forward:
            close = forward[index + 1]
            item["arguments"] = [
                _raw(text, tokens, start, end)
                for start, end in _split_arguments(tokens, index + 2, close)
            ]
            item["_expression"] = _raw(text, tokens, index, close + 1)
            item["_close_index"] = close
        macros.append(item)
    return macros


def _callable_name(name: str, signature: str) -> str:
    return f"~{name}" if re.search(rf"~\s*{re.escape(name)}\s*\(", signature) else name


def _normalized_text(value: str) -> str:
    return " ".join(value.split())


def _excluded_token_ranges(
    parsed: dict[str, Any],
    *,
    include_classes: bool,
    include_callables: bool,
) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    if include_classes:
        ranges.extend(
            (item["body_range"][0] - 1, item["body_range"][1] + 1)
            for item in parsed["classes"]
        )
    if include_callables:
        for class_item in parsed["classes"]:
            ranges.extend(
                (member["body_range"][0] - 1, member["body_range"][1] + 1)
                for member in class_item["members"]
                if member["body_range"] is not None
            )
        ranges.extend(
            (item["body_range"][0] - 1, item["body_range"][1] + 1)
            for key in ("external_definitions", "free_functions")
            for item in parsed[key]
        )
    return ranges


def _index_in_ranges(index: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in ranges)


def _statement_start(
    tokens: list[Token],
    lower: int,
    semicolon: int,
) -> int:
    paren_depth = 0
    bracket_depth = 0
    brace_depth = 0
    cursor = semicolon - 1
    while cursor >= lower:
        value = tokens[cursor].value
        if value == ")":
            paren_depth += 1
        elif value == "(":
            paren_depth = max(0, paren_depth - 1)
        elif value == "]":
            bracket_depth += 1
        elif value == "[":
            bracket_depth = max(0, bracket_depth - 1)
        elif value == "}" and paren_depth == 0 and bracket_depth == 0:
            if (
                brace_depth == 0
                and cursor + 1 < semicolon
                and (
                    tokens[cursor + 1].kind == "identifier"
                    or tokens[cursor + 1].value == "#"
                )
            ):
                return cursor + 1
            brace_depth += 1
        elif value == "{" and paren_depth == 0 and bracket_depth == 0:
            if brace_depth:
                brace_depth -= 1
            else:
                return cursor + 1
        elif (
            value == ";"
            and paren_depth == 0
            and bracket_depth == 0
            and brace_depth == 0
        ):
            return cursor + 1
        cursor -= 1
    return lower


def _declaration_variables(
    parsed: dict[str, Any],
    path: Path,
    start: int,
    end: int,
    *,
    scope: str,
    owner: str | None,
    project_root: Path,
    engine_root: Path | None,
    excluded_ranges: list[tuple[int, int]] | None = None,
    known_namespaces: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    text = parsed["text"]
    tokens: list[Token] = parsed["tokens"]
    excluded = excluded_ranges or []
    results: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for semicolon in range(start, end):
        if tokens[semicolon].value != ";" or _index_in_ranges(
            semicolon, excluded
        ):
            continue
        statement_start = _statement_start(tokens, start, semicolon)
        if statement_start >= semicolon:
            continue
        last_directive = next(
            (
                index
                for index in range(semicolon - 1, statement_start - 1, -1)
                if tokens[index].value == "#"
            ),
            None,
        )
        if last_directive is not None:
            directive_line = tokens[last_directive].line
            statement_start = last_directive + 1
            while (
                statement_start < semicolon
                and tokens[statement_start].line == directive_line
            ):
                statement_start += 1
        declaration_macros: list[str] = []
        while statement_start < semicolon:
            if (
                statement_start + 1 < semicolon
                and tokens[statement_start].value
                in {"public", "protected", "private"}
                and tokens[statement_start + 1].value == ":"
            ):
                statement_start += 2
                continue
            if (
                statement_start + 1 < semicolon
                and tokens[statement_start].kind == "identifier"
                and re.fullmatch(
                    r"[A-Z][A-Z0-9_]*",
                    tokens[statement_start].value,
                )
                and tokens[statement_start + 1].value == "("
                and statement_start + 1 in parsed["forward"]
                and parsed["forward"][statement_start + 1] < semicolon
            ):
                close = parsed["forward"][statement_start + 1]
                if tokens[statement_start].value == "UPROPERTY":
                    declaration_macros.append(
                        _raw(
                            text,
                            tokens,
                            statement_start,
                            close + 1,
                        )
                    )
                statement_start = close + 1
                continue
            break
        if statement_start >= semicolon:
            continue
        if any(
            tokens[index].value == "#"
            for index in range(statement_start, semicolon)
        ):
            continue
        if tokens[statement_start].value in {"class", "enum", "struct"}:
            continue
        classification = _classify_declaration(
            tokens,
            parsed["forward"],
            statement_start,
            semicolon,
        )
        if classification["kind"] == "callable":
            if not _callable_has_initializer_expression(
                tokens,
                parsed["forward"],
                classification,
            ):
                continue
            classification = {
                "kind": "variable",
                "name": classification["name"],
                "name_index": classification["name_index"],
                "direct_initializer": True,
            }
        if classification["kind"] == "ignored":
            continue
        if classification["kind"] == "unresolved":
            item: dict[str, Any] = {
                "scope": scope,
                "declaration": _normalized_text(
                    _raw(text, tokens, statement_start, semicolon)
                ),
                "reason": classification["reason"],
                "evidence": _file_evidence(
                    path,
                    tokens[statement_start].line,
                    project_root,
                    engine_root,
                    end_line=tokens[semicolon].line,
                ),
            }
            if owner is not None:
                item["owner"] = owner
            unresolved.append(item)
            continue
        name = classification["name"]
        name_index = int(classification["name_index"])
        qualifier_start = name_index
        while (
            qualifier_start >= statement_start + 2
            and tokens[qualifier_start - 1].value == "::"
            and tokens[qualifier_start - 2].kind == "identifier"
        ):
            qualifier_start -= 2
        explicit_namespace = (
            "::".join(
                token.value
                for token in tokens[qualifier_start:name_index]
                if token.kind == "identifier"
            )
            if qualifier_start < name_index
            else None
        )
        resolved_namespace = (
            resolve_observed_namespace(
                explicit_namespace,
                namespace_at(
                    parsed["namespace_scopes"],
                    statement_start,
                ),
                known_namespaces or set(),
            )
            if explicit_namespace is not None
            else None
        )
        if (
            scope == "file"
            and explicit_namespace is not None
            and resolved_namespace is None
        ):
            continue
        assignment = _declaration_assignment(
            tokens, statement_start, semicolon
        )
        declarator_start = (
            qualifier_start
            if explicit_namespace is not None
            else name_index
        )
        if classification.get("direct_initializer"):
            type_expression = _raw(
                text,
                tokens,
                statement_start,
                declarator_start,
            )
        elif name_index == assignment - 1:
            type_expression = _raw(
                text, tokens, statement_start, declarator_start
            )
        else:
            type_expression = _raw_from_values(
                [
                    token
                    for index, token in enumerate(
                        tokens[statement_start:assignment],
                        start=statement_start,
                    )
                    if not declarator_start <= index <= name_index
                ]
            )
        if not type_expression or type_expression in {
            "return",
            "using",
            "typedef",
        }:
            continue
        item: dict[str, Any] = {
            "scope": scope,
            "name": name,
            "type_expression": _normalized_text(type_expression),
            "evidence": _file_evidence(
                path,
                tokens[statement_start].line,
                project_root,
                engine_root,
                end_line=tokens[semicolon].line,
            ),
            "_macros": declaration_macros,
            "_token_range": (statement_start, semicolon + 1),
            "_name_index": name_index,
            "_type_end_index": declarator_start,
            "_has_initializer": (
                bool(classification.get("direct_initializer"))
                or assignment < semicolon
            ),
        }
        if resolved_namespace is not None:
            item["_explicit_namespace"] = resolved_namespace
        if owner is not None:
            item["owner"] = owner
        results.append(item)
    return results, unresolved


def _source_declaration_facts(
    loaded: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    project_root = loaded["project_root"]
    engine_root = loaded["engine_root"]
    results: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    known_namespaces = {
        namespace
        for _path, parsed in loaded["parsed_files"]
        for namespace in observed_namespace_names(
            parsed["namespace_scopes"]
        )
    }
    for path, parsed in loaded["parsed_files"]:
        global_excluded = _excluded_token_ranges(
            parsed, include_classes=True, include_callables=True
        )
        global_excluded.extend(
            (
                int(item["_token_range"][0]),
                int(item["_token_range"][1]),
            )
            for item in parsed.get("forward_declarations", [])
        )
        file_variables, file_unresolved = _declaration_variables(
            parsed,
            path,
            0,
            len(parsed["tokens"]),
            scope="file",
            owner=None,
            project_root=project_root,
            engine_root=engine_root,
            excluded_ranges=global_excluded,
            known_namespaces=known_namespaces,
        )
        results.extend(file_variables)
        unresolved.extend(file_unresolved)
        for class_item in parsed["classes"]:
            member_excluded = [
                (member["body_range"][0] - 1, member["body_range"][1] + 1)
                for member in class_item["members"]
                if member["body_range"] is not None
            ]
            member_excluded.extend(
                (
                    int(nested["_token_range"][0]),
                    int(nested["_token_range"][1]),
                )
                for nested in parsed["classes"]
                if nested is not class_item
                and int(class_item["body_range"][0])
                <= int(nested["_token_range"][0])
                < int(class_item["body_range"][1])
            )
            member_excluded.extend(
                (
                    int(item["_token_range"][0]),
                    int(item["_token_range"][1]),
                )
                for item in parsed.get("forward_declarations", [])
                if int(class_item["body_range"][0])
                <= int(item["_token_range"][0])
                < int(class_item["body_range"][1])
            )
            member_variables, member_unresolved = _declaration_variables(
                parsed,
                path,
                class_item["body_range"][0],
                class_item["body_range"][1],
                scope="member",
                owner=class_item["name"],
                project_root=project_root,
                engine_root=engine_root,
                excluded_ranges=member_excluded,
            )
            results.extend(member_variables)
            unresolved.extend(member_unresolved)
    unique = {
        (
            item["scope"],
            item["name"],
            item["evidence"]["root"],
            item["evidence"]["path"],
            item["evidence"]["line"],
        ): item
        for item in results
    }
    sorted_variables = sorted(
        unique.values(),
        key=lambda item: (
            item["evidence"]["root"],
            item["evidence"]["path"].casefold(),
            item["evidence"]["line"],
            item["scope"],
            item["name"].casefold(),
        ),
    )
    unique_unresolved = {
        (
            item["scope"],
            item["reason"],
            item["evidence"]["root"],
            item["evidence"]["path"],
            item["evidence"]["line"],
        ): item
        for item in unresolved
    }
    sorted_unresolved = sorted(
        unique_unresolved.values(),
        key=lambda item: (
            item["evidence"]["root"],
            item["evidence"]["path"].casefold(),
            item["evidence"]["line"],
            item["scope"],
            item["reason"],
        ),
    )
    return sorted_variables, sorted_unresolved
