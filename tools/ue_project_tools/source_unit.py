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
from .source_controls import _conditions_for
from .source_flow import condition_spans
from .source_operations import parse_operations
from .source_declarations import (
    _FORBIDDEN_CALLABLE_NAMES,
    _TYPE_KEYWORDS,
    _class_field_names,
    _classify_declaration,
    _declaration_assignment,
    _declaration_name,
)
from .source_parser import parse_cpp_file
from .source_preprocessor import preprocessor_conditions
from .source_tokens import (
    Token,
    _evaluation,
    _location,
    _raw,
    _raw_from_values,
    _split_arguments,
    lex_source,
    token_pairs,
)


_HEADER_SUFFIXES = {".h", ".hpp"}
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
        }
        if index + 1 < len(tokens) and tokens[index + 1].value == "(" and index + 1 in forward:
            close = forward[index + 1]
            item["arguments"] = [
                _raw(text, tokens, start, end)
                for start, end in _split_arguments(tokens, index + 2, close)
            ]
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


_KNOWN_CALL_MACROS = {
    "TEXT",
    "UE_CLOG",
    "UE_LOG",
    "UE_LOGFMT",
}


def _scalar_literal(expression: str) -> tuple[bool, Any]:
    tokens = lex_source(expression.strip())
    sign = 1
    if len(tokens) == 2 and tokens[0].value in {"+", "-"}:
        sign = -1 if tokens[0].value == "-" else 1
        tokens = tokens[1:]
    if len(tokens) != 1:
        return False, None
    token = tokens[0]
    if token.kind == "identifier":
        if token.value == "true":
            return True, True
        if token.value == "false":
            return True, False
        if token.value in {"nullptr", "null", "NULL"}:
            return True, None
        return False, None
    if token.kind != "number":
        return False, None
    raw = re.sub(r"[uUlLfF]+$", "", token.value)
    try:
        if raw.casefold().startswith(("0x", "0b", "0o")):
            return True, sign * int(raw, 0)
        if any(marker in raw.casefold() for marker in (".", "e")):
            return True, sign * float(raw)
        return True, sign * int(raw, 0)
    except ValueError:
        return False, None


def _source_evaluation(
    expression: str, evaluation: dict[str, Any]
) -> dict[str, Any]:
    if evaluation.get("status") != "unresolved":
        return evaluation
    matched, value = _scalar_literal(expression)
    if not matched:
        return evaluation
    return {"status": "literal", "literal_values": [value]}


def _enhance_operation_evaluations(operation: dict[str, Any]) -> None:
    for argument in operation.get("arguments", []):
        argument["evaluation"] = _source_evaluation(
            argument["expression"], argument["evaluation"]
        )
    if "value_expression" in operation and "evaluation" in operation:
        operation["evaluation"] = _source_evaluation(
            operation["value_expression"], operation["evaluation"]
        )
    elif operation.get("kind") == "return" and "evaluation" in operation:
        operation["evaluation"] = _source_evaluation(
            operation["expression"], operation["evaluation"]
        )


def _call_kind(operation: dict[str, Any], owner: str | None) -> str:
    callee = operation.get("callee")
    if not isinstance(callee, str):
        return ""
    if callee in _KNOWN_CALL_MACROS:
        return "known_macro"
    if (
        "->" not in callee
        and "." not in callee
        and "::" not in callee
        and (
            callee == owner
            or re.fullmatch(r"(?:F|U|A|E|I|T)[A-Z][A-Za-z0-9_]*", callee)
        )
    ):
        return "construction_candidate"
    return "call"


