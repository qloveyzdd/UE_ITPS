from __future__ import annotations

from pathlib import Path
from typing import Any

from .source_context import load_source_context, source_result
from .source_declarations import (
    _class_field_names,
)
from .source_tokens import (
    Token,
)

from .source_fact_common import (
    _SOURCE_MACROS,
    _callable_name,
    _file_evidence,
    _public_location,
    _source_declaration_facts,
    _source_macros,
)

def _enums(parsed: dict[str, Any], path: Path, project_root: Path, engine_root: Path | None) -> list[dict[str, Any]]:
    tokens: list[Token] = parsed["tokens"]
    forward: dict[int, int] = parsed["forward"]
    results: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if token.value != "enum":
            continue
        cursor = index + 1
        scoped = False
        if cursor < len(tokens) and tokens[cursor].value in {"class", "struct"}:
            scoped = True
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor].kind != "identifier":
            continue
        name = tokens[cursor].value
        opening = next(
            (
                candidate
                for candidate in range(cursor + 1, len(tokens))
                if tokens[candidate].value in {"{", ";"}
            ),
            None,
        )
        if opening is None or tokens[opening].value != "{" or opening not in forward:
            continue
        close = forward[opening]
        results.append(
            {
                "kind": "enum",
                "name": name,
                "scoped": scoped,
                "evidence": _file_evidence(
                    path,
                    token.line,
                    project_root,
                    engine_root,
                    end_line=tokens[close].line,
                ),
            }
        )
    return results


def _type_unit_evidence(
    loaded: dict[str, Any],
    path: Path,
    location: dict[str, Any],
) -> dict[str, Any]:
    source_path = loaded["parsed_files"][0][0]
    evidence: dict[str, Any] = {
        "unit": "cpp" if path == source_path else "header",
        "line": int(location["line"]),
    }
    end_line = int(location.get("end_line", location["line"]))
    if end_line != evidence["line"]:
        evidence["end_line"] = end_line
    return evidence


def _macro_prefix_start(tokens: list[Token], index: int) -> int:
    cursor = index - 1
    while cursor >= 0:
        if tokens[cursor].value in {";", "{", "}"}:
            return cursor + 1
        cursor -= 1
    return 0


def _type_macros(
    loaded: dict[str, Any],
    parsed: dict[str, Any],
    path: Path,
    type_item: dict[str, Any],
) -> list[dict[str, Any]]:
    tokens: list[Token] = parsed["tokens"]
    if "_token_range" in type_item:
        type_index = int(type_item["_token_range"][0])
    else:
        type_index = next(
            (
                index
                for index, token in enumerate(tokens)
                if token.value == "enum"
                and token.line == int(type_item["evidence"]["line"])
            ),
            -1,
        )
    if type_index < 0:
        return []

    prefix_start = _macro_prefix_start(tokens, type_index)
    declaration_macros = (
        {"UENUM"}
        if type_item["kind"] == "enum"
        else {"UCLASS", "UINTERFACE", "USTRUCT"}
    )
    body_range = type_item.get("body_range")
    selected = []
    for macro in loaded["macros"]:
        if macro["_path"] != path:
            continue
        macro_index = int(macro["_token_index"])
        if (
            macro["name"] in declaration_macros
            and prefix_start <= macro_index < type_index
        ):
            selected.append(macro)
            continue
        if (
            body_range is not None
            and macro["name"]
            in {
                "GENERATED_BODY",
                "GENERATED_UCLASS_BODY",
                "GENERATED_USTRUCT_BODY",
            }
            and int(body_range[0]) <= macro_index < int(body_range[1])
        ):
            selected.append(macro)
    selected.sort(key=lambda item: int(item["_token_index"]))
    return selected


def _type_evidence(
    loaded: dict[str, Any],
    path: Path,
    location: dict[str, Any],
    macros: list[dict[str, Any]],
) -> dict[str, Any]:
    adjusted = dict(location)
    declaration_lines = [
        int(macro["evidence"]["line"])
        for macro in macros
        if macro["name"] in {"UCLASS", "UENUM", "UINTERFACE", "USTRUCT"}
    ]
    if declaration_lines:
        adjusted["line"] = min(declaration_lines)
    return _type_unit_evidence(loaded, path, adjusted)


