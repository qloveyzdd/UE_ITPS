"""Tree-sitter syntax frontend adapted from ast-outline and gdep.

Upstream provenance:
- ast-outline e17982960cdf0893236eeb9f7002f9098459d8bc (Apache-2.0)
- gdep 736979b30879d4c4442262aa951fdf6b53cd001c (Apache-2.0)

This file is a UE ITPS-specific rewrite. It retains byte offsets while masking
AST-breaking UE macros, then exposes a small language-neutral fact model.
"""

from __future__ import annotations

from functools import lru_cache
import re
from typing import Any, Iterable

from tree_sitter import Language, Node, Parser
import tree_sitter_c_sharp as tscsharp
import tree_sitter_cpp as tscpp


ENGINE = "tree-sitter/ast-outline+gdep"

_BODY_MACROS = (
    "GENERATED_UINTERFACE_BODY",
    "GENERATED_IINTERFACE_BODY",
    "GENERATED_USTRUCT_BODY",
    "GENERATED_UCLASS_BODY",
    "GENERATED_BODY_LEGACY",
    "GENERATED_BODY",
)
_DECORATOR_MACROS = (
    "UCLASS",
    "USTRUCT",
    "UENUM",
    "UINTERFACE",
    "UDELEGATE",
    "UPROPERTY",
    "UFUNCTION",
    "UE_DEPRECATED",
)
_MACRO_CALL_RE = re.compile(
    rb"\b(?:"
    + b"|".join(name.encode("ascii") for name in (*_BODY_MACROS, *_DECORATOR_MACROS))
    + rb")\s*\("
)
_TOKEN_MACRO_RE = re.compile(rb"\b(?:[A-Z][A-Z0-9_]*_API|FORCEINLINE)\b")


def _blank(out: bytearray, start: int, end: int) -> None:
    for index in range(start, end):
        if out[index] not in {0x0A, 0x0D}:
            out[index] = 0x20


def clean_unreal_cpp(source: bytes) -> bytes:
    """Mask UE syntax disruptors without changing byte positions or lines."""
    out = bytearray(source)
    for match in list(_TOKEN_MACRO_RE.finditer(source)):
        _blank(out, match.start(), match.end())
    position = 0
    while True:
        match = _MACRO_CALL_RE.search(source, position)
        if match is None:
            break
        depth = 1
        index = match.end()
        in_string: int | None = None
        escaped = False
        while index < len(source) and depth:
            byte = source[index]
            if in_string is not None:
                if escaped:
                    escaped = False
                elif byte == 0x5C:
                    escaped = True
                elif byte == in_string:
                    in_string = None
            elif byte in {0x22, 0x27}:
                in_string = byte
            elif byte == 0x28:
                depth += 1
            elif byte == 0x29:
                depth -= 1
            index += 1
        if depth == 0:
            _blank(out, match.start(), index)
        position = max(index, match.end())
    return bytes(out)


@lru_cache(maxsize=2)
def _parser(language_name: str) -> Parser:
    handle = tscpp.language() if language_name == "cpp" else tscsharp.language()
    return Parser(Language(handle))


def _walk(root: Node) -> Iterable[Node]:
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(node.children))


def _text(source: bytes, node: Node | None) -> str:
    if node is None:
        return ""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


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


