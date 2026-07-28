from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

from .common import SKIP_DIRS, iter_files, normalized, result_document
from .descriptor import resolve_internal_directories


HEADER_EXTENSIONS = {".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp"}
CPP_EXTENSIONS = {".cpp", ".cc", ".cxx", ".mm"}
SOURCE_EXTENSIONS = HEADER_EXTENSIONS | CPP_EXTENSIONS
SKIP_DIR_KEYS = {name.casefold() for name in SKIP_DIRS}


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
        module_root = rules.parent
        plugin_descriptor = _plugin_for_rules(rules, plugin_descriptors)
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
            if (
                owning_roots
                and max(owning_roots, key=lambda root: len(root.parts)) != module_root
            ):
                continue
            kind = "headers" if source.suffix.casefold() in HEADER_EXTENSIONS else "cpp"
            classified[kind][_visibility(source, module_root)].append(
                _relative(source, project_root)
            )
        for kind in classified.values():
            for paths in kind.values():
                paths.sort(key=str.casefold)

        module_records.append(
            {
                "module": rules.name[: -len(".Build.cs")],
                "plugin": plugin_descriptor.stem if plugin_descriptor else None,
                "plugin_descriptor": (
                    _relative(plugin_descriptor, project_root)
                    if plugin_descriptor
                    else None
                ),
                "build_rules": _relative(rules, project_root),
                **classified,
            }
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

    file_count = sum(
        len(paths)
        for module in module_records
        for kind in ("headers", "cpp")
        for paths in module[kind].values()
    )
    return result_document(
        "ue-itps.project-cxx-sources.v1",
        {
            "project": {
                "name": project_file.stem,
                "root": normalized(project_root),
                "descriptor": project_file.name,
            },
            "module_count": len(module_records),
            "file_count": file_count,
            "modules": module_records,
        },
        problems,
        responsibility=(
            "List project-local, manually maintained C++ source candidates "
            "grouped by Module, Plugin, file kind, and visibility."
        ),
        boundaries=[
            "Module ownership is derived from physical *.Build.cs ancestry; UBT rules are not evaluated.",
            "Plugin ownership is derived from project-local .uplugin ancestry, including undeclared or disabled Plugins.",
            "Engine directories and external additional directories are not scanned.",
            "Generated-source exclusion uses generated directories and conventional generated filename patterns; file authorship is not inferred from file contents.",
            "Public, Classes, and Private are physical directory classifications, not effective compiler visibility.",
            "Header extensions are .h, .hh, .hpp, .hxx, .inl, and .ipp; CPP extensions are .cpp, .cc, .cxx, and .mm.",
        ],
    )
