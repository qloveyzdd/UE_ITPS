from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

from .common import SKIP_DIRS, iter_files, normalized, result_document
from .descriptor import resolve_internal_directories
from .discovery import find_nearest_uproject


HEADER_EXTENSIONS = {".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp"}
CPP_EXTENSIONS = {".cpp", ".cc", ".cxx", ".mm"}
SOURCE_EXTENSIONS = HEADER_EXTENSIONS | CPP_EXTENSIONS
SKIP_DIR_KEYS = {name.casefold() for name in SKIP_DIRS}


_BOUNDARIES = [
    "Module ownership is derived from physical *.Build.cs ancestry; UBT rules are not evaluated.",
    "Plugin ownership is derived from project-local .uplugin ancestry, including undeclared or disabled Plugins.",
    "Engine directories and external additional directories are not scanned.",
    "Generated-source exclusion uses generated directories and conventional generated filename patterns; file authorship is not inferred from file contents.",
    "Public, Classes, and Private are physical directory classifications, not effective compiler visibility.",
    "Header extensions are .h, .hh, .hpp, .hxx, .inl, and .ipp; CPP extensions are .cpp, .cc, .cxx, and .mm.",
]


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _relative(path: Path, project_root: Path) -> str:
    return path.relative_to(project_root).as_posix()


def _generated_filename(name: str) -> bool:
    folded = name.casefold()
    if ".generated." in folded or ".autogen." in folded:
        return True
    return folded.endswith(
        (
            ".gen.h",
            ".gen.hh",
            ".gen.hpp",
            ".gen.hxx",
            ".gen.inl",
            ".gen.ipp",
            ".gen.cpp",
            ".gen.cc",
            ".gen.cxx",
            ".gen.mm",
        )
    )


def _source_files(module_root: Path) -> Iterable[Path]:
    if not module_root.is_dir():
        return []
    matches: list[Path] = []
    for current, dirs, files in os.walk(module_root):
        dirs[:] = [name for name in dirs if name.casefold() not in SKIP_DIR_KEYS]
        for name in files:
            if Path(name).suffix.casefold() not in SOURCE_EXTENSIONS:
                continue
            if _generated_filename(name):
                continue
            matches.append((Path(current) / name).resolve())
    return matches


def _visibility(path: Path, module_root: Path) -> str:
    relative_parts = path.relative_to(module_root).parts
    if len(relative_parts) < 2:
        return "unclassified"
    first_directory = relative_parts[0].casefold()
    if first_directory in {"public", "classes"}:
        return "public"
    if first_directory == "private":
        return "private"
    return "unclassified"