def _type_facts(
    loaded: dict[str, Any],
    variables: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    project_root = loaded["project_root"]
    engine_root = loaded["engine_root"]
    results: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for path, parsed in loaded["parsed_files"]:
        for class_item in parsed["classes"]:
            type_macros = _type_macros(
                loaded, parsed, path, class_item
            )
            type_evidence = _type_evidence(
                loaded,
                path,
                class_item["location"],
                type_macros,
            )
            rooted_class_evidence = _public_location(
                path,
                class_item["location"],
                project_root,
                engine_root,
            )
            member_variable_details = [
                {
                    "name": item["name"],
                    "type_expression": item["type_expression"],
                    "macros": list(item.get("_macros", [])),
                    "evidence": _type_unit_evidence(
                        loaded, path, item["evidence"]
                    ),
                }
                for item in variables
                if item["scope"] == "member"
                and item.get("owner") == class_item["name"]
                and item["evidence"]["root"] == rooted_class_evidence["root"]
                and item["evidence"]["path"] == rooted_class_evidence["path"]
                and rooted_class_evidence["line"]
                <= item["evidence"]["line"]
                <= rooted_class_evidence.get(
                    "end_line", rooted_class_evidence["line"]
                )
            ]
            member_function_details = [
                {
                    "name": _callable_name(
                        member["name"], member["signature"]
                    ),
                    "signature": " ".join(member["signature"].split()),
                    "macros": list(member.get("_macros", [])),
                    "evidence": _type_unit_evidence(
                        loaded, path, member["location"]
                    ),
                }
                for member in class_item["members"]
                if member["name"] not in _SOURCE_MACROS
            ]
            lexical_field_names = _class_field_names(
                parsed["text"],
                parsed["tokens"],
                class_item["body_range"][0],
                class_item["body_range"][1],
            )
            projected_field_names = [
                item["name"] for item in member_variable_details
            ]
            if lexical_field_names != projected_field_names:
                problems.append(
                    {
                        "severity": "warning",
                        "code": "source-type-member-projection-mismatch",
                        "type": class_item["name"],
                        "lexical_member_variables": lexical_field_names,
                        "projected_member_variables": projected_field_names,
                        "evidence": type_evidence,
                        "message": (
                            "Member-variable name and variable-detail "
                            "projections disagree"
                        ),
                    }
                )
            results.append(
                {
                    "kind": class_item["kind"],
                    "name": class_item["name"],
                    "base_types": class_item["base_types"],
                    "macros": [
                        str(macro["_expression"])
                        for macro in type_macros
                    ],
                    "member_details": {
                        "variables": member_variable_details,
                        "functions": member_function_details,
                    },
                    "evidence": type_evidence,
                }
            )
        for enum_item in _enums(
            parsed, path, project_root, engine_root
        ):
            enum_macros = _type_macros(
                loaded, parsed, path, enum_item
            )
            results.append(
                {
                    **{
                        key: value
                        for key, value in enum_item.items()
                        if key != "evidence"
                    },
                    "macros": [
                        str(macro["_expression"])
                        for macro in enum_macros
                    ],
                    "evidence": _type_evidence(
                        loaded,
                        path,
                        enum_item["evidence"],
                        enum_macros,
                    ),
                }
            )
    return sorted(
        results,
        key=lambda item: (
            0 if item["evidence"]["unit"] == "cpp" else 1,
            item["evidence"]["line"],
        ),
    ), problems


def list_source_types(
    source_file: Path,
    engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = load_source_context(source_file, engine_override)
    loaded["macros"] = [
        macro
        for path, parsed in loaded["parsed_files"]
        for macro in _source_macros(
            parsed,
            path,
            loaded["project_root"],
            loaded["engine_root"],
        )
    ]
    loaded["macros"].sort(
        key=lambda item: (
            item["evidence"]["root"],
            item["evidence"]["path"].casefold(),
            item["evidence"]["line"],
        )
    )
    variables, unresolved = _source_declaration_facts(loaded)
    types, type_problems = _type_facts(loaded, variables)
    return source_result(
        "ue-itps.cxx-types.v1",
        loaded,
        {
            "types": types,
            "unresolved_declarations": [
                item for item in unresolved if item["scope"] == "member"
            ],
        },
        responsibility="Index class, struct, enum, inheritance, member-name, and UE type-macro facts.",
        boundaries=[
            "Member lists are lexical indexes and are not semantic summaries.",
            "Type and member macros are attached by lexical declaration adjacency, not UHT semantic analysis.",
            "The result is not a complete C++ type system, inheritance graph, or reflection result.",
        ],
        additional_problems=[
            *type_problems,
            *(
                [
                    {
                        "severity": "warning",
                        "code": "source-type-member-declaration-unresolved",
                        "count": len(
                            [
                                item
                                for item in unresolved
                                if item["scope"] == "member"
                            ]
                        ),
                        "message": (
                            "One or more member declarations could not be "
                            "classified conservatively"
                        ),
                    }
                ]
                if any(item["scope"] == "member" for item in unresolved)
                else []
            ),
        ],
    )