def _operation_hierarchy(
    operations: list[dict[str, Any]],
    condition_expressions: list[tuple[int, str]],
) -> None:
    for index, operation in enumerate(operations, start=1):
        operation["operation_id"] = f"op-{index:04d}"
        operation["parent_operation_id"] = None
        operation["depth"] = 0
        operation["expression_role"] = "statement"

    for child_index, child in enumerate(operations):
        child_expression = child.get("expression")
        if not isinstance(child_expression, str) or not child_expression:
            continue
        candidates: list[tuple[int, int]] = []
        for parent_index, parent in enumerate(operations):
            if parent_index == child_index:
                continue
            parent_expression = parent.get("expression")
            if (
                not isinstance(parent_expression, str)
                or parent_expression == child_expression
                or child_expression not in parent_expression
                or parent["evidence"]["path"] != child["evidence"]["path"]
                or parent["evidence"]["line"] != child["evidence"]["line"]
            ):
                continue
            candidates.append((len(parent_expression), parent_index))
        if candidates:
            _, parent_index = min(candidates)
            parent = operations[parent_index]
            child["parent_operation_id"] = parent["operation_id"]
            if parent.get("kind") == "invocation":
                child["expression_role"] = "argument"
            elif parent.get("kind") == "assignment":
                child["expression_role"] = "value"
            elif parent.get("kind") == "return":
                child["expression_role"] = "return_value"

    by_id = {item["operation_id"]: item for item in operations}

    def depth(item: dict[str, Any], seen: set[str]) -> int:
        parent_id = item["parent_operation_id"]
        if parent_id is None or parent_id in seen or parent_id not in by_id:
            return 0
        return 1 + depth(by_id[parent_id], {*seen, parent_id})

    for operation in operations:
        operation["depth"] = depth(operation, {operation["operation_id"]})
        expression = operation.get("expression")
        line = operation["evidence"]["line"]
        if isinstance(expression, str) and any(
            condition_line == line and expression in condition_expression
            for condition_line, condition_expression in condition_expressions
        ):
            operation["expression_role"] = "condition"


