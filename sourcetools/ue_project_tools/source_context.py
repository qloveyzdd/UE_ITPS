from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .common import normalized, read_json, result_document
from .cpp_frontend import load_cpp_unit, syntax_projection
from .descriptor import resolve_internal_directories
from .discovery import find_nearest_uproject
from .engine import engine_resolution_status, resolve_engine
from .source_includes import (
    include_owner,
    module_records,
    owner_for_path,
    resolve_include,
    rooted_path,
)


_CPP_SUFFIXES = {".cpp", ".cc"}
_HEADER_SUFFIXES = {".h", ".hpp"}
_SOURCE_SUFFIXES = _CPP_SUFFIXES | _HEADER_SUFFIXES


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _validated_file(path: Path, suffixes: set[str], label: str) -> Path:
    resolved = path.resolve()
    if resolved.suffix.casefold() not in suffixes:
        expected = ", ".join(sorted(suffixes))
        raise ValueError(f"Expected {label} with one of {expected}: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"{label} is not a file: {resolved}")
    return resolved


def _source_unit_kind(path: Path) -> str:
    return "header" if path.suffix.casefold() in _HEADER_SUFFIXES else "cpp"


def _validated_source_files(
    source_files: Path | Sequence[Path],
) -> tuple[Path | None, Path | None]:
    requested = (
        [source_files]
        if isinstance(source_files, Path)
        else list(source_files)
    )
    if not 1 <= len(requested) <= 2:
        raise ValueError("Expected one or two explicitly selected source files")
    selected = [
        _validated_file(path, _SOURCE_SUFFIXES, "Source file")
        for path in requested
    ]
    sources = [path for path in selected if path.suffix.casefold() in _CPP_SUFFIXES]
    headers = [path for path in selected if path.suffix.casefold() in _HEADER_SUFFIXES]
    if len(selected) == 2:
        if len(sources) != 1 or len(headers) != 1:
            raise ValueError(
                "Two source files must contain one .cpp/.cc file and one .h/.hpp file"
            )
        if sources[0].stem.casefold() != headers[0].stem.casefold():
            raise ValueError(
                "Explicit source and header files must have the same basename"
            )
    return (sources[0] if sources else None, headers[0] if headers else None)


def _public_include(
    include: dict[str, Any],
    including_file: Path,
    records: list[dict[str, Any]],
    project_root: Path,
    engine_root: Path | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    spelling = str(include["spelling"])
    source_include = {
        "spelling": spelling,
        "syntax": include.get("syntax", "quote"),
    }
    if spelling.casefold().endswith(".generated.h"):
        resolution: dict[str, Any] = {"status": "generated_header"}
    elif include.get("included_file"):
        included_path = Path(str(include["included_file"])).resolve()
        resolution = {
            "status": "resolved",
            "location": rooted_path(included_path, project_root, engine_root),
            "owner": include_owner(owner_for_path(included_path, records)),
            "method": ["parser-inclusion-directive"],
        }
    else:
        resolution = resolve_include(
            source_include, including_file, records, project_root, engine_root
        )
    fact = {
        "spelling": spelling,
        "conditions": [],
        "evidence": {
            "unit": _source_unit_kind(including_file),
            "line": int(include["line"]),
        },
        "resolution": resolution,
    }
    status = str(resolution["status"])
    if status == "resolved":
        fact["resolution"] = {
            key: value for key, value in resolution.items() if key != "status"
        }
        return fact, None
    if status in {"generated_header", "generated_source", "system_or_sdk_unresolved"}:
        return fact, None
    return None, {
        "severity": "warning",
        "code": f"source-include-{status.replace('_', '-')}",
        "include": fact,
        "message": "Include provenance could not be resolved from deterministic filesystem roots",
    }


def load_source_context(
    source_files: Path | Sequence[Path],
    engine_override: Path | None = None,
    *,
    load_includes: bool = False,
    load_cpp_analysis: bool = True,
) -> dict[str, Any]:
    selected_source, selected_header = _validated_source_files(source_files)
    unit_files = [path for path in (selected_source, selected_header) if path]
    anchor = selected_source or selected_header
    if anchor is None:
        raise ValueError("No C++ source file was selected")
    project = find_nearest_uproject(anchor)
    descriptor = read_json(project)
    project_root = project.parent.resolve()
    engine_result = resolve_engine(
        project, str(descriptor.get("EngineAssociation") or ""), engine_override
    )
    engine_status = engine_resolution_status(engine_result)
    engine_root = (
        Path(engine_result["engine_root"]).resolve()
        if engine_status == "resolved"
        else None
    )
    if not _is_relative_to(anchor, project_root) and (
        engine_root is None or not _is_relative_to(anchor, engine_root)
    ):
        raise ValueError(
            "Source file must be inside the selected project or resolved Engine: "
            f"{anchor}"
        )

    additional_module_roots, _ = resolve_internal_directories(
        project, descriptor, "AdditionalRootDirectories"
    )
    additional_plugin_roots, _ = resolve_internal_directories(
        project, descriptor, "AdditionalPluginDirectories"
    )
    records = module_records(
        project_root,
        engine_root,
        additional_module_roots,
        additional_plugin_roots,
    )
    source_owner = owner_for_path(anchor, records)
    cpp_model = load_cpp_unit(anchor, unit_files, project_root)
    parsed_files = [
        (
            path,
            {
                "path": normalized(path),
                "text": path.read_text(encoding="utf-8-sig", errors="replace"),
                "problems": [],
                "syntax_tree": syntax_projection(cpp_model, path),
            },
        )
        for path in unit_files
    ]

    problems: list[dict[str, Any]] = []
    if engine_status != "resolved":
        problems.append(
            {
                "severity": "warning",
                "code": "source-unit-engine-unresolved",
                "message": "Engine provenance could not be resolved",
            }
        )
    if source_owner is None:
        problems.append(
            {
                "severity": "warning",
                "code": "source-unit-owner-unresolved",
                "source": rooted_path(anchor, project_root, engine_root),
                "message": "No enclosing Build.cs source boundary was found",
            }
        )
    for diagnostic in cpp_model["diagnostics"]:
        if diagnostic["severity"] >= 2:
            problems.append(
                {
                    "severity": "warning",
                    "code": "tree-sitter-cpp-syntax-warning",
                    "source": {
                        "path": diagnostic["file"],
                        "line": diagnostic["line"],
                    },
                    "message": diagnostic["message"],
                }
            )

    includes: list[dict[str, Any]] = []
    include_problems: list[dict[str, Any]] = []
    unit_by_key = {
        str(path.resolve()).replace("\\", "/").casefold(): path for path in unit_files
    }
    if load_includes:
        for include in cpp_model["includes"]:
            including_file = unit_by_key.get(include["source_file"])
            if including_file is None:
                continue
            fact, problem = _public_include(
                include,
                including_file,
                records,
                project_root,
                engine_root,
            )
            if fact is not None:
                includes.append(fact)
            if problem is not None:
                include_problems.append(problem)

    return {
        "includes": includes,
        "include_problems": include_problems,
        "parsed_files": parsed_files,
        "parsed_by_path": {path: parsed for path, parsed in parsed_files},
        "project_root": project_root,
        "engine_root": engine_root,
        "cpp_model": cpp_model,
        "parts": [
            item for item in cpp_model["functions"] if item["file"] in unit_by_key
        ],
        "problems": problems,
    }


def source_result(
    schema_version: str,
    loaded: dict[str, Any],
    content: dict[str, Any],
    *,
    responsibility: str,
    boundaries: list[str],
    additional_problems: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return result_document(
        schema_version,
        content,
        [*loaded["problems"], *(additional_problems or [])],
        responsibility=responsibility,
        boundaries=[
            "Only the one or two explicitly selected source files are read.",
            *boundaries,
            "C++ facts are syntax projections from the selected files; no compiler semantic binding or preprocessing is performed.",
            "Validation ok does not prove runtime behavior.",
        ],
    )
