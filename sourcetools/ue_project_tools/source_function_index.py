from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .source_callable_declarations import parse_free_function_declarations
from .source_context import load_source_context, source_result
from .source_declarators import _FORBIDDEN_CALLABLE_NAMES, _TYPE_KEYWORDS
from .source_namespaces import (
    namespace_at,
    observed_namespace_names,
    qualified_name,
)
from .source_signatures import parameter_signature
from .source_fact_common import (
    _SOURCE_MACROS,
    _SOURCE_MACRO_PREFIXES,
    _callable_name,
    _public_location,
    _source_macros,
)
from .source_variable_facts import _source_declaration_facts


def _qualifiers(signature: str) -> list[str]:
    values = []
    for value in (
        "static",
        "virtual",
        "inline",
        "constexpr",
    ):
        if re.search(rf"\b{value}\b", signature):
            values.append(value)
    suffix = signature.rsplit(")", 1)[-1] if ")" in signature else ""
    for value in ("const", "volatile", "noexcept", "override", "final"):
        if re.search(rf"\b{value}\b", suffix):
            values.append(value)
    if re.search(r"(?:^|\s)&&(?:\s|$)", suffix):
        values.append("rvalue_ref")
    elif re.search(r"(?:^|\s)&(?:\s|$)", suffix):
        values.append("lvalue_ref")
    if re.search(r"=\s*0\b", signature):
        values.append("pure_virtual")
    if re.search(r"=\s*default\b", signature):
        values.append("defaulted")
    if re.search(r"=\s*delete\b", signature):
        values.append("deleted")
    return values


def _identity_qualifiers(signature: str) -> tuple[str, ...]:
    return tuple(
        qualifier
        for qualifier in _qualifiers(signature)
        if qualifier in {"const", "volatile", "lvalue_ref", "rvalue_ref"}
    )


def _function_id(
    kind: str,
    namespace: str | None,
    owner: str | None,
    name: str,
    parameter_signature: list[list[str]],
    identity_qualifiers: tuple[str, ...],
) -> str:
    parameters = ";".join(" ".join(group) for group in parameter_signature)
    qualifiers = ",".join(identity_qualifiers)
    return "|".join(
        (
            kind,
            namespace or "",
            owner or "",
            name,
            f"({parameters})",
            qualifiers,
        )
    )


def _callable_part(
    *,
    kind: str,
    namespace: str | None,
    owner: str | None,
    name: str,
    parameters: str,
    signature: str,
    role: str,
    path: Path,
    location: dict[str, Any],
    body_range: tuple[int, int] | None,
    project_root: Path,
    engine_root: Path | None,
) -> dict[str, Any]:
    actual_name = _callable_name(name, signature)
    normalized_parameters = [
        list(group) for group in parameter_signature(parameters)
    ]
    identity_qualifiers = _identity_qualifiers(signature)
    function_id = _function_id(
        kind,
        namespace,
        owner,
        actual_name,
        normalized_parameters,
        identity_qualifiers,
    )
    lexical_name = (
        f"{owner}::{actual_name}"
        if owner
        else actual_name
    )
    return {
        "function_id": function_id,
        "kind": kind,
        "namespace": namespace,
        "qualified_name": qualified_name(
            namespace,
            lexical_name,
        ),
        "owner": owner,
        "name": actual_name,
        "parameters": parameters,
        "parameter_signature": normalized_parameters,
        "signature": " ".join(signature.split()),
        "qualifiers": _qualifiers(signature),
        "role": role,
        "evidence": _public_location(path, location, project_root, engine_root),
        "_identity": (
            kind,
            namespace or "",
            owner or "",
            actual_name,
            tuple(tuple(group) for group in normalized_parameters),
            identity_qualifiers,
        ),
        "_body_range": body_range,
        "_path": path,
    }