def _operations(
    parts: list[dict[str, Any]], parsed_by_path: dict[Path, dict[str, Any]]
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for part in parts:
        body_range = part["_body_range"]
        if body_range is None:
            continue
        parsed = parsed_by_path[part["_path"]]
        parsed_operations = parse_operations(
            parsed["text"],
            parsed["tokens"],
            parsed["forward"],
            parsed["reverse"],
            body_range[0],
            body_range[1],
            include_control_metadata=True,
        )
        parsed_operations.extend(
            _return_and_construction_operations(parsed, body_range)
        )
        condition_expressions = [
            (
                int(span["start_line"]),
                str(span["condition"]["expression"]),
            )
            for span in condition_spans(
                parsed["tokens"],
                parsed["forward"],
                body_range[0],
                body_range[1],
            )
        ]
        public_operations: list[dict[str, Any]] = []
        for operation in parsed_operations:
            public_operation = dict(operation)
            _enhance_operation_evaluations(public_operation)
            call_kind = _call_kind(public_operation, part["owner"])
            if call_kind:
                public_operation["call_kind"] = call_kind
            public_operation["callable"] = {
                "function_id": part["function_id"],
                "kind": part["kind"],
                "owner": part["owner"],
                "name": part["name"],
                "parameter_signature": part["parameter_signature"],
                "identity_qualifiers": list(part["_identity"][4]),
            }
            location = public_operation.pop("location")
            public_operation["evidence"] = {
                **{
                    key: value
                    for key, value in part["evidence"].items()
                    if key in {"root", "path"}
                },
                **location,
            }
            public_operations.append(public_operation)
        public_operations.sort(
            key=lambda item: (
                item["evidence"]["root"],
                item["evidence"]["path"].casefold(),
                item["evidence"]["line"],
                item["kind"],
            )
        )
        _operation_hierarchy(public_operations, condition_expressions)
        results.extend(public_operations)
    return sorted(
        results,
        key=lambda item: (
            item["evidence"]["root"],
            item["evidence"]["path"].casefold(),
            item["evidence"]["line"],
            item["kind"],
        ),
    )


def _statement_end(tokens: list[Token], start: int, end: int) -> int:
    depth = 0
    for index in range(start, end):
        value = tokens[index].value
        if value in {"(", "[", "{"}:
            depth += 1
        elif value in {")", "]", "}"}:
            depth = max(0, depth - 1)
        elif value == ";" and depth == 0:
            return index
    return end


def _return_and_construction_operations(
    parsed: dict[str, Any], body_range: tuple[int, int]
) -> list[dict[str, Any]]:
    text = parsed["text"]
    tokens: list[Token] = parsed["tokens"]
    forward: dict[int, int] = parsed["forward"]
    start, end = body_range
    spans = condition_spans(tokens, forward, start, end)
    pp_context = preprocessor_conditions(text)
    results: list[dict[str, Any]] = []

    for index in range(start, end):
        token = tokens[index]
        if token.value == "return":
            expression_end = _statement_end(tokens, index + 1, end)
            expression_tokens = tokens[index + 1 : expression_end]
            results.append(
                {
                    "kind": "return",
                    "expression": _raw(
                        text, tokens, index + 1, expression_end
                    ),
                    "evaluation": _evaluation(expression_tokens),
                    "conditions": _conditions_for(
                        index, token, spans, pp_context
                    ),
                    "location": _location(
                        token,
                        tokens[expression_end]
                        if expression_end < len(tokens)
                        else token,
                    ),
                }
            )
            continue
        if token.value != "new" or index + 1 >= end:
            continue
        opening = next(
            (
                cursor
                for cursor in range(index + 1, end)
                if tokens[cursor].value in {"(", "{", ";", ","}
            ),
            None,
        )
        if opening is None or tokens[opening].value not in {"(", "{"}:
            continue
        if opening not in forward or forward[opening] >= end:
            continue
        close = forward[opening]
        arguments = [
            {
                "expression": _raw(text, tokens, argument_start, argument_end),
                "evaluation": _evaluation(
                    tokens[argument_start:argument_end]
                ),
            }
            for argument_start, argument_end in _split_arguments(
                tokens, opening + 1, close
            )
        ]
        results.append(
            {
                "kind": "construction",
                "type": _raw_from_values(tokens[index + 1 : opening]),
                "form": "parenthesized" if tokens[opening].value == "(" else "braced",
                "arguments": arguments,
                "expression": _raw(text, tokens, index, close + 1),
                "conditions": _conditions_for(index, token, spans, pp_context),
                "location": _location(token, tokens[close]),
            }
        )
    return results


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
    header_file: Path | None = None,
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
    raw_source_includes = extract_includes(source_text)
    source_includes: list[dict[str, Any]] = []
    for include in raw_source_includes:
        line = int(include.pop("line"))
        source_includes.append(
            {
                **include,
                "origin_unit": "source",
                "evidence": _file_evidence(
                    source, line, project_root, engine_root
                ),
                "resolution": resolve_include(
                    include,
                    source,
                    records,
                    project_root,
                    engine_root,
                ),
            }
        )

    selected_header: Path | None = None
    header_status = "absent"
    selection_evidence: dict[str, Any] | None = None
    header_candidates: list[dict[str, str]] = []
    if header_file is not None:
        selected_header = _validated_file(
            header_file, _HEADER_SUFFIXES, "Header file"
        )
        if not _is_relative_to(selected_header, project_root) and (
            engine_root is None or not _is_relative_to(selected_header, engine_root)
        ):
            raise ValueError(
                "Header file must be inside the selected project or resolved Engine: "
                f"{selected_header}"
            )
        header_status = "explicit"
    else:
        candidate_paths: dict[str, Path] = {}
        for include in source_includes:
            resolution = include["resolution"]
            if resolution["status"] != "resolved":
                continue
            location = resolution["location"]
            root = project_root if location["root"] == "project" else engine_root
            if root is None:
                continue
            candidate = (root / location["path"]).resolve()
            if candidate.suffix.casefold() not in _HEADER_SUFFIXES:
                continue
            if candidate.stem.casefold() != source.stem.casefold():
                continue
            if owner_for_path(candidate, records) is not source_owner:
                continue
            candidate_paths[normalized(candidate).casefold()] = candidate
        ordered_candidates = sorted(
            candidate_paths.values(), key=lambda item: normalized(item).casefold()
        )
        header_candidates = [
            rooted_path(path, project_root, engine_root)
            for path in ordered_candidates
        ]
        if len(ordered_candidates) == 1:
            selected_header = ordered_candidates[0]
            header_status = "selected"
            matching_include = next(
                include
                for include in source_includes
                if include["resolution"].get("location")
                == rooted_path(selected_header, project_root, engine_root)
            )
            selection_evidence = matching_include["evidence"]
        elif len(ordered_candidates) > 1:
            header_status = "ambiguous"

    parsed_files: list[tuple[Path, dict[str, Any]]] = [
        (source, parse_cpp_file(source))
    ]
    all_includes = list(source_includes)
    if selected_header is not None:
        parsed_header = parse_cpp_file(selected_header)
        parsed_files.append((selected_header, parsed_header))
        for include in extract_includes(parsed_header["text"]):
            line = int(include.pop("line"))
            all_includes.append(
                {
                    **include,
                    "origin_unit": "companion_header",
                    "evidence": _file_evidence(
                        selected_header,
                        line,
                        project_root,
                        engine_root,
                    ),
                    "resolution": resolve_include(
                        include,
                        selected_header,
                        records,
                        project_root,
                        engine_root,
                    ),
                }
            )

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
    if header_status == "ambiguous":
        problems.append(
            {
                "severity": "warning",
                "code": "source-unit-header-ambiguous",
                "candidates": header_candidates,
                "message": "Multiple directly included same-stem header candidates were found",
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
    header_fact: dict[str, Any] = {"status": header_status}
    if selected_header is not None:
        header_fact["location"] = rooted_path(
            selected_header, project_root, engine_root
        )
        header_fact["owner"] = public_owner(
            owner_for_path(selected_header, records)
        )
    if selection_evidence is not None:
        header_fact["selection_evidence"] = selection_evidence
    if header_candidates:
        header_fact["candidates"] = header_candidates

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
            "Only the selected .cpp and an explicit or uniquely evidenced companion header are read as C++ source.",
            *boundaries,
            "The result does not decide required dependencies, feature meaning, implementation correctness, or build-rule changes.",
            "Validation reports input and locally observable structural problems; ok does not prove compilation or runtime behavior.",
        ],
    )


def list_source_includes(
    source_file: Path,
    header_file: Path | None = None,
    engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = _load_source_unit(source_file, header_file, engine_override)
    return _source_result(
        "ue-itps.source-includes.v1",
        loaded,
        {"includes": loaded["includes"]},
        responsibility="Report direct include spellings and deterministic filesystem provenance.",
        boundaries=[
            "Referenced files are located for provenance but are never recursively read.",
            "A resolved include is a unique filesystem candidate, not proof of the effective compiler include path.",
            "Physical ownership does not prove that a dependency is required or correctly declared.",
        ],
    )


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
            class_evidence = _public_location(
                path,
                class_item["location"],
                project_root,
                engine_root,
            )
            member_variable_details = [
                {
                    "kind": "variable",
                    "name": item["name"],
                    "type_expression": item["type_expression"],
                    "evidence": item["evidence"],
                }
                for item in variables
                if item["scope"] == "member"
                and item.get("owner") == class_item["name"]
                and item["evidence"]["root"] == class_evidence["root"]
                and item["evidence"]["path"] == class_evidence["path"]
                and class_evidence["line"]
                <= item["evidence"]["line"]
                <= class_evidence.get("end_line", class_evidence["line"])
            ]
            member_function_details = [
                {
                    "kind": "function",
                    "name": _callable_name(
                        member["name"], member["signature"]
                    ),
                    "signature": " ".join(member["signature"].split()),
                    "evidence": _public_location(
                        path,
                        member["location"],
                        project_root,
                        engine_root,
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
                        "evidence": class_evidence,
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
                    "member_variables": projected_field_names,
                    "member_functions": sorted(
                        {
                            _callable_name(
                                member["name"], member["signature"]
                            )
                            for member in class_item["members"]
                            if member["name"] not in _SOURCE_MACROS
                        },
                        key=str.casefold,
                    ),
                    "member_details": sorted(
                        [
                            *member_variable_details,
                            *member_function_details,
                        ],
                        key=lambda item: (
                            item["evidence"]["line"],
                            item["kind"],
                            item["name"].casefold(),
                        ),
                    ),
                    "evidence": class_evidence,
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
    ), problems


def list_source_types(
    source_file: Path,
    header_file: Path | None = None,
    engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = _load_source_unit(source_file, header_file, engine_override)
    variables, unresolved = _variable_facts(loaded)
    types, type_problems = _type_facts(loaded, variables)
    type_macros = [
        macro
        for macro in loaded["macros"]
        if macro["name"]
        in {
            "UCLASS",
            "USTRUCT",
            "UENUM",
            "UINTERFACE",
            "GENERATED_BODY",
            "GENERATED_UCLASS_BODY",
            "GENERATED_USTRUCT_BODY",
        }
    ]
    return _source_result(
        "ue-itps.source-types.v1",
        loaded,
        {
            "types": types,
            "unresolved_declarations": [
                item for item in unresolved if item["scope"] == "member"
            ],
            "type_macros": type_macros,
        },
        responsibility="Index class, struct, enum, inheritance, member-name, and UE type-macro facts.",
        boundaries=[
            "Member lists are lexical indexes and are not semantic summaries.",
            "Type macros retain their own evidence and are not attached to a type by heuristic proximity.",
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


def _parameter_variables(part: dict[str, Any]) -> list[dict[str, Any]]:
    parameters = part["parameters"]
    if not parameters.strip() or parameters.strip() == "void":
        return []
    wrapper = f"({parameters})"
    tokens = lex_source(wrapper)
    forward, _ = token_pairs(tokens)
    if not tokens or tokens[0].value != "(" or 0 not in forward:
        return []
    results: list[dict[str, Any]] = []
    for position, (start, end) in enumerate(
        _split_arguments(tokens, 1, forward[0])
    ):
        group = tokens[start:end]
        if not group:
            continue
        default_index = next(
            (index for index, token in enumerate(group) if token.value == "="),
            len(group),
        )
        declaration_tokens = group[:default_index]
        name_index = next(
            (
                index
                for index in range(len(declaration_tokens) - 1, -1, -1)
                if declaration_tokens[index].kind == "identifier"
                and (
                    index == len(declaration_tokens) - 1
                    or declaration_tokens[index + 1].value == "["
                )
            ),
            None,
        )
        if name_index is None or name_index == 0:
            continue
        name = declaration_tokens[name_index].value
        type_expression = _raw_from_values(declaration_tokens[:name_index])
        if not type_expression:
            continue
        item: dict[str, Any] = {
            "scope": "parameter",
            "name": name,
            "type_expression": type_expression,
            "declaration": _raw_from_values(group),
            "position": position,
            "callable": {
                "function_id": part["function_id"],
                "kind": part["kind"],
                "owner": part["owner"],
                "name": part["name"],
                "parameter_signature": part["parameter_signature"],
                "identity_qualifiers": list(part["_identity"][4]),
            },
            "evidence": part["evidence"],
        }
        if default_index < len(group):
            item["initializer"] = _raw_from_values(group[default_index + 1 :])
        results.append(item)
    return results


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
    callable_fact: dict[str, Any] | None,
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
        while (
            statement_start + 1 < semicolon
            and tokens[statement_start].kind == "identifier"
            and re.fullmatch(r"[A-Z][A-Z0-9_]*", tokens[statement_start].value)
            and tokens[statement_start + 1].value == "("
            and statement_start + 1 in parsed["forward"]
            and parsed["forward"][statement_start + 1] < semicolon
        ):
            statement_start = parsed["forward"][statement_start + 1] + 1
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
        if (
            statement_start + 1 < semicolon
            and tokens[statement_start].value
            in {"public", "protected", "private"}
            and tokens[statement_start + 1].value == ":"
        ):
            statement_start += 2
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
            if callable_fact is not None:
                item["callable"] = callable_fact
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
            "declaration": _normalized_text(
                _raw(text, tokens, statement_start, semicolon)
            ),
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
        if callable_fact is not None:
            item["callable"] = callable_fact
        if assignment < semicolon:
            item["initializer"] = _raw(
                text, tokens, assignment + 1, semicolon
            )
        results.append(item)
    return results, unresolved


def _variable_facts(
    loaded: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    project_root = loaded["project_root"]
    engine_root = loaded["engine_root"]
    results: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    definition_parts = [
        part for part in loaded["parts"] if part["role"] == "definition"
    ]
    for part in definition_parts:
        results.extend(_parameter_variables(part))
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
            callable_fact=None,
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
                callable_fact=None,
                project_root=project_root,
                engine_root=engine_root,
                excluded_ranges=member_excluded,
            )
            results.extend(member_variables)
            unresolved.extend(member_unresolved)
    for part in definition_parts:
        body_range = part["_body_range"]
        if body_range is None:
            continue
        parsed = loaded["parsed_by_path"][part["_path"]]
        callable_fact = {
            "function_id": part["function_id"],
            "kind": part["kind"],
            "owner": part["owner"],
            "name": part["name"],
            "parameter_signature": part["parameter_signature"],
            "identity_qualifiers": list(part["_identity"][4]),
        }
        local_variables, local_unresolved = _declaration_variables(
            parsed,
            part["_path"],
            body_range[0],
            body_range[1],
            scope="local",
            owner=None,
            callable_fact=callable_fact,
            project_root=project_root,
            engine_root=engine_root,
        )
        results.extend(local_variables)
        unresolved.extend(local_unresolved)
    unique = {
        (
            item["scope"],
            item["name"],
            item["evidence"]["root"],
            item["evidence"]["path"],
            item["evidence"]["line"],
            str(item.get("callable")),
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


def list_source_variables(
    source_file: Path,
    header_file: Path | None = None,
    engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = _load_source_unit(source_file, header_file, engine_override)
    variables, unresolved = _variable_facts(loaded)
    variable_macros = [
        macro for macro in loaded["macros"] if macro["name"] == "UPROPERTY"
    ]
    return _source_result(
        "ue-itps.source-variables.v1",
        loaded,
        {
            "variables": variables,
            "unresolved_declarations": unresolved,
            "variable_macros": variable_macros,
        },
        responsibility="Index conservatively recognized file, member, parameter, and local variable declarations.",
        boundaries=[
            "C++ declarations that cannot be distinguished lexically are reported as unresolved rather than guessed.",
            "Comma-separated, structured-binding, macro-generated, and complex declarator forms may be incomplete.",
            "Initializers are source expressions and are not evaluated.",
        ],
        additional_problems=[
            {
                "severity": "warning",
                "code": "source-variable-declaration-unresolved",
                "count": len(unresolved),
                "message": (
                    "One or more declaration-shaped statements could not be "
                    "classified conservatively"
                ),
            }
        ]
        if unresolved
        else None,
    )


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
    header_file: Path | None = None,
    engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = _load_source_unit(source_file, header_file, engine_override)
    functions = _function_facts(loaded["parts"])
    _, all_unresolved = _variable_facts(loaded)
    unresolved = [
        item
        for item in all_unresolved
        if item["scope"] in {"file", "member"}
    ]
    invalid_names = [
        item for item in functions if item["name"] in _TYPE_KEYWORDS
    ]
    function_macros = [
        macro for macro in loaded["macros"] if macro["name"] == "UFUNCTION"
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
    function_name: str | None = None,
    *,
    function_id: str | None = None,
    owner: str | None = None,
    parameters: str | None = None,
    header_file: Path | None = None,
    engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = _load_source_unit(source_file, header_file, engine_override)
    if function_name is None and function_id is None:
        raise ValueError("Pass function_name or function_id")
    if function_name is not None and function_id is not None:
        raise ValueError("Pass only one of function_name or function_id")
    candidates = [
        part
        for part in loaded["parts"]
        if part["role"] == "definition"
        and (
            (function_id is not None and part["function_id"] == function_id)
            or (
                function_id is None
                and part["name"] == function_name
            )
        )
        and (owner is None or part["owner"] == owner)
        and (
            parameters is None
            or _normalized_text(part["parameters"])
            == _normalized_text(parameters)
        )
    ]
    if not candidates:
        selection = (
            function_id
            if function_id is not None
            else f"{owner + '::' if owner else ''}{function_name}"
        )
        return _source_result(
            "ue-itps.source-function.v1",
            loaded,
            {
                "selection": {
                    "function_id": function_id,
                    "name": function_name,
                    "owner": owner,
                    "parameters": parameters,
                },
                "function_id": function_id,
                "function": None,
                "relation": None,
                "operations": [],
            },
            responsibility="Report operations and control facts for one explicitly selected function definition.",
            boundaries=[
                "Only the selected function body is projected; called functions are not followed.",
                "Calls retain source expressions and are not assigned external meaning without unique evidence.",
                "Operations are conservative lexical facts, not runtime order, effects, or feature interpretation.",
            ],
            additional_problems=[
                {
                    "severity": "error",
                    "code": "function-not-found",
                    "selection": selection,
                    "message": "No matching function definition was found",
                }
            ],
        )
    if len(candidates) > 1:
        return _source_result(
            "ue-itps.source-function.v1",
            loaded,
            {
                "selection": {
                    "function_id": function_id,
                    "name": function_name,
                    "owner": owner,
                    "parameters": parameters,
                },
                "function_id": function_id,
                "function": None,
                "relation": None,
                "operations": [],
                "candidates": [
                    {
                        "function_id": part["function_id"],
                        "owner": part["owner"],
                        "name": part["name"],
                        "parameters": part["parameters"],
                        "qualifiers": part["qualifiers"],
                        "evidence": part["evidence"],
                    }
                    for part in candidates
                ],
            },
            responsibility="Report operations and control facts for one explicitly selected function definition.",
            boundaries=[
                "Only the selected function body is projected; called functions are not followed.",
                "Calls retain source expressions and are not assigned external meaning without unique evidence.",
                "Operations are conservative lexical facts, not runtime order, effects, or feature interpretation.",
            ],
            additional_problems=[
                {
                    "severity": "error",
                    "code": "function-selection-ambiguous",
                    "candidate_count": len(candidates),
                    "message": (
                        "Multiple function definitions matched; use "
                        "function_id or additional selectors"
                    ),
                }
            ],
        )
    selected = candidates[0]
    relation = next(
        item
        for item in _relations(loaded["parts"])
        if (
            item["callable"]["kind"],
            item["callable"]["owner"] or "",
            item["callable"]["name"],
            tuple(
                tuple(group)
                for group in item["callable"]["parameter_signature"]
            ),
            tuple(item["callable"]["identity_qualifiers"]),
        )
        == selected["_identity"]
    )
    return _source_result(
        "ue-itps.source-function.v1",
        loaded,
        {
            "function_id": selected["function_id"],
            "function": _public_callable(selected),
            "relation": relation,
            "operations": _operations(
                [selected], loaded["parsed_by_path"]
            ),
        },
        responsibility="Report operations and control facts for one explicitly selected function definition.",
        boundaries=[
            "Only the selected function body is projected; called functions are not followed.",
            "Calls retain source expressions and are not assigned external meaning without unique evidence.",
            "Operations are conservative lexical facts, not runtime order, effects, or feature interpretation.",
        ],
    )
