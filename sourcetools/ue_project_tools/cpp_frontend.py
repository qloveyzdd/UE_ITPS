from __future__ import annotations

from importlib.metadata import version as package_version
import json
from pathlib import Path
import re
from typing import Any, Iterator

from tree_sitter import Language, Node, Parser
import tree_sitter_ue_cpp

from .common import normalized
from .ue_cpp_conventions import (
    is_ignored_external_macro,
    is_ignored_external_member_call,
    is_ue_function_like_macro,
    is_ue_same_type_static_accessor,
    ue_delegate_operation,
)


ENGINE = "tree-sitter/ue-cpp"
_TYPE_NODES = {
    "class_specifier": "class",
    "struct_specifier": "struct",
    "union_specifier": "union",
    "enum_specifier": "enum",
}
_CONTAINER_NODES = {
    "translation_unit",
    "declaration_list",
    "linkage_specification",
    "template_declaration",
    "preproc_if",
    "preproc_ifdef",
    "preproc_elif",
    "preproc_else",
}
_CONTROL_NODES = {
    "if_statement": "if_statement",
    "switch_statement": "switch_statement",
    "for_statement": "for_statement",
    "for_range_loop": "for_range_loop",
    "while_statement": "while_statement",
    "do_statement": "do_statement",
    "try_statement": "try_statement",
    "throw_statement": "throw_expression",
    "return_statement": "return_statement",
}
_TOKEN_RE = re.compile(r'::|->|\.\.\.|"(?:\\.|[^"\\])*"|[A-Za-z_]\w*|\d+|[^\s]')
_PRIMITIVE_TYPES = {
    "auto",
    "bool",
    "char",
    "double",
    "float",
    "int",
    "long",
    "short",
    "signed",
    "unsigned",
    "void",
    "wchar_t",
}
class CppFrontendError(ValueError):
    pass


def frontend_version() -> str:
    try:
        return f"tree-sitter-ue-cpp {package_version('tree-sitter-ue-cpp')}"
    except Exception:
        return "tree-sitter-ue-cpp unknown"


def _parser() -> Parser:
    try:
        return Parser(Language(tree_sitter_ue_cpp.language()))
    except Exception as exc:
        raise CppFrontendError(
            f"Unable to load Tree-sitter UE C++ grammar: {exc}"
        ) from exc


def _normal_key(value: str | Path) -> str:
    return normalized(Path(value).resolve()).casefold()


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _canonical_cpp(value: str) -> str:
    """Normalize one syntax-derived C++ fragment without changing its tokens."""
    tokens = _TOKEN_RE.findall(value)
    result = ""
    previous = ""
    for token in tokens:
        if (
            previous
            and (previous[-1].isalnum() or previous[-1] == "_")
            and (token[0].isalnum() or token[0] == "_")
        ):
            result += " "
        result += token
        previous = token
    return result


def _line(node: Node) -> int:
    return int(node.start_point.row) + 1


def _end_line(node: Node) -> int:
    return max(_line(node), int(node.end_point.row) + 1)


def _walk(node: Node) -> Iterator[Node]:
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(reversed(current.named_children))


def _descendant(node: Node | None, kinds: set[str]) -> Node | None:
    if node is None:
        return None
    return next((item for item in _walk(node) if item.type in kinds), None)


def _string_literals(node: Node | None, source: bytes) -> list[str]:
    if node is None:
        return []
    results: list[str] = []
    for current in _walk(node):
        if current.type != "string_literal":
            continue
        raw = _text(current, source).strip()
        opening = raw.find('"')
        if opening < 0:
            continue
        literal = raw[opening:]
        try:
            value = str(json.loads(literal))
        except (json.JSONDecodeError, TypeError):
            value = literal[1:-1] if literal.endswith('"') else literal[1:]
        if value not in results:
            results.append(value)
    return results


def _cpp_name_path(node: Node | None, source: bytes) -> list[str]:
    if node is None:
        return []
    if node.type in {
        "identifier",
        "field_identifier",
        "namespace_identifier",
        "type_identifier",
        "this",
    }:
        value = _text(node, source).strip()
        return [value] if value else []
    if node.type == "destructor_name":
        name = next(iter(node.named_children), None)
        value = _text(name, source).strip() if name is not None else ""
        return [f"~{value}"] if value else []
    if node.type in {"operator_name", "literal_operator_name"}:
        value = _canonical_cpp(_text(node, source))
        return [value] if value else []
    if node.type in {"template_method", "template_function", "template_type"}:
        name = node.child_by_field_name("name")
        if name is None and node.named_children:
            name = node.named_children[0]
        return _cpp_name_path(name, source)
    if node.type in {"field_expression", "qualified_identifier"}:
        left = node.child_by_field_name("argument") or node.child_by_field_name("scope")
        right = node.child_by_field_name("field") or node.child_by_field_name("name")
        return [*_cpp_name_path(left, source), *_cpp_name_path(right, source)]
    if node.type == "call_expression":
        return _cpp_name_path(node.child_by_field_name("function"), source)
    if len(node.named_children) == 1:
        return _cpp_name_path(node.named_children[0], source)
    return []


