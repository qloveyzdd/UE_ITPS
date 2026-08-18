from __future__ import annotations

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
    public_owner,
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


def _automatic_companions(
    source: Path, source_owner: dict[str, Any] | None
) -> list[Path]:
    companion_suffixes = (
        _CPP_SUFFIXES
        if source.suffix.casefold() in _HEADER_SUFFIXES
        else _HEADER_SUFFIXES
    )
    candidate_bases = [source.parent / source.stem]
    if source_owner is not None:
        module_root = Path(source_owner["root"]).resolve()
        try:
            relative = source.relative_to(module_root)
        except ValueError:
            relative = None
        if relative is not None and relative.parts:
            first = relative.parts[0].casefold()
            tail = relative.parts[1:]
            if first == "private":
                candidate_bases.extend(
                    module_root / directory / Path(*tail).with_suffix("")
                    for directory in ("Public", "Classes")
                )
            elif first in {"public", "classes"}:
                candidate_bases.append(
                    module_root / "Private" / Path(*tail).with_suffix("")
                )
    candidates = {
        candidate.resolve()
        for base in candidate_bases
        for suffix in companion_suffixes
        if (candidate := base.with_suffix(suffix)).is_file()
    }
    return sorted(candidates, key=lambda path: normalized(path).casefold())


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
    source_file: Path,
    engine_override: Path | None = None,
    *,
    load_includes: bool = False,
    load_cpp_analysis: bool = True,
) -> dict[str, Any]:
    source = _validated_file(source_file, _SOURCE_SUFFIXES, "Source file")
    project = find_nearest_uproject(source)
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
    if not _is_relative_to(source, project_root) and (
        engine_root is None or not _is_relative_to(source, engine_root)
    ):
        raise ValueError(
            "Source file must be inside the selected project or resolved Engine: "
            f"{source}"
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
    source_owner = owner_for_path(source, records)
    companion_candidates = _automatic_companions(source, source_owner)
    selected_companion = (
        companion_candidates[0] if len(companion_candidates) == 1 else None
    )
    source_is_header = source.suffix.casefold() in _HEADER_SUFFIXES
    selected_source = selected_companion if source_is_header else source
    selected_header = source if source_is_header else selected_companion
    unit_files = [path for path in (selected_source, selected_header) if path]
    anchor = selected_source or selected_header
    if anchor is None:
        raise ValueError(f"No C++ source unit could be selected for: {source}")
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
                "source": rooted_path(source, project_root, engine_root),
                "message": "No enclosing Build.cs source boundary was found",
            }
        )
    if len(companion_candidates) > 1:
        companion_kind = "source" if source_is_header else "header"
        problems.append(
            {
                "severity": "warning",
                "code": f"source-unit-{companion_kind}-ambiguous",
                "candidates": [
                    rooted_path(candidate, project_root, engine_root)
                    for candidate in companion_candidates
                ],
                "message": f"Multiple automatically derived companion {companion_kind} files were found",
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
    header_key = (
        str(selected_header.resolve()).replace("\\", "/").casefold()
        if selected_header is not None
        else None
    )
    if load_includes:
        for include in cpp_model["includes"]:
            including_file = unit_by_key.get(include["source_file"])
            if including_file is None:
                continue
            if include.get("included_file") == header_key or (
                selected_header is not None
                and str(include.get("spelling", "")).casefold()
                == selected_header.name.casefold()
            ):
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

    source_fact = (
        rooted_path(selected_source, project_root, engine_root)
        if selected_source is not None
        else None
    )
    header_fact = (
        rooted_path(selected_header, project_root, engine_root)
        if selected_header is not None
        else None
    )
    return {
        "path_roots": {
            "project": normalized(project_root),
            "engine": normalized(engine_root) if engine_root else None,
        },
        "context": {
            "project_descriptor": project.name,
            "project_discovery_method": "nearest-source-ancestor",
            "engine": {
                "status": engine_status,
                "version": engine_result.get("version"),
            },
            "source_owner": public_owner(source_owner),
            "cpp_analyzer": {
                "engine": cpp_model["engine"],
                "version": cpp_model["version"],
                "model": "syntax",
            },
        },
        "source_unit": {"source": source_fact, "header": header_fact},
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
    syntax_trees = [
        {
            "source": rooted_path(path, loaded["project_root"], loaded["engine_root"]),
            "engine": parsed["syntax_tree"]["engine"],
            "language": parsed["syntax_tree"]["language"],
            "parse_error_count": parsed["syntax_tree"]["parse_error_count"],
        }
        for path, parsed in loaded["parsed_files"]
    ]
    return result_document(
        schema_version,
        {
            "path_roots": loaded["path_roots"],
            "context": loaded["context"],
            "source_unit": loaded["source_unit"],
            "analysis": {"syntax_trees": syntax_trees},
            **content,
        },
        [*loaded["problems"], *(additional_problems or [])],
        responsibility=responsibility,
        boundaries=[
            "Only the selected source file and one unambiguous automatically derived companion are emitted.",
            *boundaries,
            "C++ facts are syntax projections from the selected files; no compiler semantic binding or preprocessing is performed.",
            "Validation ok does not prove runtime behavior.",
        ],
    )
