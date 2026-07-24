from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .common import normalized, read_json, result_document
from .descriptor import resolve_internal_directories
from .discovery import find_nearest_uproject
from .engine import resolve_engine
from .module_entry_callables import _parameter_signature
from .source_includes import (
    extract_includes,
    module_records,
    owner_for_path,
    public_owner,
    resolve_include,
    rooted_path,
)
from .source_controls import _member_chain_start
from .source_declarations import (
    _FORBIDDEN_CALLABLE_NAMES,
    _TYPE_KEYWORDS,
    _class_field_names,
    _classify_declaration,
    _declaration_assignment,
)
from .source_parser import parse_cpp_file
from .source_tokens import (
    Token,
    _location,
    _raw,
    _raw_from_values,
    _split_arguments,
    lex_source,
    token_pairs,
)


_SOURCE_SUFFIXES = {".cpp", ".cc"}
_SOURCE_MACROS = {
    "UCLASS",
    "USTRUCT",
    "UENUM",
    "UINTERFACE",
    "UPROPERTY",
    "UFUNCTION",
    "GENERATED_BODY",
    "GENERATED_UCLASS_BODY",
    "GENERATED_USTRUCT_BODY",
}
_SOURCE_MACRO_PREFIXES = ("DECLARE_", "IMPLEMENT_")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _validated_file(path: Path, suffixes: set[str], label: str) -> Path:
    resolved = path.resolve()
    if resolved.suffix.casefold() not in suffixes:
        expected = ", ".join(sorted(suffixes))
        raise ValueError(f"Expected {label} with one of {expected}: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"{label} is not a file: {resolved}")
    return resolved


def _automatic_headers(
    source: Path,
    source_owner: dict[str, Any] | None,
) -> list[Path]:
    candidate_bases = [source.parent / source.stem]
    if source_owner is not None:
        module_root = Path(source_owner["root"]).resolve()
        try:
            relative = source.relative_to(module_root)
        except ValueError:
            relative = None
        if relative is not None:
            relative_base = relative.parent / relative.stem
            if relative.parts and relative.parts[0].casefold() == "private":
                tail = Path(*relative_base.parts[1:])
                candidate_bases.extend(
                    [module_root / "Public" / tail, module_root / "Classes" / tail]
                )
            elif (
                relative.parts
                and relative.parts[0].casefold()
                not in {"public", "classes"}
            ):
                candidate_bases.extend(
                    [
                        module_root / "Public" / relative_base,
                        module_root / "Classes" / relative_base,
                    ]
                )

    seen: set[str] = set()
    results: list[Path] = []
    for base in candidate_bases:
        for suffix in (".h", ".hpp"):
            candidate = (base.parent / f"{base.name}{suffix}").resolve()
            key = normalized(candidate).casefold()
            if key in seen:
                continue
            seen.add(key)
            if candidate.is_file():
                results.append(candidate)
    return results


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
    owner: str | None,
    name: str,
    parameter_signature: list[list[str]],
    identity_qualifiers: tuple[str, ...],
) -> str:
    parameters = ";".join(" ".join(group) for group in parameter_signature)
    qualifiers = ",".join(identity_qualifiers)
    return "|".join(
        (kind, owner or "", name, f"({parameters})", qualifiers)
    )


def _callable_name(name: str, signature: str) -> str:
    return f"~{name}" if re.search(rf"~\s*{re.escape(name)}\s*\(", signature) else name