def _template_arguments(node: Node | None, source: bytes) -> list[str]:
    if node is None:
        return []
    arguments = node.child_by_field_name("arguments")
    if arguments is None or arguments.type != "template_argument_list":
        return []
    return [_compact(_text(child, source)) for child in arguments.named_children]


def _callee_fact(node: Node, source: bytes) -> dict[str, Any]:
    target = node
    receiver = None
    if node.type == "field_expression":
        receiver = node.child_by_field_name("argument")
        target = node.child_by_field_name("field") or node
        receiver_kind = "member"
    elif node.type == "qualified_identifier":
        receiver = node.child_by_field_name("scope")
        target = node.child_by_field_name("name") or node
        receiver_kind = "scope"
    else:
        receiver_kind = None
    path = _cpp_name_path(node, source)
    return {
        "path": path,
        "receiver": _canonical_cpp(_text(receiver, source))
        if receiver is not None
        else None,
        "receiver_kind": receiver_kind,
        "target_name": path[-1] if path else _compact(_text(target, source)),
        "template_arguments": _template_arguments(target, source),
    }


def _macros(root: Node, source: bytes, file_key: str) -> list[dict[str, Any]]:
    results = []
    for node in _walk(root):
        if node.type != "ue_macro_invocation":
            continue
        name_node = node.child_by_field_name("head")
        arguments_node = node.child_by_field_name("arguments")
        if name_node is None or arguments_node is None:
            continue
        start = int(node.start_byte)
        end = int(arguments_node.end_byte)
        head = _text(name_node, source).rstrip()
        name = head[:-1].strip() if head.endswith("(") else head
        expression = source[start:end].decode("utf-8", errors="replace")
        arguments = [
            {
                "expression": _compact(_text(argument, source)),
                "literal_values": _string_literals(argument, source),
            }
            for argument in arguments_node.named_children
            if argument.type == "ue_macro_argument"
        ]
        results.append(
            {
                "name": name,
                "arguments": arguments,
                "tokens": _TOKEN_RE.findall(expression),
                "expression": re.sub(r"\s+", "", expression),
                "file": file_key,
                "line": source.count(b"\n", 0, start) + 1,
                "end_line": source.count(b"\n", 0, end) + 1,
                "start_offset": start,
                "end_offset": end,
            }
        )
    return results


def _includes(root: Node, source: bytes, file_key: str) -> list[dict[str, Any]]:
    results = []
    for node in _walk(root):
        if node.type != "preproc_include":
            continue
        path = node.child_by_field_name("path")
        if path is None:
            continue
        raw = _text(path, source).strip()
        if path.type == "ue_generated_header_path":
            kind = "generated_header"
            syntax = "quote"
            spelling = raw[1:-1]
        elif path.type == "ue_inline_generated_cpp_path":
            kind = "generated_source"
            syntax = "macro"
            spelling = raw
        elif path.type == "system_lib_string":
            kind = "regular"
            syntax = "angle"
            spelling = raw[1:-1]
        elif path.type == "string_literal":
            kind = "regular"
            syntax = "quote"
            spelling = raw[1:-1]
        else:
            kind = "regular"
            syntax = "macro"
            spelling = raw
        results.append(
            {
                "source_file": file_key,
                "included_file": None,
                "spelling": spelling.replace("\\", "/"),
                "syntax": syntax,
                "kind": kind,
                "line": _line(node),
            }
        )
    return results


def _declarator_name_path(node: Node | None, source: bytes) -> list[str]:
    if node is None:
        return []
    current = node
    while current.type in {
        "function_declarator",
        "pointer_declarator",
        "reference_declarator",
        "parenthesized_declarator",
        "array_declarator",
        "init_declarator",
    }:
        child = current.child_by_field_name("declarator")
        if child is None:
            break
        current = child
    return _cpp_name_path(current, source)


def _name_from_declarator(node: Node | None, source: bytes) -> tuple[str, str]:
    path = _declarator_name_path(node, source)
    return (path[-1], "::".join(path)) if path else ("", "")


