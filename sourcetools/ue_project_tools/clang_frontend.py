from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
from typing import Any, Iterator

from .common import normalized


ENGINE = "clang/libclang"
_CPP_SUFFIXES = {".cpp", ".cc", ".cxx"}
_TYPE_KINDS = {
    "CLASS_DECL": "class",
    "STRUCT_DECL": "struct",
    "CLASS_TEMPLATE": "class",
    "CLASS_TEMPLATE_PARTIAL_SPECIALIZATION": "class",
    "ENUM_DECL": "enum",
}
_FUNCTION_KINDS = {
    "FUNCTION_DECL",
    "CXX_METHOD",
    "CONSTRUCTOR",
    "DESTRUCTOR",
    "CONVERSION_FUNCTION",
    "FUNCTION_TEMPLATE",
}
_CONTROL_KINDS = {
    "IF_STMT": "if_statement",
    "SWITCH_STMT": "switch_statement",
    "FOR_STMT": "for_statement",
    "CXX_FOR_RANGE_STMT": "for_range_loop",
    "WHILE_STMT": "while_statement",
    "DO_STMT": "do_statement",
    "CXX_TRY_STMT": "try_statement",
    "CXX_THROW_EXPR": "throw_expression",
    "RETURN_STMT": "return_statement",
}


class ClangFrontendError(ValueError):
    pass


def _normal_key(value: str | Path) -> str:
    return normalized(Path(value).resolve()).casefold()


def _location_key(value: str | Path) -> str:
    return str(value).replace("\\", "/").casefold()


def resolve_compilation_database(
    project_root: Path,
    explicit: Path | None = None,
) -> Path:
    configured = explicit
    if configured is None and os.environ.get("UE_ITPS_COMPILE_DATABASE"):
        configured = Path(os.environ["UE_ITPS_COMPILE_DATABASE"])
    candidates = []
    if configured is not None:
        candidates.append(configured.resolve())
    else:
        candidates.extend(
            (
                project_root / "compile_commands.json",
                project_root / ".clang" / "compile_commands.json",
                project_root / "Intermediate" / "Build" / "compile_commands.json",
            )
        )
    for candidate in candidates:
        database_file = (
            candidate / "compile_commands.json" if candidate.is_dir() else candidate
        )
        if database_file.is_file():
            return database_file.resolve()
    rendered = ", ".join(normalized(path) for path in candidates)
    raise ClangFrontendError(
        "Clang compilation database was not found"
        + (f": {rendered}" if rendered else "")
    )


def compilation_database_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_cindex() -> Any:
    try:
        from clang import cindex
    except ImportError as exc:
        raise ClangFrontendError(
            "libclang Python package is required; install requirements.txt"
        ) from exc
    library = os.environ.get("UE_ITPS_LIBCLANG")
    if library and not cindex.Config.loaded:
        resolved = Path(library).resolve()
        if not resolved.is_file():
            raise ClangFrontendError(f"UE_ITPS_LIBCLANG is not a file: {resolved}")
        cindex.Config.set_library_file(str(resolved))
    try:
        cindex.Index.create()
    except Exception as exc:
        raise ClangFrontendError(f"Unable to load libclang: {exc}") from exc
    return cindex


def clang_version() -> str:
    cindex = _load_cindex()
    try:
        function = cindex.conf.lib.clang_getClangVersion
        function.restype = cindex._CXString
        function.errcheck = cindex._CXString.from_result
        value = function()
        return (
            value.decode("utf-8", errors="replace")
            if isinstance(value, bytes)
            else str(value)
        )
    except Exception:
        return "unknown"


@contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    original = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(original)


def _command_path(command: Any) -> Path:
    return Path(str(command.filename)).resolve()


def _commands(database: Any) -> list[Any]:
    try:
        return list(database.getAllCompileCommands())
    except Exception:
        return []


def _module_root(path: Path) -> Path | None:
    resolved = path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if any(parent.glob("*.Build.cs")):
            return parent
    return None


def _select_command(
    database: Any,
    anchor: Path,
) -> tuple[Any, str]:
    direct = database.getCompileCommands(str(anchor.resolve()))
    if direct is not None:
        selected = next(iter(direct), None)
        if selected is not None:
            return selected, "direct"
    module_root = _module_root(anchor)
    if module_root is None:
        raise ClangFrontendError(
            f"No compile command exists for source unit: {anchor.resolve()}"
        )
    candidates = [
        command
        for command in _commands(database)
        if _command_path(command).is_relative_to(module_root)
        and _command_path(command).suffix.casefold() in _CPP_SUFFIXES
    ]
    candidates.sort(key=lambda item: _normal_key(_command_path(item)))
    if not candidates:
        raise ClangFrontendError(
            f"No module compile command exists for source unit: {anchor.resolve()}"
        )
    return candidates[0], "module-profile"