def _top_level_declarations(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    return parse_free_function_declarations(
        parsed["text"],
        parsed["tokens"],
        parsed["forward"],
    )


def _callable_parts(
    parsed_files: list[tuple[Path, dict[str, Any]]],
    project_root: Path,
    engine_root: Path | None,
) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    known_namespaces = {
        namespace
        for _path, parsed in parsed_files
        for namespace in observed_namespace_names(
            parsed["namespace_scopes"]
        )
    }
    for path, parsed in parsed_files:
        for class_item in parsed["classes"]:
            namespace = namespace_at(
                parsed["namespace_scopes"],
                int(class_item["_token_range"][0]),
            )
            for member in class_item["members"]:
                if member["name"] in _SOURCE_MACROS or member["name"].startswith(
                    _SOURCE_MACRO_PREFIXES
                ):
                    continue
                parts.append(
                    _callable_part(
                        kind="method",
                        namespace=namespace,
                        owner=class_item["qualified_name"],
                        name=member["name"],
                        parameters=member["parameters"],
                        signature=member["signature"],
                        role="definition" if member["has_body"] else "declaration",
                        path=path,
                        location=member["location"],
                        body_range=member["body_range"],
                        project_root=project_root,
                        engine_root=engine_root,
                    )
                )
        for definition in parsed["external_definitions"]:
            lexical_namespace = namespace_at(
                parsed["namespace_scopes"],
                int(definition["_token_index"]),
            )
            qualifier_parts = str(
                definition["qualifier"]
            ).split("::")
            namespace = lexical_namespace
            for end in range(len(qualifier_parts) - 1, 0, -1):
                prefix = "::".join(qualifier_parts[:end])
                if prefix in known_namespaces:
                    namespace = prefix
                    break
                nested = qualified_name(lexical_namespace, prefix)
                if nested in known_namespaces:
                    namespace = nested
                    break
            owner = str(definition["qualifier"])
            namespace_prefix = f"{namespace}::" if namespace else None
            if (
                namespace_prefix
                and owner.startswith(namespace_prefix)
            ):
                owner = owner[len(namespace_prefix) :]
            parts.append(
                _callable_part(
                    kind="method",
                    namespace=namespace,
                    owner=owner,
                    name=definition["name"],
                    parameters=definition["parameters"],
                    signature=definition["signature"],
                    role="definition",
                    path=path,
                    location=definition["location"],
                    body_range=definition["body_range"],
                    project_root=project_root,
                    engine_root=engine_root,
                )
            )
        for function in parsed["free_functions"]:
            namespace = (
                function.get("_explicit_namespace")
                or namespace_at(
                    parsed["namespace_scopes"],
                    int(function["_token_index"]),
                )
            )
            parts.append(
                _callable_part(
                    kind="free_function",
                    namespace=namespace,
                    owner=None,
                    name=function["name"],
                    parameters=function["parameters"],
                    signature=function["signature"],
                    role="definition",
                    path=path,
                    location=function["location"],
                    body_range=function["body_range"],
                    project_root=project_root,
                    engine_root=engine_root,
                )
            )
        for declaration in _top_level_declarations(parsed):
            namespace = namespace_at(
                parsed["namespace_scopes"],
                int(declaration["_token_index"]),
            )
            parts.append(
                _callable_part(
                    kind="free_function",
                    namespace=namespace,
                    owner=None,
                    name=declaration["name"],
                    parameters=declaration["parameters"],
                    signature=declaration["signature"],
                    role="declaration",
                    path=path,
                    location=declaration["location"],
                    body_range=None,
                    project_root=project_root,
                    engine_root=engine_root,
                )
            )
    return sorted(
        [
            part
            for part in parts
            if part["name"] not in _FORBIDDEN_CALLABLE_NAMES
        ],
        key=lambda item: (
            item["evidence"]["root"],
            item["evidence"]["path"].casefold(),
            item["evidence"]["line"],
            item["name"],
        ),
    )


def _public_callable(part: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in part.items()
        if not key.startswith("_")
        and key not in {"function_id", "parameter_signature", "evidence"}
    }


def _public_relation(relation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: relation[key]
        for key in ("status", "declarations", "definitions")
    }


def _relations(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for part in parts:
        grouped.setdefault(part["_identity"], []).append(part)
    relations: list[dict[str, Any]] = []
    for identity, items in sorted(grouped.items(), key=lambda pair: str(pair[0])):
        declarations = [item for item in items if item["role"] == "declaration"]
        definitions = [item for item in items if item["role"] == "definition"]
        if len(definitions) > 1 or len(declarations) > 1:
            status = "ambiguous"
        elif declarations and definitions:
            status = "matched"
        elif definitions:
            definition_path = str(definitions[0]["evidence"]["path"]).casefold()
            status = (
                "inline_definition"
                if definition_path.endswith((".h", ".hpp"))
                else "source_only"
            )
        else:
            status = "declaration_only"
        relations.append(
            {
                "kind": "declaration_definition",
                "callable": {
                    "function_id": _function_id(
                        identity[0],
                        identity[1] or None,
                        identity[2] or None,
                        identity[3],
                        [list(group) for group in identity[4]],
                        identity[5],
                    ),
                    "kind": identity[0],
                    "namespace": identity[1] or None,
                    "qualified_name": qualified_name(
                        identity[1] or None,
                        (
                            f"{identity[2]}::{identity[3]}"
                            if identity[2]
                            else identity[3]
                        ),
                    ),
                    "owner": identity[2] or None,
                    "name": identity[3],
                    "parameter_signature": [list(group) for group in identity[4]],
                    "identity_qualifiers": list(identity[5]),
                },
                "status": status,
                "declarations": [item["evidence"] for item in declarations],
                "definitions": [item["evidence"] for item in definitions],
            }
        )
    return relations


def _function_facts(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def occurrence(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "signature": item["signature"],
            "evidence": item["evidence"],
        }

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for part in parts:
        grouped.setdefault(part["_identity"], []).append(part)
    relation_by_identity = {
        (
            relation["callable"]["kind"],
            relation["callable"]["namespace"] or "",
            relation["callable"]["owner"] or "",
            relation["callable"]["name"],
            tuple(
                tuple(group)
                for group in relation["callable"]["parameter_signature"]
            ),
            tuple(relation["callable"]["identity_qualifiers"]),
        ): relation
        for relation in _relations(parts)
    }
    results: list[dict[str, Any]] = []
    for identity, items in sorted(
        grouped.items(), key=lambda pair: str(pair[0])
    ):
        declarations = [
            occurrence(item)
            for item in items
            if item["role"] == "declaration"
        ]
        definitions = [
            occurrence(item)
            for item in items
            if item["role"] == "definition"
        ]
        relation = relation_by_identity[identity]
        results.append(
            {
                "kind": identity[0],
                "namespace": identity[1] or None,
                "qualified_name": qualified_name(
                    identity[1] or None,
                    (
                        f"{identity[2]}::{identity[3]}"
                        if identity[2]
                        else identity[3]
                    ),
                ),
                "owner": identity[2] or None,
                "name": identity[3],
                "function_id": items[0]["function_id"],
                "parameters": items[0]["parameters"],
                "parameter_signature": [
                    list(group) for group in identity[4]
                ],
                "identity_qualifiers": list(identity[5]),
                "qualifiers": sorted(
                    {
                        qualifier
                        for item in items
                        for qualifier in item["qualifiers"]
                    }
                ),
                "relation": relation["status"],
                "declarations": declarations,
                "definitions": definitions,
            }
        )
    return results


def list_source_functions(
    source_file: Path,
    engine_override: Path | None = None,
    compilation_database: Path | None = None,
) -> dict[str, Any]:
    loaded = load_source_context(
        source_file, engine_override, compilation_database
    )
    loaded["parts"] = _callable_parts(
        loaded["parsed_files"],
        loaded["project_root"],
        loaded["engine_root"],
    )
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
    functions = _function_facts(loaded["parts"])
    _, all_unresolved = _source_declaration_facts(loaded)
    unresolved = [
        item
        for item in all_unresolved
        if item["scope"] in {"file", "member"}
    ]
    invalid_names = [
        item for item in functions if item["name"] in _TYPE_KEYWORDS
    ]
    function_macros = [
        {
            key: value
            for key, value in macro.items()
            if not key.startswith("_")
        }
        for macro in loaded["macros"]
        if macro["name"] == "UFUNCTION"
    ]
    return source_result(
        "ue_list_cxx_functions",
        loaded,
        {
            "functions": functions,
            "unresolved_declarations": unresolved,
            "function_macros": function_macros,
        },
        responsibility="Index callable signatures and conservative declaration-definition relations.",
        boundaries=[
            "Function bodies, calls, and state-changing operations are not included in this index.",
            "Relations are a conservative projection, not a complete C++ AST or linker result.",
        ],
        additional_problems=[
            *[
                {
                    "severity": "warning",
                    "code": "source-function-invalid-name",
                    "function_id": item["function_id"],
                    "name": item["name"],
                    "message": (
                        "A callable projection used a reserved type keyword "
                        "as its name"
                    ),
                }
                for item in invalid_names
            ],
            *(
                [
                    {
                        "severity": "warning",
                        "code": "source-function-declaration-unresolved",
                        "count": len(unresolved),
                        "message": (
                            "One or more declaration-shaped statements could "
                            "not be classified conservatively"
                        ),
                    }
                ]
                if unresolved
                else []
            ),
        ],
    )