def _declarator_modifiers(node: Node | None, source: bytes) -> tuple[str, str]:
    prefix: list[str] = []
    suffix: list[str] = []
    current = node
    while current is not None:
        child = current.child_by_field_name("declarator")
        if current.type in {"pointer_declarator", "abstract_pointer_declarator"}:
            prefix.append("*")
        elif current.type in {
            "reference_declarator",
            "reference_field_declarator",
            "abstract_reference_declarator",
        }:
            token = next(
                (
                    _text(item, source)
                    for item in current.children
                    if not item.is_named and _text(item, source) in {"&", "&&"}
                ),
                "&",
            )
            prefix.append(token)
        elif current.type == "array_declarator":
            size = current.child_by_field_name("size")
            suffix.append(
                f"[{_compact(_text(size, source)) if size is not None else ''}]"
            )
        if child is None:
            break
        current = child
    return "".join(prefix), "".join(reversed(suffix))


def _type_references(node: Node | None, source: bytes) -> list[str]:
    if node is None:
        return []
    results: list[str] = []

    def visit(current: Node) -> None:
        if current.type == "qualified_identifier":
            value = "::".join(_cpp_name_path(current, source))
            if value and value not in results:
                results.append(value)
            name = current.child_by_field_name("name")
            if name is not None and name.type in {"template_type", "template_function"}:
                arguments = name.child_by_field_name("arguments")
                if arguments is not None:
                    for child in arguments.named_children:
                        visit(child)
            return
        if current.type in {"template_type", "template_function"}:
            name = current.child_by_field_name("name")
            value = "::".join(_cpp_name_path(name, source))
            if value and value not in results:
                results.append(value)
            arguments = current.child_by_field_name("arguments")
            if arguments is not None:
                for child in arguments.named_children:
                    visit(child)
            return
        if current.type in {
            "type_identifier",
            "primitive_type",
            "sized_type_specifier",
        }:
            value = _compact(_text(current, source))
            if value and value not in results:
                results.append(value)
            return
        for child in current.named_children:
            visit(child)

    visit(node)
    return results


def _type_fact(node: Node | None, source: bytes) -> dict[str, Any]:
    expression = _canonical_cpp(_text(node, source)) if node is not None else ""
    references = _type_references(node, source)
    primary = references[0] if references else None
    return {
        "expression": expression,
        "name": primary.rsplit("::", 1)[-1] if primary else None,
        "qualified_name": primary,
        "references": references,
    }


def _storage_classes(node: Node, source: bytes) -> list[str]:
    return [
        _text(child, source)
        for child in node.named_children
        if child.type == "storage_class_specifier"
    ]


def _is_scoped_enum(node: Node, source: bytes) -> bool:
    name = node.child_by_field_name("name")
    for child in node.children:
        if name is not None and child.start_byte >= name.start_byte:
            break
        if not child.is_named and _text(child, source) in {"class", "struct"}:
            return True
    return False


def _leading_macro_expressions(
    node: Node, macros_by_start: dict[int, dict[str, Any]]
) -> list[str]:
    results: list[str] = []
    current = node.prev_named_sibling
    while current is not None:
        if current.type == "comment":
            current = current.prev_named_sibling
            continue
        if current.type != "ue_macro_invocation":
            break
        macro = macros_by_start.get(int(current.start_byte))
        if macro is not None:
            results.append(str(macro["expression"]))
        current = current.prev_named_sibling
    results.reverse()
    return results


def _parameter_facts(function_declarator: Node, source: bytes) -> list[dict[str, Any]]:
    parameters = function_declarator.child_by_field_name("parameters")
    if parameters is None:
        return []
    results = []
    for parameter in parameters.named_children:
        if parameter.type not in {
            "parameter_declaration",
            "optional_parameter_declaration",
        }:
            continue
        declarator = parameter.child_by_field_name("declarator")
        name, _ = _name_from_declarator(declarator, source)
        specifiers = []
        for index, child in enumerate(parameter.children):
            if not child.is_named or child == declarator:
                continue
            if child.type in {"ue_parameter_macro", "ue_parameter_modifier"}:
                continue
            if parameter.field_name_for_child(index) == "default_value":
                continue
            specifiers.append(child)
        base_type = _type_fact(parameter.child_by_field_name("type"), source)
        type_expression = _canonical_cpp(
            " ".join(_text(child, source) for child in specifiers)
        )
        prefix, suffix = _declarator_modifiers(declarator, source)
        type_expression = _canonical_cpp(f"{type_expression}{prefix}{suffix}")
        results.append(
            {
                "name": name,
                "type_expression": type_expression,
                "type": base_type,
            }
        )
    return results


