from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .common import result_document
from .source_declarators import _classify_declaration
from .source_parser import parse_csharp_file
from .source_tokens import _raw, _split_arguments, lex_source, token_pairs


SCHEMA_VERSION = "ue-itps.cs-function.v1"
RESPONSIBILITY = (
    "Report type and method references for all C# class methods "
    "matching one selected name."
)

_PARAMETER_MODIFIERS = {
    "in",
    "out",
    "params",
    "ref",
    "readonly",
    "scoped",
    "this",
}
_BUILTIN_TYPES = {
    "bool",
    "byte",
    "char",
    "decimal",
    "double",
    "dynamic",
    "float",
    "int",
    "long",
    "nint",
    "nuint",
    "object",
    "sbyte",
    "short",
    "string",
    "uint",
    "ulong",
    "ushort",
    "var",
    "void",
}


def _compact(value: str) -> str:
    return " ".join(value.split())


def _evidence(location: dict[str, Any]) -> dict[str, int]:
    result = {"line": int(location["line"])}
    if "end_line" in location:
        result["end_line"] = int(location["end_line"])
    return result


def _parameter_variables(parameters: str) -> list[dict[str, str]]:
    tokens = lex_source(parameters)
    forward, _ = token_pairs(tokens)
    variables: list[dict[str, str]] = []
    for start, end in _split_arguments(tokens, 0, len(tokens)):
        classification = _classify_declaration(
            tokens,
            forward,
            start,
            end,
        )
        if classification["kind"] != "variable":
            continue
        name_index = int(classification["name_index"])
        type_start = start
        while type_start < name_index:
            if (
                tokens[type_start].value == "["
                and type_start in forward
                and forward[type_start] < name_index
            ):
                type_start = forward[type_start] + 1
                continue
            if tokens[type_start].value in _PARAMETER_MODIFIERS:
                type_start += 1
                continue
            break
        type_expression = _compact(
            _raw(parameters, tokens, type_start, name_index)
        )
        if type_expression:
            variables.append(
                {
                    "name": str(classification["name"]),
                    "type_expression": type_expression,
                }
            )
    return variables


def _primary_type_name(type_expression: str) -> str | None:
    expression = re.sub(r"(?:\?|\[\])+$", "", type_expression.strip())
    expression = expression.split("<", 1)[0].strip()
    identifiers = re.findall(r"[A-Za-z_]\w*", expression)
    return identifiers[-1] if identifiers else None


def _external_types(
    parsed: dict[str, Any],
    class_item: dict[str, Any],
    method: dict[str, Any],
    parameters: list[dict[str, str]],
) -> list[str]:
    local_types = {
        str(item["name"])
        for item in parsed["classes"]
    }
    locals_and_parameters = [
        *parameters,
        *method.get("local_variables", []),
    ]
    shadowed_names = {
        str(item["name"])
        for item in locals_and_parameters
    }
    referenced_names = set(method.get("referenced_names", []))
    candidates = [
        str(item["type_expression"])
        for item in locals_and_parameters
    ]
    candidates.extend(
        str(field["type_expression"])
        for field in class_item["fields"]
        if (
            field["name"] in referenced_names
            and field["name"] not in shadowed_names
        )
    )
    bound_names = {
        *shadowed_names,
        *(str(field["name"]) for field in class_item["fields"]),
    }
    invocation_receivers = {
        str(operation.get("callee", "")).replace("::", ".").split(".", 1)[0]
        for operation in method["operations"]
        if operation["kind"] == "invocation"
        and "." in str(operation.get("callee", "")).replace("::", ".")
    }
    candidates.extend(
        str(name)
        for name in method.get("qualified_references", [])
        if name not in bound_names
        and name not in invocation_receivers
    )
    return sorted(
        {
            type_expression
            for type_expression in candidates
            if (
                (primary := _primary_type_name(type_expression))
                and primary not in local_types
                and primary.casefold() not in _BUILTIN_TYPES
                and primary[0].isupper()
                and not primary.isupper()
            )
        },
        key=str.casefold,
    )


