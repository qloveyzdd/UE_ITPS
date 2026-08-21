from __future__ import annotations

from importlib.metadata import version as package_version
from pathlib import Path
import re
from typing import Any, Iterator

from tree_sitter import Language, Node, Parser
import tree_sitter_ue_cpp

from .common import normalized


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
_INCLUDE_RE = re.compile(
    rb"^[ \t]*#[ \t]*include[ \t]+(?P<value><[^>]+>|\"[^\"]+\"|[^\r\n]+)",
    re.MULTILINE,
)
_TOKEN_RE = re.compile(
    r'::|->|\.\.\.|"(?:\\.|[^"\\])*"|[A-Za-z_]\w*|\d+|[^\s]'
)
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


def _macros(
    root: Node, source: bytes, file_key: str
) -> list[dict[str, Any]]:
    results = []
    for node in _walk(root):
        if node.type != "ue_macro_invocation":
            continue
        head = node.child_by_field_name("head")
        arguments = node.child_by_field_name("arguments")
        if head is None or arguments is None:
            continue
        start = int(node.start_byte)
        end = int(arguments.end_byte)
        name = _text(head, source).split("(", 1)[0].strip()
        expression = source[start:end].decode("utf-8", errors="replace")
        results.append(
            {
                "name": name,
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


def _includes(source: bytes, file_key: str) -> list[dict[str, Any]]:
    results = []
    for match in _INCLUDE_RE.finditer(source):
        raw = match.group("value").strip()
        if raw.startswith(b"<") and raw.endswith(b">"):
            syntax = "angle"
            spelling = raw[1:-1]
        elif raw.startswith(b'"') and raw.endswith(b'"'):
            syntax = "quote"
            spelling = raw[1:-1]
        else:
            syntax = "macro"
            spelling = raw
        results.append(
            {
                "source_file": file_key,
                "included_file": None,
                "spelling": spelling.decode("utf-8", errors="replace").replace("\\", "/"),
                "syntax": syntax,
                "line": source.count(b"\n", 0, match.start()) + 1,
            }
        )
    return results


def _name_from_declarator(node: Node | None, source: bytes) -> tuple[str, str]:
    if node is None:
        return "", ""
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
    raw = _compact(_text(current, source))
    raw = re.sub(r"\s*::\s*", "::", raw)
    raw = re.sub(r"<.*>$", "", raw)
    name = raw.rsplit("::", 1)[-1]
    return name, raw


def _parameter_facts(function_declarator: Node, source: bytes) -> list[dict[str, str]]:
    parameters = function_declarator.child_by_field_name("parameters")
    if parameters is None:
        return []
    results = []
    for parameter in parameters.named_children:
        if parameter.type not in {"parameter_declaration", "optional_parameter_declaration"}:
            continue
        declarator = parameter.child_by_field_name("declarator")
        name, _ = _name_from_declarator(declarator, source)
        type_node = parameter.child_by_field_name("type")
        type_expression = _compact(_text(type_node, source)) if type_node else ""
        if declarator is not None:
            declarator_text = _compact(_text(declarator, source))
            if name:
                declarator_text = re.sub(rf"\b{re.escape(name)}\b", "", declarator_text)
            type_expression = _compact(f"{type_expression} {declarator_text}")
        results.append({"name": name, "type_expression": type_expression})
    return results


def _base_types(node: Node, source: bytes) -> list[str]:
    clause = next((child for child in node.named_children if child.type == "base_class_clause"), None)
    if clause is None:
        return []
    results = []
    for child in clause.named_children:
        if child.type in {"access_specifier", "virtual"}:
            continue
        value = _compact(_text(child, source))
        value = re.sub(r"^(?:public|protected|private|virtual)\s+", "", value)
        if value and value not in results:
            results.append(value)
    return results


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


def _function_fact(
    node: Node,
    function_declarator: Node,
    source: bytes,
    file_key: str,
    namespaces: tuple[str, ...],
    owners: tuple[str, ...],
    role: str,
) -> dict[str, Any] | None:
    name, raw_name = _name_from_declarator(function_declarator, source)
    if not name:
        return None
    explicit_prefix = raw_name.rsplit("::", 1)[0] if "::" in raw_name else ""
    owner_parts = list(owners)
    if explicit_prefix:
        prefix_parts = [part for part in explicit_prefix.split("::") if part]
        if namespaces and prefix_parts[: len(namespaces)] == list(namespaces):
            prefix_parts = prefix_parts[len(namespaces) :]
        owner_parts = prefix_parts
    owner = "::".join(owner_parts) or None
    qualified_parts = [*namespaces, *owner_parts, name]
    qualified_name = "::".join(qualified_parts)
    parameters = _parameter_facts(function_declarator, source)
    parameter_text = ", ".join(
        _compact(f"{item['type_expression']} {item['name']}") for item in parameters
    )
    declaration_text = _compact(_text(node, source).split("{", 1)[0]).rstrip(";")
    qualifiers = [
        value
        for value in ("const", "static", "virtual", "override", "final")
        if re.search(rf"\b{value}\b", declaration_text)
    ]
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
        "qualifiers": qualifiers,
        "role": role,
        "linkage": "internal" if "static" in qualifiers else "external",
        "file": file_key,
        "line": _line(node),
        "end_line": _end_line(node),
        "start_offset": int(node.start_byte),
        "end_offset": int(node.end_byte),
    }


def _variable_type(value: str) -> str:
    return re.sub(r"\s*[*&]+\s*$", "", value).split("::")[-1].strip()


def _function_references(
    node: Node,
    fact: dict[str, Any],
    source: bytes,
) -> dict[str, Any]:
    symbols: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    call_details: list[dict[str, Any]] = []
    variable_types = {
        str(item["name"]): _variable_type(str(item["type_expression"]))
        for item in fact.get("parameter_facts", [])
        if item.get("name")
    }
    for current in _walk(node):
        if current.type in _CONTROL_NODES:
            controls.append(
                {
                    "kind": _CONTROL_NODES[current.type],
                    "location": {"line": _line(current)},
                }
            )
        if current.type == "declaration":
            type_expression = _type_expression(current, source)
            type_name = _variable_type(type_expression)
            if type_name and type_name not in _PRIMITIVE_TYPES and re.search(r"[A-Z]", type_name):
                symbols.append({"kind": "type", "spelling": type_name, "line": _line(current)})
            for declarator in _declarators(current):
                if _function_declarator(declarator) is not None:
                    continue
                name, _ = _name_from_declarator(declarator, source)
                if name and type_name:
                    variable_types[name] = type_name
        if current.type != "call_expression":
            continue
        callee_node = current.child_by_field_name("function")
        arguments_node = current.child_by_field_name("arguments")
        if callee_node is None:
            continue
        raw_callee = _compact(_text(callee_node, source))
        callee = re.sub(r"\s*(?:->|\.)\s*", ".", raw_callee)
        target_name = re.sub(r"<.*>$", "", callee.rsplit(".", 1)[-1].rsplit("::", 1)[-1])
        arguments = (
            [_compact(_text(child, source)) for child in arguments_node.named_children]
            if arguments_node is not None
            else []
        )
        line = _line(current)
        calls.append({"callee": callee, "location": {"line": line}})
        call_details.append(
            {
                "callee": callee,
                "raw_callee": raw_callee,
                "expression": _compact(_text(current, source)),
                "arguments": arguments,
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
        "body_text": _text(node, source),
    }


def _parse_file(path: Path, parser: Parser) -> dict[str, Any]:
    source = path.read_bytes()
    file_key = _normal_key(path)
    tree = parser.parse(source)
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
                            functions.append(function)
                            methods.append(
                                {
                                    "name": function["name"],
                                    "signature": function["signature"],
                                    "role": "declaration",
                                    "line": _line(child),
                                    "end_line": _end_line(child),
                                }
                            )
                        continue
                    type_expression = _type_expression(child, source)
                    for declarator in _declarators(child):
                        field_name, _ = _name_from_declarator(declarator, source)
                        if field_name:
                            fields.append(
                                {
                                    "name": field_name,
                                    "type_expression": type_expression,
                                    "line": _line(child),
                                    "end_line": _end_line(child),
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
                    "fields": fields,
                    "methods": methods,
                    "scoped": kind == "enum" and bool(re.search(r"\benum\s+(?:class|struct)\b", _text(node, source))),
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
                        item for item in child.named_children if item.type in _TYPE_NODES
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
                functions.append(function)
                references[function["usr"]] = _function_references(node, function, source)
            return
        if node.type in {"declaration", "field_declaration"}:
            direct_types = [child for child in node.named_children if child.type in _TYPE_NODES]
            if direct_types:
                for child in direct_types:
                    visit(child, namespaces, owners)
                return
            declarator = _function_declarator(node)
            if declarator is not None:
                function = _function_fact(
                    node, declarator, source, file_key, namespaces, owners, "declaration"
                )
                if function is not None:
                    functions.append(function)
                return
            if not owners:
                declaration_text = _compact(_text(node, source))
                type_expression = _type_expression(node, source)
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
                            "role": "declaration" if re.search(r"\bextern\b", declaration_text) else "definition",
                            "linkage": "internal" if re.search(r"\bstatic\b", declaration_text) else "external",
                            "file": file_key,
                            "line": _line(node),
                            "end_line": _end_line(node),
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
        "includes": _includes(source, file_key),
        "macros": _macros(tree.root_node, source, file_key),
        "diagnostics": diagnostics,
    }


def _deduplicate(items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
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
    functions_by_usr = {str(item["usr"]): item for item in model["functions"]}
    for usr, references in model["references"].items():
        function = functions_by_usr.get(usr, {})
        symbols = list(references.get("external_symbols", []))
        for call in references.get("call_details", []):
            callee = str(call["callee"])
            target_name = str(call.get("target_name") or "")
            segments = [part for part in callee.split(".") if part]
            root = segments[0].split("::", 1)[0] if len(segments) > 1 else ""
            owner_type = call.get("variable_types", {}).get(root)
            if not owner_type and len(segments) > 1 and function.get("owner"):
                owner_type = str(function["owner"]).rsplit("::", 1)[-1]
            owner_key = str(function.get("owner") or "").rsplit("::", 1)[-1]
            method = methods.get((str(owner_type or owner_key), target_name))
            free = free_functions.get((str(function.get("namespace") or ""), target_name))
            if owner_type or method:
                resolved_owner = str(owner_type or method.get("owner") or owner_key).rsplit("::", 1)[-1]
                call["target_owner"] = resolved_owner
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
                        "spelling": f"{target_name}()",
                        "line": int(call["line"]),
                    }
                )
            for argument in call.get("arguments", []):
                for match in re.finditer(r"&(?P<owner>[A-Za-z_]\w*)::(?P<name>[A-Za-z_]\w*)", str(argument)):
                    symbols.append(
                        {
                            "kind": "callback_target" if re.match(r"^(?:Add|Bind|Create|Register|Subscribe|Listen)", target_name) else "function_address",
                            "spelling": f"{match.group('owner')}::{match.group('name')}",
                            "owner_type": match.group("owner"),
                            "line": int(call["line"]),
                        }
                    )
        body_text = str(references.pop("body_text", ""))
        for name, item in globals_by_name.items():
            if re.search(rf"\b{re.escape(name)}\b", body_text):
                symbols.append(
                    {
                        "kind": "global_variable",
                        "spelling": item["qualified_name"],
                        "line": int(function.get("line", 1)),
                    }
                )
        references["external_symbols"] = sorted(
            _deduplicate(symbols, ("kind", "spelling", "owner_type", "line")),
            key=lambda item: (int(item["line"]), str(item["kind"]), str(item["spelling"])),
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
    model["includes"].sort(key=lambda item: (item["source_file"], item["line"], item["spelling"]))
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
                "controls": model["references"].get(item["usr"], {}).get("controls", []),
            }
            for item in functions
        ],
    }