def _base_types(node: Node, source: bytes) -> list[str]:
    clause = next(
        (child for child in node.named_children if child.type == "base_class_clause"),
        None,
    )
    if clause is None:
        return []
    results = []
    for child in clause.named_children:
        if child.type in {"access_specifier", "virtual"}:
            continue
        value = _canonical_cpp(_text(child, source))
        if value and value not in results:
            results.append(value)
    return results


def _base_type_facts(node: Node, source: bytes) -> list[dict[str, Any]]:
    clause = next(
        (child for child in node.named_children if child.type == "base_class_clause"),
        None,
    )
    if clause is None:
        return []
    return [
        _type_fact(child, source)
        for child in clause.named_children
        if child.type != "access_specifier"
    ]


def _type_expression(declaration: Node, source: bytes) -> str:
    type_node = declaration.child_by_field_name("type")
    return _compact(_text(type_node, source)) if type_node is not None else ""


def _declarators(declaration: Node) -> list[Node]:
    return [
        child
        for index, child in enumerate(declaration.children)
        if child.is_named and declaration.field_name_for_child(index) == "declarator"
    ]


def _function_declarator(node: Node) -> Node | None:
    return _descendant(node, {"function_declarator"})


def _function_qualifiers(
    node: Node, function_declarator: Node, source: bytes
) -> list[str]:
    values: set[str] = set()
    parameters = function_declarator.child_by_field_name("parameters")
    for child in function_declarator.named_children:
        if parameters is not None and child.start_byte < parameters.end_byte:
            continue
        if child.type in {"type_qualifier", "virtual_specifier"}:
            value = _text(child, source)
            if value in {"const", "override", "final"}:
                values.add(value)
    for child in node.children:
        if child.end_byte > function_declarator.start_byte:
            continue
        value = _text(child, source)
        if child.type == "storage_class_specifier" and value == "static":
            values.add(value)
        elif child.type == "virtual" or value == "virtual":
            values.add("virtual")
    return [
        value
        for value in ("const", "static", "virtual", "override", "final")
        if value in values
    ]


def _function_fact(
    node: Node,
    function_declarator: Node,
    source: bytes,
    file_key: str,
    namespaces: tuple[str, ...],
    owners: tuple[str, ...],
    role: str,
) -> dict[str, Any] | None:
    name_path = _declarator_name_path(function_declarator, source)
    if not name_path:
        return None
    name = name_path[-1]
    owner_parts = list(owners)
    if len(name_path) > 1:
        prefix_parts = name_path[:-1]
        if namespaces and prefix_parts[: len(namespaces)] == list(namespaces):
            prefix_parts = prefix_parts[len(namespaces) :]
        owner_parts = prefix_parts
    owner = "::".join(owner_parts) or None
    qualified_parts = [*namespaces, *owner_parts, name]
    qualified_name = "::".join(qualified_parts)
    parameters = _parameter_facts(function_declarator, source)
    parameter_text = ", ".join(
        f"{item['type_expression']} {item['name']}".strip() for item in parameters
    )
    body = node.child_by_field_name("body")
    declaration_end = body.start_byte if body is not None else node.end_byte
    declaration_text = _compact(
        source[node.start_byte : declaration_end].decode("utf-8", errors="replace")
    ).rstrip(";")
    qualifiers = _function_qualifiers(node, function_declarator, source)
    identity = "|".join(
        (
            "method" if owner else "free_function",
            "::".join(namespaces),
            owner or "",
            name,
            ",".join(item["type_expression"] for item in parameters),
            ",".join(value for value in qualifiers if value in {"const", "static"}),
        )
    )
    return {
        "usr": identity,
        "kind": "method" if owner else "free_function",
        "namespace": "::".join(namespaces) or None,
        "owner": owner,
        "name": name,
        "qualified_name": qualified_name,
        "parameters": parameter_text,
        "parameter_facts": parameters,
        "signature": declaration_text or _compact(_text(function_declarator, source)),
        "return_type": _type_fact(node.child_by_field_name("type"), source),
        "qualifiers": qualifiers,
        "role": role,
        "linkage": "internal" if "static" in qualifiers else "external",
        "file": file_key,
        "line": _line(node),
        "end_line": _end_line(node),
        "start_offset": int(node.start_byte),
        "end_offset": int(node.end_byte),
    }


def _function_addresses(arguments: Node | None, source: bytes) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    if arguments is None:
        return results
    for argument in arguments.named_children:
        for current in _walk(argument):
            if current.type != "pointer_expression":
                continue
            spelling = _canonical_cpp(_text(current, source))
            if not spelling.startswith("&"):
                continue
            qualified_name = spelling[1:]
            if not qualified_name:
                continue
            owner, separator, name = qualified_name.rpartition("::")
            result = {"name": name if separator else qualified_name}
            if separator:
                result["owner_type"] = owner
                result["qualified_name"] = qualified_name
            else:
                result["qualified_name"] = qualified_name
            results.append(result)
    return results


