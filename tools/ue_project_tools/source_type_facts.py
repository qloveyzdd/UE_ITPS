from __future__ import annotations

from pathlib import Path
from typing import Any

from .source_callable_declarations import parse_free_function_declarations
from .source_context import load_source_context, source_result
from .source_declarations import (
    _class_field_names,
    _type_owner_at,
)
from .source_namespaces import (
    namespace_at,
    qualified_name,
)
from .source_tokens import (
    Token,
)

from .source_fact_common import (
    _SOURCE_MACROS,
    _callable_name,
    _file_evidence,
    _public_location,
    _source_macros,
)
from .source_variable_facts import (
    _global_variable_facts,
    _has_anonymous_namespace,
    _path_matches_evidence,
    _source_declaration_facts,
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
        owner = _type_owner_at(parsed["classes"], index)
        owner_name = owner["qualified_name"] if owner else None
        namespace = namespace_at(parsed["namespace_scopes"], index)
        lexical_name = f"{owner_name}::{name}" if owner_name else name
        results.append(
            {
                "kind": "enum",
                "name": name,
                "namespace": namespace,
                "qualified_name": qualified_name(namespace, lexical_name),
                "owner": owner_name,
                "role": "definition",
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
    evidence: dict[str, Any] = {
        "unit": (
            "header"
            if path.suffix.casefold() in {".h", ".hpp"}
            else "cpp"
        ),
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
                "GENERATED_IINTERFACE_BODY",
                "GENERATED_UCLASS_BODY",
                "GENERATED_UINTERFACE_BODY",
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


def _anchor_sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    evidence = item["evidence"]
    return (
        0 if evidence["unit"] == "cpp" else 1,
        int(evidence["line"]),
        str(item["name"]).casefold(),
    )


def _member_anchors(
    loaded: dict[str, Any],
    path: Path,
    parsed: dict[str, Any],
    class_item: dict[str, Any],
    variables: list[dict[str, Any]],
    rooted_class_evidence: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    variable_anchors = [
        {
            "kind": "variable",
            "name": item["name"],
            "type_expression": item["type_expression"],
            "macros": list(item.get("_macros", [])),
            "evidence": _type_unit_evidence(
                loaded,
                path,
                item["evidence"],
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
            "end_line",
            rooted_class_evidence["line"],
        )
    ]
    function_anchors = [
        {
            "kind": "function",
            "name": _callable_name(
                member["name"],
                member["signature"],
            ),
            "signature": " ".join(member["signature"].split()),
            "macros": list(member.get("_macros", [])),
            "evidence": _type_unit_evidence(
                loaded,
                path,
                member["location"],
            ),
        }
        for member in class_item["members"]
        if member["name"] not in _SOURCE_MACROS
    ]
    anchors = sorted(
        [*variable_anchors, *function_anchors],
        key=lambda item: (
            int(item["evidence"]["line"]),
            0 if item["kind"] == "variable" else 1,
            str(item["name"]).casefold(),
        ),
    )
    return (
        anchors,
        _class_field_names(
            parsed["text"],
            parsed["tokens"],
            class_item["body_range"][0],
            class_item["body_range"][1],
        ),
        [item["name"] for item in variable_anchors],
    )


def _inherits_uinterface(base_types: list[str]) -> bool:
    return any(
        base_type.rsplit("::", 1)[-1] == "UInterface"
        for base_type in base_types
    )


def _type_definition_fact(
    loaded: dict[str, Any],
    path: Path,
    parsed: dict[str, Any],
    class_item: dict[str, Any],
    variables: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    type_macros = _type_macros(loaded, parsed, path, class_item)
    type_evidence = _type_evidence(
        loaded,
        path,
        class_item["location"],
        type_macros,
    )
    rooted_class_evidence = _public_location(
        path,
        class_item["location"],
        loaded["project_root"],
        loaded["engine_root"],
    )
    member_anchors, lexical_field_names, projected_field_names = (
        _member_anchors(
            loaded,
            path,
            parsed,
            class_item,
            variables,
            rooted_class_evidence,
        )
    )
    problem = None
    if lexical_field_names != projected_field_names:
        problem = {
            "severity": "warning",
            "code": "source-type-member-projection-mismatch",
            "type": class_item["name"],
            "lexical_member_variables": lexical_field_names,
            "projected_member_variables": projected_field_names,
            "evidence": type_evidence,
            "message": (
                "Member-variable name and variable-detail projections disagree"
            ),
        }
    namespace = namespace_at(
        parsed["namespace_scopes"],
        int(class_item["_token_range"][0]),
    )
    public_item = {
        "name": class_item["name"],
        "namespace": namespace,
        "qualified_name": qualified_name(
            namespace,
            class_item["qualified_name"],
        ),
        "owner": class_item["owner"],
        "role": "definition",
        "base_types": class_item["base_types"],
        "macros": [str(macro["_expression"]) for macro in type_macros],
        "member_anchors": member_anchors,
        "evidence": type_evidence,
    }
    interface_source = {
        "declaration_kind": class_item["kind"],
        "name": class_item["name"],
        "qualified_name": public_item["qualified_name"],
        "owner": class_item["owner"],
        "base_types": class_item["base_types"],
        "macro_names": [str(macro["name"]) for macro in type_macros],
        "evidence": type_evidence,
    }
    return public_item, interface_source, problem


def _forward_type_fact(
    loaded: dict[str, Any],
    path: Path,
    parsed: dict[str, Any],
    declaration: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    evidence = _type_unit_evidence(
        loaded,
        path,
        declaration["location"],
    )
    namespace = namespace_at(
        parsed["namespace_scopes"],
        int(declaration["_token_range"][0]),
    )
    public_qualified_name = qualified_name(
        namespace,
        declaration["qualified_name"],
    )
    if declaration["kind"] == "enum":
        return (
            "enums",
            {
                "kind": "enum",
                "name": declaration["name"],
                "namespace": namespace,
                "qualified_name": public_qualified_name,
                "owner": declaration["owner"],
                "role": "declaration",
                "scoped": declaration["scoped"],
                "macros": [],
                "evidence": evidence,
            },
        )
    return (
        "classes" if declaration["kind"] == "class" else "structs",
        {
            "name": declaration["name"],
            "namespace": namespace,
            "qualified_name": public_qualified_name,
            "owner": declaration["owner"],
            "role": "declaration",
            "base_types": [],
            "macros": [],
            "member_anchors": [],
            "evidence": evidence,
        },
    )


def _interface_candidate_facts(
    interface_sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    uinterface_stems = {
        item["name"][1:]
        for item in interface_sources
        if item["name"].startswith("U")
        and len(item["name"]) > 1
        and (
            "UINTERFACE" in item["macro_names"]
            or _inherits_uinterface(item["base_types"])
        )
    }
    generated_interface_macros = {
        "GENERATED_BODY",
        "GENERATED_IINTERFACE_BODY",
        "GENERATED_UINTERFACE_BODY",
    }
    candidates: list[dict[str, Any]] = []
    for item in interface_sources:
        reasons: list[str] = []
        if "UINTERFACE" in item["macro_names"]:
            reasons.append("uinterface_macro")
        if _inherits_uinterface(item["base_types"]):
            reasons.append("inherits_uinterface")
        if (
            item["name"].startswith("I")
            and len(item["name"]) > 1
            and generated_interface_macros.intersection(
                item["macro_names"]
            )
        ):
            reasons.append("generated_body_i_prefix")
        if (
            item["name"].startswith("I")
            and item["name"][1:] in uinterface_stems
        ):
            reasons.append("paired_uinterface")
        if reasons:
            candidates.append(
                {
                    "name": item["name"],
                    "qualified_name": item["qualified_name"],
                    "owner": item["owner"],
                    "declaration_kind": item["declaration_kind"],
                    "reasons": reasons,
                    "evidence": item["evidence"],
                }
            )
    return candidates


def _type_anchor_facts(
    loaded: dict[str, Any],
    variables: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    anchors: dict[str, list[dict[str, Any]]] = {
        "classes": [],
        "structs": [],
        "enums": [],
    }
    interface_sources: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for path, parsed in loaded["parsed_files"]:
        for class_item in parsed["classes"]:
            public_item, interface_source, problem = _type_definition_fact(
                loaded,
                path,
                parsed,
                class_item,
                variables,
            )
            bucket = (
                "classes" if class_item["kind"] == "class" else "structs"
            )
            anchors[bucket].append(public_item)
            interface_sources.append(interface_source)
            if problem is not None:
                problems.append(problem)
        for enum_item in _enums(
            parsed,
            path,
            loaded["project_root"],
            loaded["engine_root"],
        ):
            enum_macros = _type_macros(loaded, parsed, path, enum_item)
            anchors["enums"].append(
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
        for declaration in parsed.get("forward_declarations", []):
            bucket, public_item = _forward_type_fact(
                loaded,
                path,
                parsed,
                declaration,
            )
            anchors[bucket].append(public_item)

    return (
        {
            "classes": sorted(anchors["classes"], key=_anchor_sort_key),
            "structs": sorted(anchors["structs"], key=_anchor_sort_key),
            "enums": sorted(anchors["enums"], key=_anchor_sort_key),
            "interface_candidates": sorted(
                _interface_candidate_facts(interface_sources),
                key=_anchor_sort_key,
            ),
        },
        problems,
    )


def _free_function_facts(
    loaded: dict[str, Any],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path, parsed in loaded["parsed_files"]:
        groups = (
            ("definition", parsed["free_functions"]),
            (
                "declaration",
                parse_free_function_declarations(
                    parsed["text"],
                    parsed["tokens"],
                    parsed["forward"],
                ),
            ),
        )
        for role, functions in groups:
            for function in functions:
                namespace = namespace_at(
                    parsed["namespace_scopes"],
                    int(function["_token_index"]),
                )
                namespace = (
                    function.get("_explicit_namespace")
                    or namespace
                )
                declaration_tokens = parsed["tokens"][
                    int(function["_token_index"]) :
                    int(function["_name_index"])
                ]
                results.append(
                    {
                        "name": function["name"],
                        "namespace": namespace,
                        "qualified_name": qualified_name(
                            namespace,
                            function["name"],
                        ),
                        "signature": " ".join(
                            function["signature"].split()
                        ),
                        "role": role,
                        "linkage": (
                            "internal"
                            if _has_anonymous_namespace(namespace)
                            or any(
                                token.value == "static"
                                for token in declaration_tokens
                            )
                            else "external"
                        ),
                        "evidence": _type_unit_evidence(
                            loaded,
                            path,
                            function["location"],
                        ),
                    }
                )
    unique = {
        (
            item["qualified_name"],
            item["signature"],
            item["role"],
            item["linkage"],
            item["evidence"]["unit"],
            item["evidence"]["line"],
        ): item
        for item in results
    }
    return sorted(unique.values(), key=_anchor_sort_key)


def _unresolved_facts(
    loaded: dict[str, Any],
    unresolved: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path, _parsed in loaded["parsed_files"]:
        for item in unresolved:
            if not _path_matches_evidence(
                path,
                item["evidence"],
                loaded,
            ):
                continue
            public_item = {
                key: value
                for key, value in item.items()
                if key != "evidence"
            }
            public_item["evidence"] = _type_unit_evidence(
                loaded,
                path,
                item["evidence"],
            )
            results.append(public_item)
    return sorted(
        results,
        key=lambda item: (
            0 if item["evidence"]["unit"] == "cpp" else 1,
            int(item["evidence"]["line"]),
            str(item.get("scope", "")),
        ),
    )


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
    type_anchors, type_problems = _type_anchor_facts(
        loaded,
        variables,
    )
    unresolved_facts = _unresolved_facts(loaded, unresolved)
    return source_result(
        "ue_list_cxx_types",
        loaded,
        {
            **type_anchors,
            "global_variables": _global_variable_facts(
                loaded,
                variables,
            ),
            "free_functions": _free_function_facts(loaded),
            "unresolved_declarations": unresolved_facts,
        },
        responsibility=(
            "Index class, struct, enum, interface-candidate, global-variable, "
            "free-function, and class/struct member anchors."
        ),
        boundaries=[
            "All anchors are lexical navigation facts and are not semantic summaries.",
            "Class, struct, and enum anchors distinguish declarations from definitions; qualified names include locally observed named or anonymous namespace scopes.",
            "Nested type owners remain lexical class/struct owners; namespace qualification is carried separately.",
            "Interface candidates are reported only from local UINTERFACE, UInterface inheritance, generated-body I-prefix, or paired U/I naming evidence.",
            "Type and member macros are attached by lexical declaration adjacency, not UHT semantic analysis.",
            "Global variables include file- and namespace-scope declarations; roles and linkage use only declaration-local syntax, and function locals and class/struct members are excluded.",
            "A scope-qualified variable or function definition is classified as a namespace symbol only when its qualifier resolves to a namespace observed in the selected source pair; other qualified definitions remain member-shaped.",
            "Macro-like declarations are excluded from free functions, and call-shaped variable initializers are classified only when a value expression is lexically evident.",
            "Free functions include declarations and definitions with locally observed linkage but are not overload-resolved.",
            "The selected source and its uniquely derived companion are reported independently; declarations and definitions are not merged across files.",
            "The result does not create project-level IDs and is not a complete C++ symbol table, type system, inheritance graph, or reflection result.",
        ],
        additional_problems=[
            *type_problems,
            *(
                [
                    {
                        "severity": "warning",
                        "code": "source-type-declaration-unresolved",
                        "count": len(unresolved),
                        "message": (
                            "One or more declarations could not be "
                            "classified conservatively"
                        ),
                    }
                ]
                if unresolved
                else []
            ),
        ],
    )