def _declarator_name(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    if node.type in {
        "identifier",
        "field_identifier",
        "qualified_identifier",
        "operator_name",
        "destructor_name",
    }:
        return _text(source, node).strip()
    preferred = node.child_by_field_name("declarator") or node.child_by_field_name(
        "name"
    )
    if preferred is not None:
        found = _declarator_name(preferred, source)
        if found:
            return found
    for child in reversed(node.named_children):
        found = _declarator_name(child, source)
        if found:
            return found
    return ""


def _cpp_types(root: Node, source: bytes) -> list[dict[str, Any]]:
    kinds = {
        "class_specifier": "class",
        "struct_specifier": "struct",
        "union_specifier": "union",
        "enum_specifier": "enum",
    }
    results: list[dict[str, Any]] = []
    for node in _walk(root):
        if node.type not in kinds:
            continue
        name_node = node.child_by_field_name("name")
        name = _text(source, name_node).strip()
        if not name:
            continue
        namespace_scopes: list[str] = []
        owner_parts: list[str] = []
        parent = node.parent
        while parent is not None:
            if parent.type == "namespace_definition":
                namespace_name = _text(
                    source, parent.child_by_field_name("name")
                ).strip()
                if namespace_name:
                    namespace_scopes.append(namespace_name)
            elif parent.type in {
                "class_specifier",
                "struct_specifier",
                "union_specifier",
            }:
                owner_name = _text(source, parent.child_by_field_name("name")).strip()
                if owner_name:
                    owner_parts.append(owner_name)
            parent = parent.parent
        namespace_parts = [
            part for scope in reversed(namespace_scopes) for part in scope.split("::")
        ]
        owner_parts.reverse()
        namespace = "::".join(namespace_parts) or None
        owner = "::".join(owner_parts) or None
        qualified_name = "::".join([*namespace_parts, *owner_parts, name])
        bases: list[str] = []
        base_clause = node.child_by_field_name("base_class_clause")
        if base_clause is None:
            base_clause = next(
                (
                    child
                    for child in node.named_children
                    if child.type == "base_class_clause"
                ),
                None,
            )
        if base_clause is not None:
            for child in base_clause.named_children:
                value = re.sub(
                    r"\b(public|protected|private|virtual)\b", "", _text(source, child)
                ).strip()
                if value:
                    bases.append(value)
        references: list[dict[str, Any]] = []
        body = node.child_by_field_name("body")
        if body is not None:
            for member in body.named_children:
                if member.type != "field_declaration":
                    continue
                declarator = member.child_by_field_name("declarator")
                if declarator is None or any(
                    descendant.type == "function_declarator"
                    for descendant in _walk(declarator)
                ):
                    continue
                type_node = member.child_by_field_name("type")
                type_expression = _text(source, type_node).strip()
                member_name = _declarator_name(declarator, source)
                if type_expression and member_name:
                    references.append(
                        {
                            "kind": "field",
                            "name": member_name,
                            "type_expression": type_expression,
                            "location": _location(member),
                        }
                    )
        results.append(
            {
                "kind": kinds[node.type],
                "name": name,
                "namespace": namespace,
                "owner": owner,
                "qualified_name": qualified_name,
                "base_types": list(dict.fromkeys(bases)),
                "type_references": references,
                "location": _location(node),
            }
        )
    return results


def _cpp_functions(root: Node, source: bytes) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, int, bool]] = set()
    for node in _walk(root):
        if node.type not in {"function_definition", "declaration", "field_declaration"}:
            continue
        declarator = node.child_by_field_name("declarator")
        candidates = (
            [item for item in _walk(declarator)] if declarator is not None else []
        )
        function_declarator = next(
            (item for item in candidates if item.type == "function_declarator"), None
        )
        if function_declarator is None:
            continue
        name = _declarator_name(
            function_declarator.child_by_field_name("declarator"), source
        )
        if not name:
            continue
        has_body = node.type == "function_definition"
        key = (name, node.start_point.row + 1, has_body)
        if key in seen:
            continue
        seen.add(key)
        calls: list[dict[str, Any]] = []
        controls: list[dict[str, Any]] = []
        body = node.child_by_field_name("body")
        if body is not None:
            for descendant in _walk(body):
                if descendant.type == "call_expression":
                    callee = _text(
                        source, descendant.child_by_field_name("function")
                    ).strip()
                    if callee:
                        calls.append(
                            {"callee": callee, "location": _location(descendant)}
                        )
                elif descendant.type in {
                    "if_statement",
                    "switch_statement",
                    "for_statement",
                    "for_range_loop",
                    "while_statement",
                    "do_statement",
                    "try_statement",
                    "return_statement",
                    "throw_expression",
                }:
                    controls.append(
                        {"kind": descendant.type, "location": _location(descendant)}
                    )
        results.append(
            {
                "name": name,
                "signature": " ".join(_text(source, function_declarator).split()),
                "has_body": has_body,
                "location": _location(node),
                "calls": calls,
                "controls": controls,
            }
        )
    return results


def parse_cpp_syntax(text: str) -> dict[str, Any]:
    source = text.encode("utf-8")
    tree = _parser("cpp").parse(clean_unreal_cpp(source))
    includes = []
    for node in _walk(tree.root_node):
        if node.type == "preproc_include":
            includes.append(
                {"text": _text(source, node).strip(), "location": _location(node)}
            )
    return {
        "engine": ENGINE,
        "language": "cpp",
        "parse_error_count": _errors(tree.root_node),
        "includes": includes,
        "types": _cpp_types(tree.root_node, source),
        "functions": _cpp_functions(tree.root_node, source),
    }


def _csharp_types(root: Node, source: bytes) -> list[dict[str, Any]]:
    kinds = {
        "class_declaration": "class",
        "struct_declaration": "struct",
        "interface_declaration": "interface",
        "record_declaration": "record",
        "enum_declaration": "enum",
    }
    results = []
    for node in _walk(root):
        if node.type not in kinds:
            continue
        name = _text(source, node.child_by_field_name("name")).strip()
        if not name:
            continue
        bases = []
        base_list = node.child_by_field_name("bases")
        if base_list is None:
            base_list = next(
                (child for child in node.named_children if child.type == "base_list"),
                None,
            )
        if base_list is not None:
            bases = [
                _text(source, child).strip()
                for child in base_list.named_children
                if _text(source, child).strip()
            ]
        results.append(
            {
                "kind": kinds[node.type],
                "name": name,
                "base_types": bases,
                "location": _location(node),
            }
        )
    return results


def _csharp_functions(root: Node, source: bytes) -> list[dict[str, Any]]:
    results = []
    for node in _walk(root):
        if node.type not in {
            "method_declaration",
            "constructor_declaration",
            "local_function_statement",
        }:
            continue
        name = _text(source, node.child_by_field_name("name")).strip()
        if not name:
            continue
        body = node.child_by_field_name("body")
        calls = []
        controls = []
        if body is not None:
            for descendant in _walk(body):
                if descendant.type == "invocation_expression":
                    callee = _text(
                        source, descendant.child_by_field_name("function")
                    ).strip()
                    if callee:
                        calls.append(
                            {"callee": callee, "location": _location(descendant)}
                        )
                elif descendant.type in {
                    "if_statement",
                    "switch_statement",
                    "for_statement",
                    "foreach_statement",
                    "while_statement",
                    "do_statement",
                    "try_statement",
                    "return_statement",
                    "throw_statement",
                }:
                    controls.append(
                        {"kind": descendant.type, "location": _location(descendant)}
                    )
        results.append(
            {
                "name": name,
                "signature": " ".join(_text(source, node).split("{", 1)[0].split()),
                "has_body": body is not None,
                "location": _location(node),
                "calls": calls,
                "controls": controls,
            }
        )
    return results


def parse_csharp_syntax(text: str) -> dict[str, Any]:
    source = text.encode("utf-8")
    tree = _parser("csharp").parse(source)
    return {
        "engine": ENGINE,
        "language": "csharp",
        "parse_error_count": _errors(tree.root_node),
        "types": _csharp_types(tree.root_node, source),
        "functions": _csharp_functions(tree.root_node, source),
    }