def _function_references(
    node: Node,
    fact: dict[str, Any],
    source: bytes,
) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    call_details: list[dict[str, Any]] = []
    local_variables: list[dict[str, str]] = []
    identifier_references: list[dict[str, Any]] = []
    variable_types = {
        str(item["name"]): str(item.get("type", {}).get("name") or "")
        for item in fact.get("parameter_facts", [])
        if item.get("name")
    }
    body = node.child_by_field_name("body") or node
    for current in _walk(body):
        if current.type == "identifier":
            identifier_references.append(
                {"name": _text(current, source), "line": _line(current)}
            )
        if current.type in _CONTROL_NODES:
            controls.append(
                {
                    "kind": _CONTROL_NODES[current.type],
                    "location": {"line": _line(current)},
                }
            )
        if current.type == "declaration":
            type_expression = _type_expression(current, source)
            type_fact = _type_fact(current.child_by_field_name("type"), source)
            type_name = str(type_fact.get("name") or "")
            if type_name and type_name not in _PRIMITIVE_TYPES:
                symbols.append(
                    {"kind": "type", "spelling": type_name, "line": _line(current)}
                )
            for declarator in _declarators(current):
                if _function_declarator(declarator) is not None:
                    continue
                name, _ = _name_from_declarator(declarator, source)
                if name and type_name:
                    variable_types[name] = type_name
                    local_variables.append(
                        {
                            "name": name,
                            "type_expression": type_expression,
                            "type": type_fact,
                        }
                    )
        if current.type != "call_expression":
            continue
        callee_node = current.child_by_field_name("function")
        arguments_node = current.child_by_field_name("arguments")
        if callee_node is None:
            continue
        raw_callee = _compact(_text(callee_node, source))
        callee = re.sub(r"\s*(?:->|\.)\s*", ".", raw_callee)
        callee_fact = _callee_fact(callee_node, source)
        target_name = str(callee_fact["target_name"])
        arguments = (
            [_compact(_text(child, source)) for child in arguments_node.named_children]
            if arguments_node is not None
            else []
        )
        argument_details = (
            [
                {
                    "expression": _compact(_text(child, source)),
                    "syntax_kind": child.type,
                    "literal_values": _string_literals(child, source),
                    "name_path": _cpp_name_path(child, source),
                }
                for child in arguments_node.named_children
            ]
            if arguments_node is not None
            else []
        )
        line = _line(current)
        calls.append({"callee": callee, "location": {"line": line}})
        call_details.append(
            {
                "callee": callee,
                "raw_callee": raw_callee,
                "callee_path": callee_fact["path"],
                "receiver": callee_fact["receiver"],
                "receiver_kind": callee_fact["receiver_kind"],
                "expression": _compact(_text(current, source)),
                "arguments": arguments,
                "argument_details": argument_details,
                "template_arguments": callee_fact["template_arguments"],
                "function_addresses": _function_addresses(arguments_node, source),
                "target_name": target_name,
                "target_owner": None,
                "variable_types": dict(variable_types),
                "line": line,
            }
        )
    return {
        "external_symbols": symbols,
        "calls": calls,
        "controls": controls,
        "call_details": call_details,
        "local_variables": local_variables,
        "identifier_references": identifier_references,
    }


