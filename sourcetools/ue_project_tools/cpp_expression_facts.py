"""Small AST projections used by delegate analysis; no UE API rules live here."""
from typing import Any


BUILTIN_TYPE_NAMES = frozenset({
    "bool", "char", "char8_t", "char16_t", "char32_t", "double", "float", "int",
    "long", "short", "signed", "unsigned", "void", "wchar_t",
})


def text(node, source):
    return source[node.start_byte:node.end_byte].decode("utf-8") if node else ""


def expression_kind(node, source):
    """Keep language operations distinct from ordinary calls and member access."""
    if node.type == "field_expression" and text(node.child_by_field_name("operator"), source) in {".*", "->*"}:
        return "member_pointer_expression"
    if node.type == "call_expression":
        callee = node.child_by_field_name("function")
        if callee is not None and (
            callee.type in {"primitive_type", "sized_type_specifier"}
            # The grammar also uses identifiers for some reserved type keywords.
            or callee.type == "identifier" and text(callee, source) in BUILTIN_TYPE_NAMES
        ):
            return "cast_expression"
        if callee is not None and callee.type == "template_function":
            name = text(callee.child_by_field_name("name"), source)
            if name in {"const_cast", "static_cast", "reinterpret_cast", "dynamic_cast"}:
                return "cast_expression"
    return node.type


def scope_path(node, source):
    """Namespace fallback; the frontend supplies the innermost named definition."""
    parts = []
    current = node.parent
    while current:
        if current.type == "namespace_definition":
            name = text(current.child_by_field_name("name"), source)
            if name:
                parts.append(name)
        current = current.parent
    return "::".join(reversed(parts))


def expression(node, source):
    if node is None:
        return None
    result: dict[str, Any] = {
        "kind": expression_kind(node, source), "expression": text(node, source),
        "start_offset": node.start_byte, "end_offset": node.end_byte,
        "line": node.start_point.row + 1, "column": node.start_point.column + 1,
    }
    if node.type == "field_expression":
        result["receiver"] = expression(node.child_by_field_name("argument"), source)
        result["name"] = text(node.child_by_field_name("field"), source)
    elif node.type == "call_expression":
        result["function"] = expression(node.child_by_field_name("function"), source)
    elif node.type == "qualified_identifier":
        result["scope"] = expression(node.child_by_field_name("scope"), source)
        result["name"] = text(node.child_by_field_name("name"), source)
    elif node.type in {"pointer_expression", "parenthesized_expression"}:
        result["operand"] = expression(node.named_children[-1], source) if node.named_children else None
        if node.type == "pointer_expression":
            result["operator"] = text(node.child_by_field_name("operator"), source)
    elif node.type in {"template_type", "template_function", "template_method"}:
        result["name"] = text(node.child_by_field_name("name"), source)
    return result


def execution_scope(node, source):
    current = node.parent
    while current:
        if current.type == "function_definition":
            break
        if current.type == "lambda_expression":
            return {"kind": "lambda", "line": current.start_point.row + 1,
                    "column": current.start_point.column + 1}
        current = current.parent
    return {"kind": "function"}


def result_target(node, source):
    parent = node.parent
    while parent and parent.type == "parenthesized_expression":
        node, parent = parent, parent.parent
    if parent and parent.type in {"argument_list", "initializer_list"}:
        values = [child for child in parent.named_children if child.type != "comment"]
        if values != [node]:
            return None
        node, parent = parent, parent.parent
    if parent and parent.type == "init_declarator" and parent.child_by_field_name("value") == node:
        return text(parent.child_by_field_name("declarator"), source)
    if parent and parent.type == "field_initializer":
        return text(parent.named_children[0], source)
    if parent and parent.type == "assignment_expression" and parent.child_by_field_name("right") == node:
        return text(parent.child_by_field_name("left"), source)
    return None


def visible_bindings(call, function, source, walk, type_fact, declarators, name_from_declarator,
                     declaration_nodes=None):
    """Lexical declarations only. No propagation through assignments or control flow."""
    scopes = []
    current = call.parent
    while current:
        scopes.append(current)
        if current == function:
            break
        current = current.parent
    scope_ids = {(n.start_byte, n.end_byte) for n in scopes}
    bindings = {}
    for node in declaration_nodes if declaration_nodes is not None else walk(function):
        if node.start_byte >= call.start_byte:
            continue
        if node.type not in {"declaration", "parameter_declaration", "optional_parameter_declaration", "for_range_loop"}:
            continue
        owner = node if node.type == "for_range_loop" else node.parent
        while owner and owner.type not in {"compound_statement", "lambda_expression", "function_definition",
                                          "if_statement", "for_statement", "for_range_loop", "catch_clause"}:
            owner = owner.parent
        if owner is None or (owner.start_byte, owner.end_byte) not in scope_ids:
            continue
        fact = type_fact(node.child_by_field_name("type"), source)
        for declarator in declarators(node):
            name, _ = name_from_declarator(declarator, source)
            if name:
                bindings[name] = {"kind": "parameter" if "parameter" in node.type else "local",
                                  "type": fact, "line": node.start_point.row + 1}
    return bindings
