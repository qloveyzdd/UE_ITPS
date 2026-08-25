from __future__ import annotations

from pathlib import Path
from typing import Any

from .cpp_frontend import CppFrontendError, load_cpp_unit
from .common import iter_files, normalized, result_document
from .dependency_graph import DependencyGraph, type_names
from .source_context import load_source_context


_SUFFIXES = (".h", ".hpp", ".cpp", ".cc")


def project_cpp_files(project_root: Path) -> list[Path]:
    roots = [
        project_root / "Source",
        project_root / "Plugins",
        project_root / "Platforms",
        project_root / "Mods",
    ]
    return sorted(
        {
            path.resolve()
            for root in roots
            for suffix in _SUFFIXES
            for path in iter_files(root, suffix)
        },
        key=lambda path: normalized(path).casefold(),
    )


def _resolved_type_names(
    references: list[str],
    source_name: str,
    known: set[str],
    short_index: dict[str, list[str]],
) -> list[str]:
    resolved: list[str] = []
    for candidate in type_names(references):
        explicit = [
            name
            for name in references
            if name in known and name.rsplit("::", 1)[-1] == candidate
        ]
        target = explicit[0] if len(explicit) == 1 else None
        scope = source_name.rsplit("::", 1)[0] if "::" in source_name else ""
        while target is None and scope:
            scoped = f"{scope}::{candidate}"
            if scoped in known:
                target = scoped
                break
            scope = scope.rsplit("::", 1)[0] if "::" in scope else ""
        matches = short_index.get(candidate, [])
        if target is None and len(matches) == 1:
            target = matches[0]
        if target is not None and target not in resolved:
            resolved.append(target)
    return resolved


def _selected_node_name(
    graph: DependencyGraph, selection: str
) -> tuple[str | None, bool]:
    if selection in graph.nodes:
        return selection, False
    matches = sorted(
        name for name in graph.nodes if name.rsplit("::", 1)[-1] == selection
    )
    if len(matches) == 1:
        return matches[0], False
    return None, len(matches) > 1


def build_project_graph(
    project_root: Path,
) -> tuple[DependencyGraph, list[dict[str, Any]], list[dict[str, Any]]]:
    graph = DependencyGraph()
    parsed_files: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    project_files = project_cpp_files(project_root)
    if not project_files:
        return graph, parsed_files, problems
    try:
        model = load_cpp_unit(project_files[0], project_files, project_root)
    except CppFrontendError as exc:
        problems.append(
            {
                "severity": "error",
                "code": "project-tree-sitter-cpp-parse-failure",
                "path": project_files[0].relative_to(project_root).as_posix(),
                "message": str(exc),
            }
        )
        return graph, parsed_files, problems

    types_by_path: dict[str, list[dict[str, Any]]] = {}
    for item in model["types"]:
        if item["role"] != "definition":
            continue
        relative = Path(item["file"]).resolve().relative_to(project_root).as_posix()
        types_by_path.setdefault(relative, []).append(
            {
                "kind": item["kind"],
                "name": item["name"],
                "qualified_name": item["qualified_name"],
                "base_types": item["base_types"],
                "base_type_facts": item.get("base_type_facts", []),
                "type_references": [
                    {
                        "kind": "field",
                        "name": field["name"],
                        "type_expression": field["type_expression"],
                        "type_names": list(field.get("type", {}).get("references", [])),
                        "location": {"line": field["line"]},
                    }
                    for field in item["fields"]
                ],
                "location": {"line": item["line"]},
                "_path": relative,
            }
        )
    parsed_files = [
        {
            "path": path.relative_to(project_root).as_posix(),
            "syntax": {
                "types": types_by_path.get(
                    path.relative_to(project_root).as_posix(), []
                )
            },
        }
        for path in project_files
    ]
    for diagnostic in model["diagnostics"]:
        if diagnostic["severity"] >= 3:
            problems.append(
                {
                    "severity": "error",
                    "code": "project-tree-sitter-cpp-syntax-error",
                    "path": Path(diagnostic["file"])
                    .resolve()
                    .relative_to(project_root)
                    .as_posix(),
                    "line": diagnostic["line"],
                    "message": diagnostic["message"],
                }
            )
    all_types = [
        (item.get("_path", parsed["path"]), item)
        for parsed in parsed_files
        for item in parsed["syntax"]["types"]
    ]
    known = {item["qualified_name"] for _, item in all_types}
    short_index: dict[str, list[str]] = {}
    for name in sorted(known):
        short_index.setdefault(name.rsplit("::", 1)[-1], []).append(name)

    for path, item in all_types:
        source = item["qualified_name"]
        base_types: list[str] = []
        for base in item["base_type_facts"]:
            references = [str(value) for value in base.get("references", [])]
            resolved = _resolved_type_names(references, source, known, short_index)
            base_types.extend(resolved or type_names(references))
        graph.add_node(
            source,
            kind=item["kind"],
            file=path,
            base_types=base_types,
        )

    for parsed in parsed_files:
        for item in parsed["syntax"]["types"]:
            path = item.get("_path", parsed["path"])
            source = item["qualified_name"]
            for base in item["base_type_facts"]:
                references = [str(value) for value in base.get("references", [])]
                for target in _resolved_type_names(
                    references, source, known, short_index
                ):
                    graph.add_edge(
                        source,
                        target,
                        kind="inheritance",
                        file=path,
                        line=item["location"]["line"],
                    )
            for reference in item["type_references"]:
                for target in _resolved_type_names(
                    [str(value) for value in reference["type_names"]],
                    source,
                    known,
                    short_index,
                ):
                    graph.add_edge(
                        source,
                        target,
                        kind=reference["kind"],
                        member=reference["name"],
                        file=path,
                        line=reference["location"]["line"],
                    )
    return graph, parsed_files, problems