def _parse_file(path: Path, parser: Parser) -> dict[str, Any]:
    source = path.read_bytes()
    file_key = _normal_key(path)
    tree = parser.parse(source)
    macros = _macros(tree.root_node, source, file_key)
    macros_by_start = {int(item["start_offset"]): item for item in macros}
    types: list[dict[str, Any]] = []
    functions: list[dict[str, Any]] = []
    variables: list[dict[str, Any]] = []
    references: dict[str, dict[str, Any]] = {}

    def visit(node: Node, namespaces: tuple[str, ...], owners: tuple[str, ...]) -> None:
        if node.type == "namespace_definition":
            name_node = node.child_by_field_name("name")
            name = _compact(_text(name_node, source)) if name_node is not None else ""
            body = node.child_by_field_name("body")
            if body is not None:
                visit(body, (*namespaces, name) if name else namespaces, owners)
            return
        if node.type in _TYPE_NODES:
            name_node = node.child_by_field_name("name")
            name = _compact(_text(name_node, source)) if name_node is not None else ""
            if not name:
                return
            body = node.child_by_field_name("body")
            kind = _TYPE_NODES[node.type]
            qualified = "::".join((*namespaces, *owners, name))
            fields = []
            methods = []
            if body is not None and kind != "enum":
                for child in body.named_children:
                    if child.type != "field_declaration":
                        continue
                    function_declarator = _function_declarator(child)
                    if function_declarator is not None:
                        function = _function_fact(
                            child,
                            function_declarator,
                            source,
                            file_key,
                            namespaces,
                            (*owners, name),
                            "declaration",
                        )
                        if function is not None:
                            function["macros"] = _leading_macro_expressions(
                                child, macros_by_start
                            )
                            functions.append(function)
                            methods.append(
                                {
                                    "name": function["name"],
                                    "signature": function["signature"],
                                    "role": "declaration",
                                    "macros": function["macros"],
                                    "line": _line(child),
                                    "end_line": _end_line(child),
                                }
                            )
                        continue
                    type_expression = _type_expression(child, source)
                    type_fact = _type_fact(child.child_by_field_name("type"), source)
                    for declarator in _declarators(child):
                        field_name, _ = _name_from_declarator(declarator, source)
                        if field_name:
                            fields.append(
                                {
                                    "name": field_name,
                                    "type_expression": type_expression,
                                    "type": type_fact,
                                    "macros": _leading_macro_expressions(
                                        child, macros_by_start
                                    ),
                                    "line": _line(child),
                                    "end_line": _end_line(child),
                                    "start_offset": int(child.start_byte),
                                    "end_offset": int(child.end_byte),
                                }
                            )
            types.append(
                {
                    "usr": f"{kind}|{qualified}",
                    "kind": kind,
                    "name": name,
                    "namespace": "::".join(namespaces) or None,
                    "owner": "::".join(owners) or None,
                    "qualified_name": qualified,
                    "role": "definition" if body is not None else "declaration",
                    "base_types": _base_types(node, source),
                    "base_type_facts": _base_type_facts(node, source),
                    "fields": fields,
                    "methods": methods,
                    "scoped": kind == "enum" and _is_scoped_enum(node, source),
                    "macros": _leading_macro_expressions(node, macros_by_start),
                    "file": file_key,
                    "line": _line(node),
                    "end_line": _end_line(node),
                    "start_offset": int(node.start_byte),
                    "end_offset": int(node.end_byte),
                }
            )
            if body is not None:
                for child in body.named_children:
                    if child.type != "field_declaration":
                        visit(child, namespaces, (*owners, name))
                        continue
                    nested_types = [
                        item
                        for item in child.named_children
                        if item.type in _TYPE_NODES
                    ]
                    if nested_types and not _declarators(child):
                        for nested in nested_types:
                            visit(nested, namespaces, (*owners, name))
            return
        if node.type == "function_definition":
            declarator = _function_declarator(node)
            if declarator is None:
                return
            function = _function_fact(
                node, declarator, source, file_key, namespaces, owners, "definition"
            )
            if function is not None:
                function["macros"] = _leading_macro_expressions(node, macros_by_start)
                functions.append(function)
                references[function["usr"]] = _function_references(
                    node, function, source
                )
            return
        if node.type in {"declaration", "field_declaration"}:
            direct_types = [
                child for child in node.named_children if child.type in _TYPE_NODES
            ]
            if direct_types:
                for child in direct_types:
                    visit(child, namespaces, owners)
                return
            declarator = _function_declarator(node)
            if declarator is not None:
                function = _function_fact(
                    node,
                    declarator,
                    source,
                    file_key,
                    namespaces,
                    owners,
                    "declaration",
                )
                if function is not None:
                    function["macros"] = _leading_macro_expressions(
                        node, macros_by_start
                    )
                    functions.append(function)
                return
            if not owners:
                type_expression = _type_expression(node, source)
                type_fact = _type_fact(node.child_by_field_name("type"), source)
                storage_classes = _storage_classes(node, source)
                for item in _declarators(node):
                    name, _ = _name_from_declarator(item, source)
                    if not name:
                        continue
                    qualified = "::".join((*namespaces, name))
                    variables.append(
                        {
                            "usr": f"variable|{qualified}",
                            "name": name,
                            "qualified_name": qualified,
                            "type_expression": type_expression,
                            "type": type_fact,
                            "role": "declaration"
                            if "extern" in storage_classes
                            else "definition",
                            "linkage": "internal"
                            if "static" in storage_classes
                            else "external",
                            "storage_classes": storage_classes,
                            "macros": _leading_macro_expressions(node, macros_by_start),
                            "file": file_key,
                            "line": _line(node),
                            "end_line": _end_line(node),
                            "start_offset": int(node.start_byte),
                            "end_offset": int(node.end_byte),
                        }
                    )
            return
        if node.type in _CONTAINER_NODES:
            for child in node.named_children:
                visit(child, namespaces, owners)

    visit(tree.root_node, (), ())
    diagnostics = []
    for node in _walk(tree.root_node):
        if node.type == "ERROR" or node.is_missing:
            diagnostics.append(
                {
                    "severity": 2,
                    "message": f"Tree-sitter reported {'missing syntax' if node.is_missing else 'an incomplete syntax region'}",
                    "file": file_key,
                    "line": _line(node),
                }
            )
    return {
        "file": file_key,
        "types": types,
        "functions": functions,
        "variables": variables,
        "references": references,
        "includes": _includes(tree.root_node, source, file_key),
        "macros": macros,
        "diagnostics": diagnostics,
    }