def _symbol_types(
    class_item: dict[str, Any],
    method: dict[str, Any],
    parameters: list[dict[str, str]],
) -> dict[str, str]:
    result = {
        str(field["name"]): str(field["type_expression"])
        for field in class_item["fields"]
    }
    for item in parameters:
        result[str(item["name"])] = str(item["type_expression"])
    for item in method.get("local_variables", []):
        result[str(item["name"])] = str(item["type_expression"])
    return result


def _external_methods(
    class_item: dict[str, Any],
    method: dict[str, Any],
    parameters: list[dict[str, str]],
) -> list[str]:
    local_methods = {
        str(item["name"])
        for item in class_item["methods"]
    }
    symbol_types = _symbol_types(class_item, method, parameters)
    results: list[str] = []
    for operation in method["operations"]:
        if operation["kind"] != "invocation":
            continue
        callee = str(operation.get("callee", "")).replace("::", ".")
        segments = callee.split(".")
        method_name = segments[-1]
        receivers = segments[:-1]
        if not receivers and method_name not in local_methods:
            continue

        receiver_type: str | None = None
        remaining_receivers = receivers
        if receivers:
            receiver_type = symbol_types.get(receivers[0])
            if receiver_type:
                remaining_receivers = receivers[1:]
        if (
            receiver_type is None
            and len(receivers) >= 2
            and receivers[0] == "this"
        ):
            receiver_type = symbol_types.get(receivers[1])
            if receiver_type:
                remaining_receivers = receivers[2:]

        arguments = ", ".join(
            str(argument.get("expression", ""))
            for argument in operation.get("arguments", [])
        )
        public_callee = (
            ".".join(
                [
                    receiver_type,
                    *remaining_receivers,
                    method_name,
                ]
            )
            if receiver_type
            and receiver_type.casefold() not in _BUILTIN_TYPES
            and receiver_type != "var"
            else callee
        )
        expression = f"{public_callee}({arguments})"
        if expression not in results:
            results.append(expression)
    return results


def _match(
    parsed: dict[str, Any],
    class_item: dict[str, Any],
    method: dict[str, Any],
) -> dict[str, Any]:
    owner = str(class_item["name"])
    signature = _compact(str(method["signature"]))
    parameters = _parameter_variables(str(method["parameters"]))
    return {
        "function_id": f"{owner}::{signature}",
        "function": {
            "kind": (
                "constructor"
                if method["is_constructor"]
                else "method"
            ),
            "owner": owner,
            "name": str(method["name"]),
            "signature": signature,
            "parameters": _compact(str(method["parameters"])),
            "has_body": bool(method["has_body"]),
            "evidence": _evidence(method["location"]),
        },
        "external_types": _external_types(
            parsed,
            class_item,
            method,
            parameters,
        ),
        "external_methods": _external_methods(
            class_item,
            method,
            parameters,
        ),
    }


def inspect_cs_function(path: Path, function_name: str) -> dict[str, Any]:
    parsed = parse_csharp_file(path)
    matches = [
        _match(parsed, class_item, method)
        for class_item in parsed["classes"]
        for method in class_item["methods"]
        if method["name"] == function_name
    ]
    matches.sort(
        key=lambda item: (
            item["function"]["evidence"]["line"],
            item["function"]["owner"],
            item["function"]["signature"],
        )
    )
    problems = list(parsed["problems"])
    if not matches:
        problems.append(
            {
                "severity": "error",
                "code": "function-not-found",
                "selection": function_name,
                "message": "No matching C# class method was found",
            }
        )
    return result_document(
        SCHEMA_VERSION,
        {
            "source": parsed["path"],
            "selection": {"name": function_name},
            "match_count": len(matches),
            "matches": matches,
        },
        problems,
        responsibility=RESPONSIBILITY,
        boundaries=[
            "The result is a lexical C# projection, not a compiler semantic model.",
            "Only class and struct members declared in the selected file are matched.",
            "External types omit built-ins and types declared in the selected C# file.",
            "Type names are derived from declarations and unbound type-like qualifiers used in non-call member access.",
            "A locally typed root receiver is replaced with its type expression while the remaining member chain is preserved.",
            "Method references include same-class calls but called functions are not followed.",
            "Inheritance, referenced files, runtime effects, and compiler semantics are not inferred.",
        ],
    )