def dependency_result(
    project_root: Path,
) -> dict[str, Any]:
    graph, parsed_files, problems = build_project_graph(project_root)
    return result_document(
        "ue_analyze_cxx_dependencies",
        {
            "project_root": normalized(project_root),
            "source_file_count": len(parsed_files),
            "graph": graph.document(),
        },
        problems,
        responsibility="Build a project-local C++ type dependency graph and detect cycles.",
        boundaries=[
            "Only project-local C++ text under Source, Plugins, Platforms, and Mods is scanned.",
            "Edges cover inheritance and directly declared field types; compiler-resolved aliases and generated code are not inferred.",
            "Cycle and coupling results describe the observed static graph, not runtime object ownership.",
        ],
    )


def hierarchy_result(
    project_root: Path,
    class_name: str,
) -> dict[str, Any]:
    graph, parsed_files, problems = build_project_graph(project_root)
    selected_name, ambiguous = _selected_node_name(graph, class_name)
    node = graph.nodes.get(selected_name) if selected_name else None
    if node is None:
        problems.append(
            {
                "severity": "error",
                "code": "class-ambiguous" if ambiguous else "class-not-found",
                "selection": class_name,
                "message": (
                    "Multiple project-local C++ types have this short name; use the qualified name"
                    if ambiguous
                    else "No matching project-local C++ type was found"
                ),
            }
        )
    return result_document(
        "ue_query_cxx_hierarchy",
        {
            "project_root": normalized(project_root),
            "selection": {"class": class_name},
            "source_file_count": len(parsed_files),
            "match": (
                {
                    "name": node.name,
                    "kind": node.kind,
                    "files": sorted(node.files),
                    "base_types": sorted(node.base_types),
                    "ancestor_chain": graph.ancestor_chain(selected_name),
                    "descendants": graph.descendants(selected_name),
                }
                if node
                else None
            ),
        },
        problems,
        responsibility="Report the observed project-local inheritance neighborhood of one C++ type.",
        boundaries=[
            "External Engine ancestors remain named leaves unless declared in project source.",
            "Multiple inheritance is preserved in base_types; ancestor_chain follows the first deterministic base.",
        ],
    )


def impact_result(
    project_root: Path,
    symbol: str,
    max_depth: int,
) -> dict[str, Any]:
    graph, parsed_files, problems = build_project_graph(project_root)
    selected_name, ambiguous = _selected_node_name(graph, symbol)
    if selected_name is None:
        problems.append(
            {
                "severity": "error",
                "code": "symbol-ambiguous" if ambiguous else "symbol-not-found",
                "selection": symbol,
                "message": (
                    "Multiple project-local C++ types have this short name; use the qualified name"
                    if ambiguous
                    else "No matching project-local C++ type was found"
                ),
            }
        )
    return result_document(
        "ue_analyze_cxx_impact",
        {
            "project_root": normalized(project_root),
            "selection": {"symbol": symbol, "max_depth": max_depth},
            "source_file_count": len(parsed_files),
            "impacted": (
                graph.impact(selected_name, max_depth) if selected_name else []
            ),
        },
        problems,
        responsibility="Trace reverse project-local C++ type dependencies for one selected symbol.",
        boundaries=[
            "Impact means a reverse static type edge, not proof that behavior or ABI changes.",
            "Generated code, Blueprint assets, Engine source, and runtime references are excluded.",
        ],
    )


def function_flow_result(
    source: Path,
    function_name: str,
) -> dict[str, Any]:
    loaded = load_source_context(source)
    syntax = loaded["parsed_by_path"][source.resolve()]["syntax_tree"]
    matches = [
        item
        for item in syntax["functions"]
        if item["name"] == function_name
        or item["name"].split("::")[-1] == function_name
    ]
    problems: list[dict[str, Any]] = []
    problems.extend(loaded["problems"])
    if not matches:
        problems.append(
            {
                "severity": "error",
                "code": "function-not-found",
                "selection": function_name,
                "message": "No matching C++ function was found",
            }
        )
    control_kinds = {
        "if_statement": "branch",
        "switch_statement": "branch",
        "for_statement": "loop",
        "for_range_loop": "loop",
        "while_statement": "loop",
        "do_statement": "loop",
        "try_statement": "exception",
        "throw_expression": "throw",
        "return_statement": "return",
    }
    return result_document(
        "ue_trace_cxx_function_flow",
        {
            "source": normalized(source),
            "selection": {"function": function_name},
            "match_count": len(matches),
            "matches": [
                {
                    "name": item["name"],
                    "signature": item["signature"],
                    "has_body": item["has_body"],
                    "evidence": item["location"],
                    "calls": item["calls"],
                    "flow": [
                        {
                            "kind": control_kinds[control["kind"]],
                            "syntax": control["kind"],
                            "evidence": control["location"],
                        }
                        for control in item["controls"]
                    ],
                }
                for item in matches
            ],
        },
        problems,
        responsibility="Report local control-flow constructs and direct calls for selected C++ function definitions.",
        boundaries=[
            "Calls and function identities are local Tree-sitter syntax projections.",
            "The flow is local to the selected file and does not recursively follow callees.",
        ],
    )