def _deduplicate(
    items: list[dict[str, Any]], keys: tuple[str, ...]
) -> list[dict[str, Any]]:
    unique = {tuple(item.get(key) for key in keys): item for item in items}
    return list(unique.values())


def _finalize_references(model: dict[str, Any]) -> None:
    methods = {
        (str(item.get("owner") or "").rsplit("::", 1)[-1], str(item["name"])): item
        for item in model["functions"]
        if item.get("owner")
    }
    free_functions = {
        (str(item.get("namespace") or ""), str(item["name"])): item
        for item in model["functions"]
        if not item.get("owner")
    }
    globals_by_name = {str(item["name"]): item for item in model["variables"]}
    functions_by_usr = {
        str(item["usr"]): item
        for item in model["functions"]
        if item["role"] == "definition"
    }
    field_types_by_owner: dict[str, dict[str, str]] = {}
    for item in model["types"]:
        if item["role"] != "definition":
            continue
        field_types_by_owner[str(item["qualified_name"])] = {
            str(field["name"]): str(field.get("type", {}).get("name") or "")
            for field in item.get("fields", [])
            if field.get("name")
        }
    for usr, references in model["references"].items():
        function = functions_by_usr.get(usr, {})
        function_owner = "::".join(
            part
            for part in (
                str(function.get("namespace") or ""),
                str(function.get("owner") or ""),
            )
            if part
        )
        field_types = field_types_by_owner.get(function_owner, {})
        symbols = list(references.get("external_symbols", []))
        for call in references.get("call_details", []):
            callee = str(call["callee"])
            target_name = str(call.get("target_name") or "")
            segments = [str(part) for part in call.get("callee_path", [])]
            receiver = str(call.get("receiver") or "")
            root = segments[0] if len(segments) > 1 else ""
            variable_types = call.get("variable_types", {})
            owner_type = (
                (
                    variable_types.get(root)
                    if root in variable_types
                    else field_types.get(root)
                )
                if len(segments) == 2
                else None
            )
            owner_key = str(function.get("owner") or "").rsplit("::", 1)[-1]
            if owner_type:
                resolved_owner = str(owner_type).rsplit("::", 1)[-1]
            elif call.get("receiver_kind") == "scope" and len(segments) >= 2:
                resolved_owner = segments[-2]
            elif (
                call.get("receiver_kind") == "member"
                and len(segments) >= 3
                and is_ue_same_type_static_accessor(segments[-2])
                and receiver.endswith(f"::{segments[-2]}()")
            ):
                resolved_owner = segments[-3]
            elif len(segments) == 1 and methods.get((owner_key, target_name)):
                resolved_owner = owner_key
            else:
                resolved_owner = ""
            free = free_functions.get(
                (str(function.get("namespace") or ""), target_name)
            )
            if len(segments) == 1 and is_ue_function_like_macro(target_name):
                if not is_ignored_external_macro(target_name):
                    symbols.append(
                        {
                            "kind": "macro",
                            "spelling": f"{target_name}()",
                            "line": int(call["line"]),
                        }
                    )
            elif resolved_owner:
                call["target_owner"] = resolved_owner
                is_static_accessor = (
                    call.get("receiver_kind") == "scope"
                    and is_ue_same_type_static_accessor(target_name)
                )
                if not is_static_accessor and not is_ignored_external_member_call(
                    resolved_owner, target_name
                ):
                    symbols.append(
                        {
                            "kind": "member_call",
                            "spelling": f"{resolved_owner}->{target_name}()",
                            "owner_type": resolved_owner,
                            "line": int(call["line"]),
                        }
                    )
            elif free is not None:
                symbols.append(
                    {
                        "kind": "free_function",
                        "spelling": free["qualified_name"],
                        "line": int(call["line"]),
                    }
                )
            elif target_name:
                symbols.append(
                    {
                        "kind": "unknown",
                        "spelling": f"{callee}()",
                        "line": int(call["line"]),
                    }
                )
            for address in call.get("function_addresses", []):
                symbol = {
                    "kind": "callback_target"
                    if ue_delegate_operation(target_name) == "subscribe"
                    else "function_address",
                    "spelling": address["qualified_name"],
                    "line": int(call["line"]),
                }
                if address.get("owner_type"):
                    symbol["owner_type"] = address["owner_type"]
                symbols.append(symbol)
        local_names = {
            str(item["name"])
            for item in [
                *function.get("parameter_facts", []),
                *references.get("local_variables", []),
            ]
            if item.get("name")
        }
        for name, item in globals_by_name.items():
            if name in local_names:
                continue
            reference = next(
                (
                    candidate
                    for candidate in references.get("identifier_references", [])
                    if candidate["name"] == name
                ),
                None,
            )
            if reference is None:
                continue
            symbols.append(
                {
                    "kind": "global_variable",
                    "spelling": item["qualified_name"],
                    "line": int(reference["line"]),
                }
            )
        references["external_symbols"] = sorted(
            _deduplicate(symbols, ("kind", "spelling", "owner_type", "line")),
            key=lambda item: (
                int(item["line"]),
                str(item["kind"]),
                str(item["spelling"]),
            ),
        )
        for call in references.get("call_details", []):
            call.pop("raw_callee", None)
            call.pop("variable_types", None)