def _additional_directory_problems(
    field: str,
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    for finding in findings:
        if finding["status"] == "invalid":
            problems.append(
                {
                    "severity": "error",
                    "code": "invalid-additional-directory",
                    "descriptor_pointer": finding["descriptor_pointer"],
                    "message": f"{field} entries must be non-empty path strings",
                }
            )
        elif finding["status"] == "skipped_external":
            problems.append(
                {
                    "severity": "warning",
                    "code": "external-additional-directory-skipped",
                    "descriptor_pointer": finding["descriptor_pointer"],
                    "message": (
                        f"External {field} entry was not scanned: {finding['resolved']}"
                    ),
                }
            )
    return problems


def _plugin_descriptors(
    roots: Iterable[Path],
    project_root: Path,
    engine_directory: Path,
) -> list[Path]:
    descriptors = {
        path
        for root in roots
        for path in iter_files(root, ".uplugin")
        if _is_within(path, project_root) and not _is_within(path, engine_directory)
    }
    return sorted(descriptors, key=lambda path: normalized(path).casefold())


def _plugin_for_rules(
    rules: Path,
    plugin_descriptors: list[Path],
) -> Path | None:
    candidates = [
        descriptor
        for descriptor in plugin_descriptors
        if _is_within(rules, descriptor.parent)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda descriptor: len(descriptor.parent.parts))


def _validated_module_rules(rules_path: Path) -> Path:
    rules = rules_path.resolve()
    if not rules.is_file():
        raise ValueError(f"Module Build.cs is not a file: {rules}")
    if not rules.name.casefold().endswith(".build.cs"):
        raise ValueError(f"Expected a Module Build.cs file: {rules}")
    module_name = rules.name[: -len(".Build.cs")]
    if not module_name:
        raise ValueError(f"Module Build.cs filename has no module name: {rules}")
    return rules


def _module_record(
    rules: Path,
    project_root: Path,
    module_roots: set[Path],
    plugin_descriptor: Path | None,
) -> dict[str, Any]:
    module_root = rules.parent
    classified: dict[str, dict[str, list[str]]] = {
        "headers": {
            "public": [],
            "private": [],
            "unclassified": [],
        },
        "cpp": {
            "public": [],
            "private": [],
            "unclassified": [],
        },
    }
    for source in _source_files(module_root):
        if not _is_within(source, project_root):
            continue
        owning_roots = [root for root in module_roots if _is_within(source, root)]
        if owning_roots and max(
            owning_roots,
            key=lambda root: len(root.parts),
        ) != module_root:
            continue
        kind = "headers" if source.suffix.casefold() in HEADER_EXTENSIONS else "cpp"
        classified[kind][_visibility(source, module_root)].append(
            _relative(source, project_root)
        )
    for kind in classified.values():
        for paths in kind.values():
            paths.sort(key=str.casefold)

    return {
        "module": rules.name[: -len(".Build.cs")],
        "plugin": plugin_descriptor.stem if plugin_descriptor else None,
        "plugin_descriptor": (
            _relative(plugin_descriptor, project_root) if plugin_descriptor else None
        ),
        "build_rules": _relative(rules, project_root),
        **classified,
    }


def _file_count(module_records: Iterable[dict[str, Any]]) -> int:
    return sum(
        len(paths)
        for module in module_records
        for kind in ("headers", "cpp")
        for paths in module[kind].values()
    )


def _module_source_paths(
    module: dict[str, Any],
    kind: str,
    project_root: Path,
) -> set[Path]:
    return {
        (project_root / path).resolve()
        for paths in module[kind].values()
        for path in paths
    }


def _companion_bases(path: Path, module_root: Path) -> list[Path]:
    bases = [path.parent / path.stem]
    relative = path.relative_to(module_root)
    if len(relative.parts) < 2:
        return bases
    first = relative.parts[0].casefold()
    tail = Path(*relative.parts[1:]).with_suffix("")
    if first == "private":
        bases.extend(
            module_root / directory / tail
            for directory in ("Public", "Classes")
        )
    elif first in {"public", "classes"}:
        bases.append(module_root / "Private" / tail)
    return bases


def _pair_module_sources(
    module: dict[str, Any],
    module_root: Path,
    project_root: Path,
) -> tuple[list[dict[str, str]], list[str], list[str], list[dict[str, Any]]]:
    headers = _module_source_paths(module, "headers", project_root)
    cpp = _module_source_paths(module, "cpp", project_root)
    header_edges: dict[Path, set[Path]] = {path: set() for path in headers}
    cpp_edges: dict[Path, set[Path]] = {path: set() for path in cpp}
    for header in headers:
        candidates = {
            (base.parent / f"{base.name}{suffix}").resolve()
            for base in _companion_bases(header, module_root)
            for suffix in CPP_EXTENSIONS
        }
        for source in candidates & cpp:
            header_edges[header].add(source)
            cpp_edges[source].add(header)

    pairs: list[dict[str, str]] = []
    problems: list[dict[str, Any]] = []
    visited_headers: set[Path] = set()
    connected_headers = {path for path, edges in header_edges.items() if edges}
    connected_cpp = {path for path, edges in cpp_edges.items() if edges}
    for start in sorted(connected_headers, key=lambda path: normalized(path).casefold()):
        if start in visited_headers:
            continue
        component_headers: set[Path] = set()
        component_cpp: set[Path] = set()
        pending: list[tuple[str, Path]] = [("header", start)]
        while pending:
            kind, path = pending.pop()
            if kind == "header":
                if path in component_headers:
                    continue
                component_headers.add(path)
                pending.extend(("cpp", candidate) for candidate in header_edges[path])
            else:
                if path in component_cpp:
                    continue
                component_cpp.add(path)
                pending.extend(("header", candidate) for candidate in cpp_edges[path])
        visited_headers.update(component_headers)
        relative_headers = sorted(
            (_relative(path, project_root) for path in component_headers),
            key=str.casefold,
        )
        relative_cpp = sorted(
            (_relative(path, project_root) for path in component_cpp),
            key=str.casefold,
        )
        if len(relative_headers) == len(relative_cpp) == 1:
            pairs.append({"header": relative_headers[0], "cpp": relative_cpp[0]})
            continue
        problems.append(
            {
                "severity": "warning",
                "code": "source-pair-ambiguous",
                "headers": relative_headers,
                "cpp": relative_cpp,
                "message": "Multiple same-named source pairing candidates were found",
            }
        )

    pairs.sort(key=lambda item: (item["header"].casefold(), item["cpp"].casefold()))
    header_only = sorted(
        (_relative(path, project_root) for path in headers - connected_headers),
        key=str.casefold,
    )
    cpp_only = sorted(
        (_relative(path, project_root) for path in cpp - connected_cpp),
        key=str.casefold,
    )
    return pairs, header_only, cpp_only, problems


def list_module_cxx_sources(rules_path: Path) -> dict[str, Any]:
    rules = _validated_module_rules(rules_path)
    project_file = find_nearest_uproject(rules)
    project_root = project_file.parent.resolve()
    engine_directory = (project_root / "Engine").resolve()
    if not _is_within(rules, project_root) or _is_within(rules, engine_directory):
        raise ValueError(f"Module Build.cs is not project-local: {rules}")

    nested_rules = {
        path.resolve()
        for path in iter_files(rules.parent, ".Build.cs")
        if _is_within(path, project_root) and not _is_within(path, engine_directory)
    }
    module_roots = {path.parent for path in nested_rules}
    module_roots.add(rules.parent)
    module = _module_record(
        rules,
        project_root,
        module_roots,
        None,
    )
    pairs, header_only, cpp_only, problems = _pair_module_sources(
        module,
        rules.parent,
        project_root,
    )
    return result_document(
        "ue_list_module_cxx_sources",
        {
            "pairs": pairs,
            "header_only": header_only,
            "cpp_only": cpp_only,
        },
        problems,
        responsibility=(
            "Pair project-local, manually maintained C++ headers and sources "
            "for one explicitly selected Module."
        ),
        boundaries=[
            "The selected Module boundary is derived from physical *.Build.cs ancestry; UBT rules are not evaluated.",
            "Nested Modules with their own *.Build.cs files are excluded from the selected Module.",
            "Reported paths are relative to the nearest unique .uproject root.",
            "Pairing uses same-stem files in the same directory and conventional Public or Classes to Private mirrors in either direction.",
            "Only one-header-to-one-source components are paired; ambiguous candidate components are reported in validation.",
            "Generated-source exclusion uses generated directories and conventional generated filename patterns; file authorship is not inferred from file contents.",
            "Header extensions are .h, .hh, .hpp, .hxx, .inl, and .ipp; CPP extensions are .cpp, .cc, .cxx, and .mm.",
        ],
    )


def list_project_cxx_sources(
    project_file: Path,
    descriptor: dict[str, Any],
) -> dict[str, Any]:
    project_file = project_file.resolve()
    project_root = project_file.parent
    engine_directory = (project_root / "Engine").resolve()
    additional_roots, additional_root_findings = resolve_internal_directories(
        project_file,
        descriptor,
        "AdditionalRootDirectories",
    )
    additional_plugin_roots, additional_plugin_findings = resolve_internal_directories(
        project_file,
        descriptor,
        "AdditionalPluginDirectories",
    )
    problems = [
        *_additional_directory_problems(
            "AdditionalRootDirectories",
            additional_root_findings,
        ),
        *_additional_directory_problems(
            "AdditionalPluginDirectories",
            additional_plugin_findings,
        ),
    ]

    plugin_search_roots = [
        project_root / "Plugins",
        project_root / "Platforms",
        project_root / "Mods",
        *additional_plugin_roots,
    ]
    plugin_descriptors = _plugin_descriptors(
        plugin_search_roots,
        project_root,
        engine_directory,
    )

    project_search_roots = [
        project_root / "Source",
        project_root / "Platforms",
        *additional_roots,
    ]
    plugin_source_roots = [
        source_root
        for plugin in plugin_descriptors
        for source_root in (plugin.parent / "Source", plugin.parent / "Platforms")
    ]
    build_rules = {
        path
        for root in [*project_search_roots, *plugin_source_roots]
        for path in iter_files(root, ".Build.cs")
        if _is_within(path, project_root) and not _is_within(path, engine_directory)
    }

    module_records: list[dict[str, Any]] = []
    module_roots = {rules.parent for rules in build_rules}
    for rules in sorted(build_rules, key=lambda path: normalized(path).casefold()):
        plugin_descriptor = _plugin_for_rules(rules, plugin_descriptors)
        module_records.append(
            _module_record(
                rules,
                project_root,
                module_roots,
                plugin_descriptor,
            )
        )

    module_records.sort(
        key=lambda item: (
            str(item["module"]).casefold(),
            str(item["plugin"] or "").casefold(),
            str(item["build_rules"]).casefold(),
        )
    )
    names: dict[str, list[dict[str, Any]]] = {}
    for module in module_records:
        names.setdefault(str(module["module"]).casefold(), []).append(module)
    for duplicates in names.values():
        if len(duplicates) < 2:
            continue
        problems.append(
            {
                "severity": "warning",
                "code": "duplicate-module-name",
                "module": duplicates[0]["module"],
                "build_rules": [item["build_rules"] for item in duplicates],
                "message": (
                    f"Module name {duplicates[0]['module']} has multiple "
                    "project-local Build.cs files"
                ),
            }
        )

    return result_document(
        "ue_list_project_cxx_sources",
        {
            "project": {
                "name": project_file.stem,
                "root": normalized(project_root),
                "descriptor": project_file.name,
            },
            "module_count": len(module_records),
            "file_count": _file_count(module_records),
            "modules": module_records,
        },
        problems,
        responsibility=(
            "List project-local, manually maintained C++ source candidates "
            "grouped by Module, Plugin, file kind, and visibility."
        ),
        boundaries=_BOUNDARIES,
    )