def _compile_arguments(
    command: Any,
    anchor: Path,
    selection: str,
) -> list[str]:
    arguments = list(command.arguments)[1:]
    command_source = _normal_key(_command_path(command))
    anchor_key = _normal_key(anchor)
    if selection != "direct" and any(arg.startswith("@") for arg in arguments):
        raise ClangFrontendError(
            "A response-file compile command cannot be borrowed for another source file"
        )
    filtered: list[str] = []
    skip_next = False
    for argument in arguments:
        if skip_next:
            skip_next = False
            continue
        key = argument.strip('"')
        if key == "--":
            continue
        if key in {"-o", "/Fo"}:
            skip_next = True
            continue
        if key.startswith(("/Fo", "-o")):
            continue
        try:
            resolved_key = _normal_key(Path(key))
        except (OSError, ValueError):
            resolved_key = ""
        if resolved_key in {command_source, anchor_key}:
            continue
        filtered.append(argument)
    filtered.extend(
        [
            "-Wno-error",
            "-Wno-unused-command-line-argument",
            "-Wno-unknown-argument",
            "-ferror-limit=0",
        ]
    )
    return filtered


def _cursor_location(cursor: Any) -> dict[str, Any] | None:
    location = cursor.location
    if location is None or location.file is None or location.line < 1:
        return None
    return {
        "file": _location_key(location.file.name),
        "line": int(location.line),
        "column": int(location.column),
        "offset": int(location.offset),
    }


def _extent_location(cursor: Any) -> dict[str, int]:
    start = cursor.extent.start
    end = cursor.extent.end
    return {
        "line": int(start.line),
        "end_line": max(int(start.line), int(end.line)),
        "start_offset": int(start.offset),
        "end_offset": int(end.offset),
    }


def _parent_name(cursor: Any) -> str:
    return cursor.displayname or cursor.spelling


def _qualified_name(cursor: Any) -> str:
    names = [cursor.spelling] if cursor.spelling else []
    parent = cursor.semantic_parent
    while parent and parent.kind.name != "TRANSLATION_UNIT":
        name = _parent_name(parent)
        if name:
            names.append(name)
        parent = parent.semantic_parent
    return "::".join(reversed(names))


def _namespace(cursor: Any) -> str | None:
    values: list[str] = []
    parent = cursor.semantic_parent
    while parent and parent.kind.name != "TRANSLATION_UNIT":
        if parent.kind.name == "NAMESPACE" and parent.spelling:
            values.append(parent.spelling)
        parent = parent.semantic_parent
    return "::".join(reversed(values)) or None


def _owner(cursor: Any) -> str | None:
    values: list[str] = []
    parent = cursor.semantic_parent
    while parent and parent.kind.name != "TRANSLATION_UNIT":
        if parent.kind.name in _TYPE_KINDS and parent.spelling:
            values.append(parent.spelling)
        parent = parent.semantic_parent
    return "::".join(reversed(values)) or None


def _source_slice(path: Path, start: int, end: int) -> str:
    data = path.read_bytes()
    return data[start:end].decode("utf-8", errors="replace")


def _call_spelling(cursor: Any, path: Path) -> str:
    raw = _source_slice(
        path,
        int(cursor.extent.start.offset),
        int(cursor.extent.end.offset),
    )
    prefix = raw.split("(", 1)[0].strip()
    return re.sub(r"\s*(?:->|\.)\s*", ".", prefix)


def _type_spelling(cursor: Any) -> str:
    spelling = cursor.type.spelling or cursor.spelling
    return re.sub(r"^(?:class|struct|enum)\s+", "", spelling).strip()