def _callable_part(
    *,
    kind: str,
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
    parameter_signature = [list(group) for group in _parameter_signature(parameters)]
    identity_qualifiers = _identity_qualifiers(signature)
    function_id = _function_id(
        kind,
        owner,
        actual_name,
        parameter_signature,
        identity_qualifiers,
    )
    return {
        "function_id": function_id,
        "kind": kind,
        "owner": owner,
        "name": actual_name,
        "parameters": parameters,
        "parameter_signature": parameter_signature,
        "signature": " ".join(signature.split()),
        "qualifiers": _qualifiers(signature),
        "role": role,
        "evidence": _public_location(path, location, project_root, engine_root),
        "_identity": (
            kind,
            owner or "",
            actual_name,
            tuple(tuple(group) for group in parameter_signature),
            identity_qualifiers,
        ),
        "_body_range": body_range,
        "_path": path,
    }


def _top_level_declarations(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    text = parsed["text"]
    tokens: list[Token] = parsed["tokens"]
    forward: dict[int, int] = parsed["forward"]
    declarations: list[dict[str, Any]] = []
    brace_depth = 0
    index = 0
    excluded = {
        "alignof",
        "catch",
        "decltype",
        "for",
        "if",
        "sizeof",
        "switch",
        "while",
    }
    while index < len(tokens):
        value = tokens[index].value
        if value == "{":
            brace_depth += 1
            index += 1
            continue
        if value == "}":
            brace_depth = max(0, brace_depth - 1)
            index += 1
            continue
        if value != "(" or brace_depth or index not in forward or index == 0:
            index += 1
            continue
        name_index = index - 1
        name_token = tokens[name_index]
        if (
            name_token.kind != "identifier"
            or name_token.value in excluded
            or name_token.value in _SOURCE_MACROS
            or name_token.value.startswith(_SOURCE_MACRO_PREFIXES)
            or (name_index > 0 and tokens[name_index - 1].value == "::")
        ):
            index = forward[index] + 1
            continue
        start = name_index - 1
        while start >= 0 and tokens[start].value not in {";", "{", "}"}:
            start -= 1
        start += 1
        if any(
            token.value in {"=", "return"}
            for token in tokens[start:index]
        ):
            index = forward[index] + 1
            continue
        close = forward[index]
        cursor = close + 1
        while cursor < len(tokens) and tokens[cursor].value not in {";", "{"}:
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor].value != ";" or start >= name_index:
            index = close + 1
            continue
        classification = _classify_declaration(
            tokens, forward, start, cursor
        )
        if (
            classification["kind"] != "callable"
            or classification.get("name_index") != name_index
            or classification.get("parameter_open") != index
        ):
            index = close + 1
            continue
        declarations.append(
            {
                "name": name_token.value,
                "parameters": _raw(text, tokens, index + 1, close),
                "signature": _raw(text, tokens, start, cursor),
                "location": _location(tokens[start], tokens[cursor]),
            }
        )
        index = cursor + 1
    return declarations


def _callable_parts(
    parsed_files: list[tuple[Path, dict[str, Any]]],
    project_root: Path,
    engine_root: Path | None,
) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    for path, parsed in parsed_files:
        for class_item in parsed["classes"]:
            for member in class_item["members"]:
                if member["name"] in _SOURCE_MACROS or member["name"].startswith(
                    _SOURCE_MACRO_PREFIXES
                ):
                    continue
                parts.append(
                    _callable_part(
                        kind="method",
                        owner=class_item["name"],
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
            parts.append(
                _callable_part(
                    kind="method",
                    owner=definition["class_name"],
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
            parts.append(
                _callable_part(
                    kind="free_function",
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
            parts.append(
                _callable_part(
                    kind="free_function",
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


def _primary_type_name(type_expression: str) -> str | None:
    identifiers = [
        token.value
        for token in lex_source(type_expression)
        if token.kind == "identifier"
        and token.value
        not in {
            "auto",
            "class",
            "const",
            "enum",
            "struct",
            "typename",
            "volatile",
        }
    ]
    return identifiers[0] if identifiers else None


def _canonical_type_expression(type_expression: str) -> str:
    tokens = [
        token
        for token in lex_source(type_expression)
        if token.value
        not in {
            "class",
            "const",
            "struct",
            "typename",
            "volatile",
            "*",
            "&",
            "&&",
        }
    ]
    rendered = _raw_from_values(tokens)
    rendered = re.sub(r"\s*<\s*", "<", rendered)
    rendered = re.sub(r"\s*>\s*", ">", rendered)
    rendered = re.sub(r"\s*,\s*", ", ", rendered)
    return rendered


def _parameter_symbol_types(part: dict[str, Any]) -> dict[str, str]:
    tokens = lex_source(part["parameters"])
    forward, _ = token_pairs(tokens)
    symbols: dict[str, str] = {}
    for start, end in _split_arguments(tokens, 0, len(tokens)):
        classification = _classify_declaration(
            tokens, forward, start, end
        )
        if classification["kind"] != "variable":
            continue
        name_index = int(classification["name_index"])
        type_expression = _raw_from_values(tokens[start:name_index])
        canonical_type = _canonical_type_expression(type_expression)
        if canonical_type:
            symbols[str(classification["name"])] = canonical_type
    return symbols


def _function_symbol_types(
    part: dict[str, Any],
    loaded: dict[str, Any],
) -> tuple[dict[str, str], set[str]]:
    symbols = _parameter_symbol_types(part)
    type_names = set(symbols.values())
    variables, _ = _declaration_variables(
        loaded["parsed_by_path"][part["_path"]],
        part["_path"],
        part["_body_range"][0],
        part["_body_range"][1],
        scope="local",
        owner=part["owner"],
        project_root=loaded["project_root"],
        engine_root=loaded["engine_root"],
    )
    shadowed_member_names = {
        *symbols,
        *(variable["name"] for variable in variables),
    }
    parsed = loaded["parsed_by_path"][part["_path"]]
    tokens: list[Token] = parsed["tokens"]
    start, end = part["_body_range"]
    referenced_names = {
        token.value
        for token in tokens[start:end]
        if token.kind == "identifier"
    }
    variables.extend(
        item
        for item in _source_declaration_facts(loaded)[0]
        if item["scope"] == "member"
        and item.get("owner") == part["owner"]
        and item["name"] in referenced_names
        and item["name"] not in shadowed_member_names
    )
    for variable in variables:
        if any(
            token.value in {".", "->"}
            for token in lex_source(variable["type_expression"])
        ):
            continue
        canonical_type = _canonical_type_expression(
            variable["type_expression"]
        )
        if not canonical_type:
            continue
        symbols[variable["name"]] = canonical_type
        outer_type = _primary_type_name(canonical_type)
        if (
            outer_type
            and outer_type[0].isupper()
            and not outer_type.isupper()
        ):
            type_names.add(canonical_type)
    for semicolon in range(start, end):
        if tokens[semicolon].value != ";":
            continue
        statement_start = _statement_start(tokens, start, semicolon)
        classification = _classify_declaration(
            tokens,
            parsed["forward"],
            statement_start,
            semicolon,
        )
        if classification["kind"] != "callable":
            continue
        name_index = int(classification["name_index"])
        if (
            name_index <= statement_start
            or name_index + 1 >= semicolon
            or tokens[name_index + 1].value not in {"(", "{"}
            or tokens[name_index - 1].value in {".", "->", "::"}
            or any(
                tokens[index].value in {".", "->"}
                for index in range(statement_start, name_index)
            )
        ):
            continue
        canonical_type = _canonical_type_expression(
            _raw_from_values(tokens[statement_start:name_index])
        )
        outer_type = _primary_type_name(canonical_type)
        if (
            not outer_type
            or not outer_type[0].isupper()
            or outer_type.isupper()
        ):
            continue
        symbols[str(classification["name"])] = canonical_type
        type_names.add(canonical_type)
    return symbols, type_names


def _call_name_before_open(
    tokens: list[Token],
    open_index: int,
    lower: int,
) -> int | None:
    candidate = open_index - 1
    if candidate >= lower and tokens[candidate].kind == "identifier":
        return candidate
    if candidate < lower or tokens[candidate].value not in {">", ">>"}:
        return None
    depth = 0
    for cursor in range(candidate, lower - 1, -1):
        value = tokens[cursor].value
        if value == ">":
            depth += 1
        elif value == ">>":
            depth += 2
        elif value == "<":
            depth -= 1
            if depth == 0:
                name_index = cursor - 1
                if (
                    name_index >= lower
                    and tokens[name_index].kind == "identifier"
                ):
                    return name_index
                return None
    return None


def _external_methods(
    part: dict[str, Any],
    loaded: dict[str, Any],
    symbol_types: dict[str, str],
) -> list[str]:
    parsed = loaded["parsed_by_path"][part["_path"]]
    text = parsed["text"]
    tokens: list[Token] = parsed["tokens"]
    forward: dict[int, int] = parsed["forward"]
    reverse: dict[int, int] = parsed["reverse"]
    start, end = part["_body_range"]
    local_methods = {
        item["name"]
        for item in loaded["parts"]
        if item["owner"] == part["owner"]
    }
    results: list[str] = []
    for open_index in range(start, end):
        if tokens[open_index].value != "(" or open_index not in forward:
            continue
        close_index = forward[open_index]
        if close_index >= end:
            continue
        name_index = _call_name_before_open(tokens, open_index, start)
        if name_index is None or name_index - 1 < start:
            continue
        operator = tokens[name_index - 1].value
        if operator not in {".", "->", "::"}:
            continue
        callee_start = _member_chain_start(
            tokens, reverse, name_index, start
        )
        receiver_tokens = tokens[callee_start : name_index - 1]
        receiver_identifiers = [
            token.value
            for token in receiver_tokens
            if token.kind == "identifier"
        ]
        owner_type: str | None = None
        if operator == "::" and name_index >= 2:
            owner_type = tokens[name_index - 2].value
        elif receiver_identifiers:
            receiver_root = receiver_identifiers[0]
            owner_type = (
                part["owner"]
                if receiver_root == "this"
                else symbol_types.get(receiver_root)
            )
        method_name = tokens[name_index].value
        if owner_type == part["owner"] and method_name in local_methods:
            continue
        original_expression = _raw(
            text, tokens, callee_start, close_index + 1
        )
        if owner_type is None:
            results.append(original_expression)
            continue
        method_expression = _raw(
            text, tokens, name_index, close_index + 1
        )
        results.append(f"{owner_type}{operator}{method_expression}")
    return list(dict.fromkeys(results))


def _external_type_facts(
    part: dict[str, Any],
    loaded: dict[str, Any],
    candidate_names: set[str],
) -> list[str]:
    local_types = {
        class_item["name"]
        for _, source_parsed in loaded["parsed_files"]
        for class_item in source_parsed["classes"]
    }
    return sorted(
        {
            type_expression
            for type_expression in candidate_names
            if (
                (outer_type := _primary_type_name(type_expression))
                and outer_type not in local_types
                and outer_type[0].isupper()
                and not outer_type.isupper()
            )
        },
        key=str.casefold,
    )


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
                        identity[2],
                        [list(group) for group in identity[3]],
                        identity[4],
                    ),
                    "kind": identity[0],
                    "owner": identity[1] or None,
                    "name": identity[2],
                    "parameter_signature": [list(group) for group in identity[3]],
                    "identity_qualifiers": list(identity[4]),
                },
                "status": status,
                "declarations": [item["evidence"] for item in declarations],
                "definitions": [item["evidence"] for item in definitions],
            }
        )
    return relations


def _types(
    parsed_files: list[tuple[Path, dict[str, Any]]],
    project_root: Path,
    engine_root: Path | None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path, parsed in parsed_files:
        for class_item in parsed["classes"]:
            results.append(
                {
                    "kind": class_item["kind"],
                    "name": class_item["name"],
                    "base_types": class_item["base_types"],
                    "evidence": _public_location(
                        path,
                        class_item["location"],
                        project_root,
                        engine_root,
                    ),
                }
            )
        results.extend(_enums(parsed, path, project_root, engine_root))
    return sorted(
        results,
        key=lambda item: (
            item["evidence"]["root"],
            item["evidence"]["path"].casefold(),
            item["evidence"]["line"],
        ),
    )


def _load_source_unit(
    source_file: Path,
    engine_override: Path | None = None,
) -> dict[str, Any]:
    source = _validated_file(source_file, _SOURCE_SUFFIXES, "Source file")
    project = find_nearest_uproject(source)
    descriptor = read_json(project)
    project_root = project.parent.resolve()

    engine_result = resolve_engine(
        project,
        str(descriptor.get("EngineAssociation") or ""),
        engine_override,
    )
    engine_root = (
        Path(engine_result["engine_root"]).resolve()
        if engine_result["status"] == "resolved"
        else None
    )
    if not _is_relative_to(source, project_root) and (
        engine_root is None or not _is_relative_to(source, engine_root)
    ):
        raise ValueError(
            "Source file must be inside the selected project or resolved Engine: "
            f"{source}"
        )

    additional_module_roots, _ = resolve_internal_directories(
        project, descriptor, "AdditionalRootDirectories"
    )
    additional_plugin_roots, _ = resolve_internal_directories(
        project, descriptor, "AdditionalPluginDirectories"
    )
    records = module_records(
        project_root,
        engine_root,
        additional_module_roots,
        additional_plugin_roots,
    )
    source_owner = owner_for_path(source, records)
    source_text = source.read_text(encoding="utf-8-sig", errors="replace")
    header_candidates = _automatic_headers(source, source_owner)
    selected_header = header_candidates[0] if len(header_candidates) == 1 else None
    header_locations = [
        rooted_path(candidate, project_root, engine_root)
        for candidate in header_candidates
    ]

    parsed_files: list[tuple[Path, dict[str, Any]]] = [
        (source, parse_cpp_file(source))
    ]
    all_includes: list[dict[str, Any]] = []
    include_problems: list[dict[str, Any]] = []

    def collect_include(
        include: dict[str, Any],
        unit: str,
        including_file: Path,
    ) -> None:
        resolution = resolve_include(
            include,
            including_file,
            records,
            project_root,
            engine_root,
        )
        resolved_locations = [
            *([resolution["location"]] if "location" in resolution else []),
            *[
                candidate["location"]
                for candidate in resolution.get("candidates", [])
            ],
        ]
        if any(location in header_locations for location in resolved_locations):
            return

        fact = {
            "spelling": include["spelling"],
            "conditions": include["conditions"],
            "evidence": {
                "unit": unit,
                "line": int(include["line"]),
            },
            "resolution": resolution,
        }
        status = str(resolution["status"])
        if status == "resolved":
            fact["resolution"] = {
                key: value
                for key, value in resolution.items()
                if key != "status"
            }
            all_includes.append(fact)
            return
        if status in {
            "generated_header",
            "generated_source",
            "system_or_sdk_unresolved",
        }:
            all_includes.append(fact)
            return

        messages = {
            "ambiguous": "Include resolved to multiple filesystem candidates",
            "not_found": "Include could not be located in known source roots",
            "macro_unresolved": "Include macro could not be resolved statically",
        }
        include_problems.append(
            {
                "severity": "warning",
                "code": f"source-include-{status.replace('_', '-')}",
                "include": fact,
                "message": messages.get(
                    status, "Include provenance could not be resolved"
                ),
            }
        )

    for include in extract_includes(source_text):
        collect_include(include, "cpp", source)
    if selected_header is not None:
        parsed_header = parse_cpp_file(selected_header)
        parsed_files.append((selected_header, parsed_header))
        for include in extract_includes(parsed_header["text"]):
            collect_include(include, "header", selected_header)

    problems: list[dict[str, Any]] = []
    if engine_result["status"] != "resolved":
        problems.append(
            {
                "severity": "warning",
                "code": "source-unit-engine-unresolved",
                "message": (
                    "Engine provenance could not be resolved; project source facts "
                    "remain available but Engine ownership may be incomplete"
                ),
            }
        )
    if source_owner is None:
        problems.append(
            {
                "severity": "warning",
                "code": "source-unit-owner-unresolved",
                "source": rooted_path(source, project_root, engine_root),
                "message": "No enclosing Build.cs source boundary was found",
            }
        )
    if len(header_candidates) > 1:
        problems.append(
            {
                "severity": "warning",
                "code": "source-unit-header-ambiguous",
                "candidates": header_locations,
                "message": "Multiple automatically derived companion headers were found",
            }
        )
    for path, parsed in parsed_files:
        for problem in parsed["problems"]:
            problems.append(
                {
                    **problem,
                    "source": rooted_path(path, project_root, engine_root),
                }
            )

    parts = _callable_parts(parsed_files, project_root, engine_root)
    parsed_by_path = {path: parsed for path, parsed in parsed_files}
    header_fact = (
        rooted_path(selected_header, project_root, engine_root)
        if selected_header is not None
        else None
    )

    macros = [
        macro
        for path, parsed in parsed_files
        for macro in _source_macros(
            parsed, path, project_root, engine_root
        )
    ]
    macros.sort(
        key=lambda item: (
            item["evidence"]["root"],
            item["evidence"]["path"].casefold(),
            item["evidence"]["line"],
        )
    )

    return {
        "path_roots": {
            "project": normalized(project_root),
            "engine": normalized(engine_root) if engine_root else None,
        },
        "context": {
            "project_descriptor": project.name,
            "project_discovery_method": "nearest-source-ancestor",
            "engine": {
                "status": engine_result["status"],
                "version": engine_result.get("version"),
            },
            "source_owner": public_owner(source_owner),
        },
        "source_unit": {
            "source": rooted_path(source, project_root, engine_root),
            "header": header_fact,
        },
        "includes": all_includes,
        "include_problems": include_problems,
        "macros": macros,
        "parts": parts,
        "parsed_files": parsed_files,
        "parsed_by_path": parsed_by_path,
        "project_root": project_root,
        "engine_root": engine_root,
        "problems": problems,
    }


def _base_content(loaded: dict[str, Any]) -> dict[str, Any]:
    return {
        "path_roots": loaded["path_roots"],
        "context": loaded["context"],
        "source_unit": loaded["source_unit"],
    }


def _source_result(
    schema_version: str,
    loaded: dict[str, Any],
    content: dict[str, Any],
    *,
    responsibility: str,
    boundaries: list[str],
    additional_problems: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return result_document(
        schema_version,
        {**_base_content(loaded), **content},
        [*loaded["problems"], *(additional_problems or [])],
        responsibility=responsibility,
        boundaries=[
            "Only the selected .cpp and one unambiguous automatically derived companion header are read as C++ source.",
            *boundaries,
            "The result does not decide required dependencies, feature meaning, implementation correctness, or build-rule changes.",
            "Validation reports input and locally observable structural problems; ok does not prove compilation or runtime behavior.",
        ],
    )


def list_source_includes(
    source_file: Path,
    engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = _load_source_unit(source_file, engine_override)
    return _source_result(
        "ue-itps.source-includes.v1",
        loaded,
        {"includes": loaded["includes"]},
        responsibility="Report non-companion direct include spellings and deterministic filesystem provenance.",
        boundaries=[
            "The selected source's own companion-header include is represented by source_unit.header and omitted from includes.",
            "Ambiguous, missing, and unresolved-macro includes are moved to validation.",
            "Referenced files are located for provenance but are never recursively read.",
            "A resolved include is a unique filesystem candidate, not proof of the effective compiler include path.",
            "Physical ownership does not prove that a dependency is required or correctly declared.",
        ],
        additional_problems=loaded["include_problems"],
    )


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
    loaded = _load_source_unit(source_file, engine_override)
    variables, unresolved = _source_declaration_facts(loaded)
    types, type_problems = _type_facts(loaded, variables)
    return _source_result(
        "ue-itps.source-types.v1",
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
        if classification["kind"] in {"ignored", "callable"}:
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
        assignment = _declaration_assignment(
            tokens, statement_start, semicolon
        )
        if name_index == assignment - 1:
            type_expression = _raw(
                text, tokens, statement_start, name_index
            )
        else:
            type_expression = _raw_from_values(
                [
                    token
                    for index, token in enumerate(
                        tokens[statement_start:assignment],
                        start=statement_start,
                    )
                    if index != name_index
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
        }
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
    for path, parsed in loaded["parsed_files"]:
        global_excluded = _excluded_token_ranges(
            parsed, include_classes=True, include_callables=True
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
        )
        results.extend(file_variables)
        unresolved.extend(file_unresolved)
        for class_item in parsed["classes"]:
            member_excluded = [
                (member["body_range"][0] - 1, member["body_range"][1] + 1)
                for member in class_item["members"]
                if member["body_range"] is not None
            ]
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
                "owner": identity[1] or None,
                "name": identity[2],
                "function_id": items[0]["function_id"],
                "parameters": items[0]["parameters"],
                "parameter_signature": [
                    list(group) for group in identity[3]
                ],
                "identity_qualifiers": list(identity[4]),
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
) -> dict[str, Any]:
    loaded = _load_source_unit(source_file, engine_override)
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
    return _source_result(
        "ue-itps.source-functions.v1",
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


def inspect_source_function(
    source_file: Path,
    function_name: str,
    *,
    engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = _load_source_unit(source_file, engine_override)
    candidates = [
        part
        for part in loaded["parts"]
        if part["role"] == "definition"
        and part["name"] == function_name
    ]
    if not candidates:
        return _source_result(
            "ue-itps.source-function.v1",
            loaded,
            {
                "selection": {"name": function_name},
                "match_count": 0,
                "matches": [],
            },
            responsibility="Report external type and method references for all definitions matching one function name.",
            boundaries=[
                "External means not defined by the selected .cpp or its companion header.",
                "Type names are derived from local declaration syntax; wrapped template types remain one expression.",
                "Member-call receivers are replaced with locally declared type expressions when available.",
                "Called methods, inheritance, overloads, and included source are not followed.",
            ],
            additional_problems=[
                {
                    "severity": "error",
                    "code": "function-not-found",
                    "selection": function_name,
                    "message": "No matching function definition was found",
                }
            ],
        )
    relations = {
        (
            item["callable"]["kind"],
            item["callable"]["owner"] or "",
            item["callable"]["name"],
            tuple(
                tuple(group)
                for group in item["callable"]["parameter_signature"]
            ),
            tuple(item["callable"]["identity_qualifiers"]),
        ): item
        for item in _relations(loaded["parts"])
    }
    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        symbol_types, candidate_type_names = _function_symbol_types(
            candidate, loaded
        )
        methods = _external_methods(candidate, loaded, symbol_types)
        matches.append(
            {
                "function_id": candidate["function_id"],
                "function": _public_callable(candidate),
                "relation": _public_relation(
                    relations[candidate["_identity"]]
                ),
                "external_types": _external_type_facts(
                    candidate,
                    loaded,
                    candidate_type_names,
                ),
                "external_methods": methods,
            }
        )
    return _source_result(
        "ue-itps.source-function.v1",
        loaded,
        {
            "selection": {"name": function_name},
            "match_count": len(matches),
            "matches": matches,
        },
        responsibility="Report external type and method references for all definitions matching one function name.",
        boundaries=[
            "External means not defined by the selected .cpp or its companion header.",
            "Type names are derived from local declaration syntax; wrapped template types remain one expression.",
            "Member-call receivers are replaced with locally declared type expressions when available.",
            "Called methods, inheritance, overloads, and included source are not followed.",
        ],
    )