def load_cpp_unit(
    anchor: Path,
    unit_files: list[Path],
    project_root: Path,
) -> dict[str, Any]:
    anchor = anchor.resolve()
    project_root = project_root.resolve()
    if not anchor.is_file():
        raise CppFrontendError(f"C++ source file is not a file: {anchor}")
    parser = _parser()
    parsed = [_parse_file(path.resolve(), parser) for path in unit_files]
    model: dict[str, Any] = {
        "engine": ENGINE,
        "version": frontend_version(),
        "types": [item for result in parsed for item in result["types"]],
        "functions": [item for result in parsed for item in result["functions"]],
        "variables": [item for result in parsed for item in result["variables"]],
        "references": {
            key: value
            for result in parsed
            for key, value in result["references"].items()
        },
        "includes": [item for result in parsed for item in result["includes"]],
        "macros": [item for result in parsed for item in result["macros"]],
        "diagnostics": [item for result in parsed for item in result["diagnostics"]],
    }
    for key in ("types", "functions", "variables"):
        model[key].sort(
            key=lambda item: (
                str(item["file"]),
                int(item["line"]),
                str(item.get("qualified_name") or item.get("name") or ""),
                str(item.get("role") or ""),
            )
        )
    model["includes"].sort(
        key=lambda item: (item["source_file"], item["line"], item["spelling"])
    )
    model["macros"].sort(key=lambda item: (item["file"], item["line"], item["name"]))
    model["diagnostic_error_count"] = sum(
        int(item["severity"]) >= 3 for item in model["diagnostics"]
    )
    _finalize_references(model)
    return model


def syntax_projection(model: dict[str, Any], path: Path) -> dict[str, Any]:
    key = _normal_key(path)
    functions = [item for item in model["functions"] if item["file"] == key]
    return {
        "engine": model["engine"],
        "language": "cpp",
        "parse_error_count": sum(
            1 for item in model["diagnostics"] if item["file"] == key
        ),
        "includes": [
            {"text": item["spelling"], "location": {"line": item["line"]}}
            for item in model["includes"]
            if item["source_file"] == key
        ],
        "types": [
            {
                "kind": item["kind"],
                "name": item["name"],
                "namespace": item["namespace"],
                "owner": item["owner"],
                "qualified_name": item["qualified_name"],
                "base_types": item["base_types"],
                "type_references": [
                    {
                        "kind": "field",
                        "name": field["name"],
                        "type_expression": field["type_expression"],
                        "location": {"line": field["line"]},
                    }
                    for field in item["fields"]
                ],
                "location": {"line": item["line"]},
            }
            for item in model["types"]
            if item["file"] == key and item["role"] == "definition"
        ],
        "functions": [
            {
                "name": item["qualified_name"],
                "signature": item["signature"],
                "has_body": item["role"] == "definition",
                "location": {"line": item["line"]},
                "calls": model["references"].get(item["usr"], {}).get("calls", []),
                "controls": model["references"]
                .get(item["usr"], {})
                .get("controls", []),
            }
            for item in functions
        ],
    }