def _function_fact(cursor: Any, location: dict[str, Any]) -> dict[str, Any]:
    arguments = list(cursor.get_arguments() or [])
    parameters = ", ".join(
        " ".join(part for part in (item.type.spelling, item.spelling) if part)
        for item in arguments
    )
    qualified = _qualified_name(cursor)
    owner = _owner(cursor)
    namespace = _namespace(cursor)
    extent = _extent_location(cursor)
    return {
        "usr": cursor.get_usr() or f"{qualified}|{cursor.type.spelling}",
        "kind": "method" if owner else "free_function",
        "namespace": namespace,
        "owner": owner,
        "name": cursor.spelling,
        "qualified_name": qualified,
        "parameters": parameters,
        "parameter_facts": [
            {"name": item.spelling, "type_expression": item.type.spelling}
            for item in arguments
        ],
        "signature": cursor.type.spelling or cursor.displayname,
        "qualifiers": [
            value
            for value, present in (
                ("const", getattr(cursor, "is_const_method", lambda: False)()),
                ("static", getattr(cursor, "is_static_method", lambda: False)()),
                ("virtual", getattr(cursor, "is_virtual_method", lambda: False)()),
                (
                    "pure_virtual",
                    getattr(cursor, "is_pure_virtual_method", lambda: False)(),
                ),
            )
            if present
        ],
        "role": "definition" if cursor.is_definition() else "declaration",
        "linkage": (
            "internal"
            if cursor.linkage.name in {"INTERNAL", "NO_LINKAGE"}
            else "external"
        ),
        "file": location["file"],
        **extent,
    }


def _type_fact(cursor: Any, location: dict[str, Any]) -> dict[str, Any]:
    children = list(cursor.get_children())
    bases = [
        _type_spelling(child)
        for child in children
        if child.kind.name == "CXX_BASE_SPECIFIER"
    ]
    fields = [
        {
            "name": child.spelling,
            "type_expression": child.type.spelling,
            **_extent_location(child),
        }
        for child in children
        if child.kind.name == "FIELD_DECL"
    ]
    methods = [
        {
            "name": child.spelling,
            "signature": child.type.spelling or child.displayname,
            "role": "definition" if child.is_definition() else "declaration",
            **_extent_location(child),
        }
        for child in children
        if child.kind.name in _FUNCTION_KINDS and child.spelling
    ]
    return {
        "usr": cursor.get_usr() or _qualified_name(cursor),
        "kind": _TYPE_KINDS[cursor.kind.name],
        "name": cursor.spelling,
        "namespace": _namespace(cursor),
        "owner": _owner(cursor),
        "qualified_name": _qualified_name(cursor),
        "role": "definition" if cursor.is_definition() else "declaration",
        "base_types": bases,
        "fields": fields,
        "methods": methods,
        "scoped": bool(
            cursor.kind.name == "ENUM_DECL"
            and getattr(cursor, "is_scoped_enum", lambda: False)()
        ),
        "file": location["file"],
        **_extent_location(cursor),
    }


