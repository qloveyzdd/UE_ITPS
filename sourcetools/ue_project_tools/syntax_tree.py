"""Tree-sitter C# frontend for UE build and target rule analysis."""

from __future__ import annotations

from functools import lru_cache
import json
from typing import Any, Iterable

from tree_sitter import Language, Node, Parser
import tree_sitter_c_sharp as tscsharp


ENGINE = "tree-sitter/ast-outline+gdep"


@lru_cache(maxsize=1)
def _parser() -> Parser:
    return Parser(Language(tscsharp.language()))


def _walk(root: Node) -> Iterable[Node]:
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.named_children))


def _text(source: bytes, node: Node | None) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _compact(value: str) -> str:
    return " ".join(value.split())


def _location(node: Node) -> dict[str, int]:
    result = {"line": node.start_point.row + 1}
    end_line = node.end_point.row + 1
    if end_line != result["line"]:
        result["end_line"] = end_line
    return result


def _errors(root: Node) -> int:
    if not root.has_error:
        return 0
    return sum(1 for node in _walk(root) if node.type == "ERROR" or node.is_missing)


def _string_value(source: bytes, node: Node) -> str | None:
    raw = _text(source, node)
    if node.type == "string_literal":
        try:
            return str(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            return raw[1:-1] if len(raw) >= 2 else ""
    if node.type == "verbatim_string_literal" and raw.startswith('@"'):
        return raw[2:-1].replace('""', '"')
    if "raw_string_literal" in node.type:
        return raw.strip('"')
    return None


def _evaluation(source: bytes, node: Node) -> dict[str, Any]:
    literals = [
        value
        for descendant in _walk(node)
        if (value := _string_value(source, descendant)) is not None
    ]
    unresolved_kinds = {
        "identifier",
        "member_access_expression",
        "invocation_expression",
        "element_access_expression",
        "interpolated_string_expression",
    }
    unresolved = any(
        descendant.type in unresolved_kinds
        for descendant in _walk(node)
        if descendant is not node
    )
    return {
        "status": "unresolved" if unresolved else "literal",
        "literal_values": list(dict.fromkeys(literals)),
    }


def _argument_node(node: Node) -> Node:
    expression = node.child_by_field_name("expression")
    if expression is not None:
        return expression
    return node.named_children[-1] if node.named_children else node


def _control_contexts(source: bytes, node: Node) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    current = node.parent
    while current is not None:
        if current.type == "if_statement":
            condition = current.child_by_field_name("condition")
            consequence = current.child_by_field_name("consequence")
            alternative = current.child_by_field_name("alternative")
            branch = "then"
            if (
                alternative is not None
                and alternative.start_byte <= node.start_byte < alternative.end_byte
            ):
                branch = "else"
            elif consequence is None or not (
                consequence.start_byte <= node.start_byte < consequence.end_byte
            ):
                current = current.parent
                continue
            expression = _compact(_text(source, condition))
            contexts.append(
                {
                    "kind": "if",
                    "expression": expression,
                    "branch": branch,
                    "start_line": current.start_point.row + 1,
                    "span_width": current.end_point.row - current.start_point.row + 1,
                }
            )
        current = current.parent
    contexts.reverse()
    return contexts


def _operation(source: bytes, node: Node) -> dict[str, Any] | None:
    conditions = _control_contexts(source, node)
    common: dict[str, Any] = {
        "expression": _compact(_text(source, node)),
        "location": _location(node),
        "conditions": conditions,
        "applicability": "conditional" if conditions else "direct",
    }
    if conditions:
        common["control_path"] = [item["kind"] for item in conditions]
        common["control_details"] = [
            {
                **{
                    key: item[key]
                    for key in ("kind", "expression", "branch", "start_line")
                },
                "references": [item["expression"]] if item["expression"] else [],
            }
            for item in conditions
        ]
        common["related_symbols"] = list(
            dict.fromkeys(
                item["expression"] for item in conditions if item["expression"]
            )
        )
    if node.type == "invocation_expression":
        function = node.child_by_field_name("function")
        arguments_node = node.child_by_field_name("arguments")
        arguments = []
        for raw_argument in (
            arguments_node.named_children if arguments_node is not None else []
        ):
            argument = _argument_node(raw_argument)
            arguments.append(
                {
                    "expression": _compact(_text(source, argument)),
                    "evaluation": _evaluation(source, argument),
                }
            )
        literal_values = [
            value
            for argument in arguments
            for value in argument["evaluation"]["literal_values"]
        ]
        return {
            "kind": "invocation",
            "callee": _compact(_text(source, function)).replace("?.", "."),
            "arguments": arguments,
            "evaluation": {
                "status": (
                    "literal"
                    if all(
                        item["evaluation"]["status"] == "literal" for item in arguments
                    )
                    else "unresolved"
                ),
                "literal_values": list(dict.fromkeys(literal_values)),
            },
            **common,
        }
    if node.type == "assignment_expression":
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        operator = next(
            (
                _text(source, child)
                for child in node.children
                if not child.is_named and "=" in _text(source, child)
            ),
            "=",
        )
        return {
            "kind": "assignment",
            "target": _compact(_text(source, left)),
            "operator": operator,
            "value_expression": _compact(_text(source, right)),
            "evaluation": _evaluation(source, right or node),
            **common,
        }
    return None


def _parameters(source: bytes, node: Node | None) -> list[dict[str, str]]:
    if node is None:
        return []
    results: list[dict[str, str]] = []
    for parameter in node.named_children:
        if parameter.type != "parameter":
            continue
        name = _text(source, parameter.child_by_field_name("name")).strip()
        type_expression = _compact(_text(source, parameter.child_by_field_name("type")))
        if name and type_expression:
            results.append({"name": name, "type_expression": type_expression})
    return results


def _variables(source: bytes, root: Node, statement_type: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for statement in _walk(root):
        if statement.type != statement_type:
            continue
        declaration = next(
            (
                child
                for child in statement.named_children
                if child.type == "variable_declaration"
            ),
            None,
        )
        if declaration is None:
            continue
        type_node = declaration.child_by_field_name("type")
        if type_node is None and declaration.named_children:
            type_node = declaration.named_children[0]
        type_expression = _compact(_text(source, type_node))
        for declarator in declaration.named_children:
            if declarator.type != "variable_declarator":
                continue
            name = _text(source, declarator.child_by_field_name("name")).strip()
            if name and type_expression:
                results.append(
                    {
                        "name": name,
                        "type_expression": type_expression,
                        "location": _location(statement),
                    }
                )
    return results


def _method(source: bytes, node: Node) -> dict[str, Any]:
    name = _text(source, node.child_by_field_name("name")).strip()
    parameter_node = node.child_by_field_name("parameters")
    body = node.child_by_field_name("body")
    if body is None:
        body = next(
            (
                child
                for child in node.named_children
                if child.type in {"block", "arrow_expression_clause"}
            ),
            None,
        )
    signature_end = body.start_byte if body is not None else node.end_byte
    signature = _compact(
        source[node.start_byte : signature_end].decode("utf-8", errors="replace")
    ).rstrip(";")
    parameters_text = _text(source, parameter_node).strip()
    if parameters_text.startswith("(") and parameters_text.endswith(")"):
        parameters_text = parameters_text[1:-1]
    operations = []
    if body is not None:
        for descendant in _walk(body):
            operation = _operation(source, descendant)
            if operation is not None:
                operations.append((descendant.start_byte, operation))
    operations.sort(key=lambda item: item[0])
    referenced_names = []
    qualified_references = []
    if body is not None:
        for descendant in _walk(body):
            if descendant.type == "identifier":
                value = _text(source, descendant)
                if value not in referenced_names:
                    referenced_names.append(value)
            if descendant.type == "member_access_expression":
                root = _text(source, descendant).replace("?.", ".").split(".", 1)[0]
                if root and root not in qualified_references:
                    qualified_references.append(root)
    return {
        "name": name,
        "parameters": _compact(parameters_text),
        "parameter_variables": _parameters(source, parameter_node),
        "signature": signature,
        "has_body": body is not None,
        "is_constructor": node.type == "constructor_declaration",
        "location": _location(node),
        "declared_names": [
            item["name"]
            for item in _variables(source, body, "local_declaration_statement")
        ]
        if body is not None
        else [],
        "local_variables": (
            _variables(source, body, "local_declaration_statement")
            if body is not None
            else []
        ),
        "referenced_names": referenced_names,
        "qualified_references": qualified_references,
        "operations": [item for _, item in operations],
    }


def parse_csharp_model(text: str) -> dict[str, Any]:
    source = text.encode("utf-8")
    tree = _parser().parse(source)
    classes: list[dict[str, Any]] = []
    for node in _walk(tree.root_node):
        if node.type not in {"class_declaration", "struct_declaration"}:
            continue
        name = _text(source, node.child_by_field_name("name")).strip()
        if not name:
            continue
        base_list = next(
            (child for child in node.named_children if child.type == "base_list"),
            None,
        )
        bases = (
            [
                _compact(_text(source, child))
                for child in base_list.named_children
                if _text(source, child).strip()
            ]
            if base_list is not None
            else []
        )
        body = node.child_by_field_name("body")
        members = body.named_children if body is not None else []
        methods = [
            _method(source, member)
            for member in members
            if member.type in {"method_declaration", "constructor_declaration"}
        ]
        fields = []
        if body is not None:
            fields = _variables(source, body, "field_declaration")
        classes.append(
            {
                "kind": "class" if node.type == "class_declaration" else "struct",
                "name": name,
                "base_types": bases,
                "location": _location(node),
                "fields": fields,
                "methods": methods,
            }
        )
    return {
        "engine": ENGINE,
        "language": "csharp",
        "parse_error_count": _errors(tree.root_node),
        "classes": classes,
    }


def parse_csharp_syntax(text: str) -> dict[str, Any]:
    model = parse_csharp_model(text)
    return {
        "engine": model["engine"],
        "language": model["language"],
        "parse_error_count": model["parse_error_count"],
        "types": [
            {
                "kind": item["kind"],
                "name": item["name"],
                "base_types": item["base_types"],
                "location": item["location"],
            }
            for item in model["classes"]
        ],
        "functions": [
            {
                "name": method["name"],
                "signature": method["signature"],
                "has_body": method["has_body"],
                "location": method["location"],
                "calls": [
                    {
                        "callee": operation["callee"],
                        "location": operation["location"],
                    }
                    for operation in method["operations"]
                    if operation["kind"] == "invocation"
                ],
                "controls": [
                    {
                        "kind": detail["kind"],
                        "location": {"line": detail["start_line"]},
                    }
                    for operation in method["operations"]
                    for detail in operation.get("control_details", [])
                ],
            }
            for item in model["classes"]
            for method in item["methods"]
        ],
    }