def _reference_facts(
    function: Any,
    unit_keys: set[str],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    symbols: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    controls: list[dict[str, Any]] = []
    call_details: list[dict[str, Any]] = []
    stack: list[tuple[Any, str | None, bool]] = [
        (child, function.kind.name, False) for child in function.get_children()
    ]
    while stack:
        cursor, parent_kind, callback_context = stack.pop()
        location = _cursor_location(cursor)
        if location is None or location["file"] not in unit_keys:
            continue
        children = list(cursor.get_children())
        kind_name = cursor.kind.name
        callback_call = False
        if kind_name == "CALL_EXPR":
            target = cursor.referenced
            callback_call = bool(
                target
                and re.match(
                    r"^(?:Add|Bind|Create|Register|Subscribe|Listen)",
                    target.spelling,
                )
            )
        stack.extend(
            (child, kind_name, callback_context or callback_call)
            for child in reversed(children)
        )
        if kind_name in _CONTROL_KINDS:
            controls.append(
                {
                    "kind": _CONTROL_KINDS[kind_name],
                    "location": {"line": location["line"]},
                }
            )
        if kind_name == "TYPE_REF":
            target = cursor.referenced
            spelling = target.spelling if target is not None else cursor.spelling
            if spelling:
                symbols.append(
                    {
                        "kind": "type",
                        "spelling": spelling,
                        "line": location["line"],
                    }
                )
        if kind_name == "CALL_EXPR":
            target = cursor.referenced
            source_path = Path(cursor.location.file.name).resolve()
            callee = _call_spelling(cursor, source_path)
            calls.append({"callee": callee, "location": {"line": location["line"]}})
            call_details.append(
                {
                    "callee": callee,
                    "expression": _source_slice(
                        source_path,
                        int(cursor.extent.start.offset),
                        int(cursor.extent.end.offset),
                    ).strip(),
                    "arguments": [
                        _source_slice(
                            source_path,
                            int(argument.extent.start.offset),
                            int(argument.extent.end.offset),
                        ).strip()
                        for argument in (cursor.get_arguments() or [])
                    ],
                    "target_name": target.spelling if target is not None else None,
                    "target_owner": _owner(target) if target is not None else None,
                    "line": location["line"],
                }
            )
            if target is None or target.kind.name not in _FUNCTION_KINDS:
                if callee:
                    symbols.append(
                        {
                            "kind": "unknown",
                            "spelling": f"{callee}()",
                            "line": location["line"],
                        }
                    )
                continue
            owner = _owner(target)
            if owner:
                owner_type = owner.rsplit("::", 1)[-1]
                symbols.append(
                    {
                        "kind": "member_call",
                        "spelling": f"{owner_type}->{target.spelling}()",
                        "owner_type": owner_type,
                        "line": location["line"],
                    }
                )
            else:
                symbols.append(
                    {
                        "kind": "free_function",
                        "spelling": _qualified_name(target),
                        "line": location["line"],
                    }
                )
        if kind_name in {"DECL_REF_EXPR", "MEMBER_REF_EXPR"}:
            target = cursor.referenced
            if target is None:
                continue
            target_kind = target.kind.name
            if target_kind == "VAR_DECL" and target.semantic_parent.kind.name in {
                "TRANSLATION_UNIT",
                "NAMESPACE",
            }:
                symbols.append(
                    {
                        "kind": "global_variable",
                        "spelling": _qualified_name(target),
                        "line": location["line"],
                    }
                )
            elif target_kind in _FUNCTION_KINDS and parent_kind != "CALL_EXPR":
                owner = _owner(target)
                item = {
                    "kind": (
                        "callback_target" if callback_context else "function_address"
                    ),
                    "spelling": _qualified_name(target),
                    "line": location["line"],
                }
                if owner:
                    item["owner_type"] = owner.rsplit("::", 1)[-1]
                symbols.append(item)
    unique_symbols = {
        (
            item["kind"],
            item["spelling"],
            item.get("owner_type"),
            item["line"],
        ): item
        for item in symbols
    }
    unique_calls = {(item["callee"], item["location"]["line"]): item for item in calls}
    unique_controls = {
        (item["kind"], item["location"]["line"]): item for item in controls
    }
    unique_call_details = {
        (item["callee"], item["line"], item["expression"]): item
        for item in call_details
    }
    return (
        sorted(
            unique_symbols.values(),
            key=lambda item: (item["line"], item["kind"], item["spelling"]),
        ),
        sorted(
            unique_calls.values(),
            key=lambda item: (item["location"]["line"], item["callee"]),
        ),
        sorted(
            unique_controls.values(),
            key=lambda item: (item["location"]["line"], item["kind"]),
        ),
        sorted(
            unique_call_details.values(),
            key=lambda item: (item["line"], item["callee"], item["expression"]),
        ),
    )


def load_clang_unit(
    anchor: Path,
    unit_files: list[Path],
    project_root: Path,
    compilation_database: Path | None = None,
) -> dict[str, Any]:
    anchor = anchor.resolve()
    unit_files = [path.resolve() for path in unit_files]
    project_root = project_root.resolve()
    cindex = _load_cindex()
    database_file = resolve_compilation_database(
        project_root,
        compilation_database,
    )
    database = cindex.CompilationDatabase.fromDirectory(str(database_file.parent))
    selected_command, command_source = _select_command(database, anchor)
    arguments = _compile_arguments(selected_command, anchor, command_source)
    index = cindex.Index.create()
    options = (
        cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
        | cindex.TranslationUnit.PARSE_INCOMPLETE
        | getattr(cindex.TranslationUnit, "PARSE_KEEP_GOING", 0)
    )
    try:
        with _working_directory(Path(str(selected_command.directory))):
            translation_unit = index.parse(
                str(anchor.resolve()),
                args=arguments,
                options=options,
            )
    except Exception as exc:
        raise ClangFrontendError(
            f"Clang failed to parse {anchor.resolve()}: {exc}"
        ) from exc

    unit_by_key = {_normal_key(path): path.resolve() for path in unit_files}
    unit_keys = set(unit_by_key)
    types: list[dict[str, Any]] = []
    functions: list[dict[str, Any]] = []
    variables: list[dict[str, Any]] = []
    references: dict[str, dict[str, Any]] = {}
    seen_types: set[tuple[Any, ...]] = set()
    seen_functions: set[tuple[Any, ...]] = set()
    stack = [translation_unit.cursor]
    while stack:
        cursor = stack.pop()
        if cursor.kind.name == "TRANSLATION_UNIT":
            stack.extend(reversed(list(cursor.get_children())))
            continue
        location = _cursor_location(cursor)
        if location is None or location["file"] not in unit_keys:
            continue
        children = list(cursor.get_children())
        stack.extend(reversed(children))
        if cursor.kind.name in _TYPE_KINDS and cursor.spelling:
            item = _type_fact(cursor, location)
            key = (item["usr"], item["role"], item["file"], item["line"])
            if key not in seen_types:
                seen_types.add(key)
                types.append(item)
        if cursor.kind.name in _FUNCTION_KINDS and cursor.spelling:
            item = _function_fact(cursor, location)
            key = (item["usr"], item["role"], item["file"], item["line"])
            if key in seen_functions:
                continue
            seen_functions.add(key)
            functions.append(item)
            if item["role"] == "definition":
                symbols, calls, controls, call_details = _reference_facts(
                    cursor, unit_keys
                )
                references[item["usr"]] = {
                    "external_symbols": symbols,
                    "calls": calls,
                    "controls": controls,
                    "call_details": call_details,
                }
        if (
            cursor.kind.name == "VAR_DECL"
            and cursor.spelling
            and cursor.semantic_parent.kind.name in {"TRANSLATION_UNIT", "NAMESPACE"}
        ):
            variables.append(
                {
                    "usr": cursor.get_usr() or _qualified_name(cursor),
                    "name": cursor.spelling,
                    "qualified_name": _qualified_name(cursor),
                    "type_expression": cursor.type.spelling,
                    "role": ("definition" if cursor.is_definition() else "declaration"),
                    "linkage": (
                        "internal"
                        if cursor.linkage.name in {"INTERNAL", "NO_LINKAGE"}
                        else "external"
                    ),
                    "file": location["file"],
                    **_extent_location(cursor),
                }
            )

    includes: list[dict[str, Any]] = []
    macros: list[dict[str, Any]] = []
    for cursor in translation_unit.cursor.get_children():
        location = _cursor_location(cursor)
        if location is None or location["file"] not in unit_keys:
            continue
        tokens = [token.spelling for token in cursor.get_tokens()]
        if cursor.kind.name == "INCLUSION_DIRECTIVE":
            spelling = cursor.spelling
            included = cursor.get_included_file()
            includes.append(
                {
                    "source_file": location["file"],
                    "included_file": (
                        _location_key(included.name) if included is not None else None
                    ),
                    "spelling": spelling.replace("\\", "/"),
                    "syntax": (
                        "angle"
                        if any(token.startswith("<") for token in tokens)
                        else "quote"
                    ),
                    "line": int(location["line"]),
                }
            )
        elif cursor.kind.name == "MACRO_INSTANTIATION":
            macros.append(
                {
                    "name": cursor.spelling,
                    "tokens": tokens,
                    "expression": "".join(tokens),
                    "file": location["file"],
                    **_extent_location(cursor),
                }
            )

    diagnostics = [
        {
            "severity": int(item.severity),
            "message": item.spelling,
            "file": (
                _location_key(item.location.file.name)
                if item.location.file is not None
                else None
            ),
            "line": int(item.location.line),
        }
        for item in translation_unit.diagnostics
    ]
    types.sort(
        key=lambda item: (
            item["file"],
            item["line"],
            item["qualified_name"],
            item["role"],
        )
    )
    functions.sort(
        key=lambda item: (
            item["file"],
            item["line"],
            item["qualified_name"],
            item["role"],
        )
    )
    variables.sort(
        key=lambda item: (
            item["file"],
            item["line"],
            item["qualified_name"],
            item["role"],
        )
    )
    includes.sort(
        key=lambda item: (
            item["source_file"],
            item["line"],
            str(item["included_file"] or ""),
        )
    )
    macros.sort(key=lambda item: (item["file"], item["line"], item["name"]))
    return {
        "engine": ENGINE,
        "version": clang_version(),
        "compilation_database": normalized(database_file),
        "compilation_database_sha256": compilation_database_fingerprint(database_file),
        "command_source": command_source,
        "command_file": normalized(_command_path(selected_command)),
        "types": types,
        "functions": functions,
        "variables": variables,
        "references": references,
        "includes": includes,
        "macros": macros,
        "diagnostics": diagnostics,
        "diagnostic_error_count": sum(item["severity"] >= 3 for item in diagnostics),
    }


def syntax_projection(model: dict[str, Any], path: Path) -> dict[str, Any]:
    key = _normal_key(path)
    types = [
        item
        for item in model["types"]
        if item["file"] == key and item["role"] == "definition"
    ]
    functions = [item for item in model["functions"] if item["file"] == key]
    return {
        "engine": model["engine"],
        "language": "cpp",
        "parse_error_count": model["diagnostic_error_count"],
        "includes": [
            {
                "text": item["included_file"],
                "location": {"line": item["line"]},
            }
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
                "location": {
                    "line": item["line"],
                    "end_line": item["end_line"],
                },
            }
            for item in types
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
