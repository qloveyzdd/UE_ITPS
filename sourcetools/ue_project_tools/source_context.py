from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import normalized, read_json, result_document
from .descriptor import resolve_internal_directories
from .discovery import find_nearest_uproject
from .engine import resolve_engine
from .source_includes import (
    extract_includes,
    module_records,
    owner_for_path,
    public_owner,
    resolve_include,
    rooted_path,
)
from .source_parser import parse_cpp_file
from .source_namespaces import (
    namespace_at,
    observed_namespace_names,
    resolve_observed_namespace,
)
from .source_tokens import delimiter_problems, lex_source
from .syntax_tree import parse_cpp_syntax


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
    source: Path,
    source_owner: dict[str, Any] | None,
) -> list[Path]:
    source_suffix = source.suffix.casefold()
    companion_suffixes = (
        _CPP_SUFFIXES
        if source_suffix in _HEADER_SUFFIXES
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
                    module_root / public_dir / Path(*tail).with_suffix("")
                    for public_dir in ("Public", "Classes")
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


def _lightweight_source(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    tokens = lex_source(text)
    syntax_tree = parse_cpp_syntax(text)
    problems = delimiter_problems(tokens)
    if syntax_tree["parse_error_count"]:
        problems.append(
            {
                "severity": "warning",
                "code": "cxx-syntax-tree-errors",
                "count": syntax_tree["parse_error_count"],
                "message": "Tree-sitter reported incomplete C++ syntax regions after UE macro normalization",
            }
        )
    return {
        "path": normalized(path),
        "text": text,
        "tokens": tokens,
        "syntax_tree": syntax_tree,
        "problems": problems,
    }


def _parse_source_pair(
    selected_source: Path | None,
    selected_header: Path | None,
    *,
    load_cpp_analysis: bool,
) -> list[tuple[Path, dict[str, Any]]]:
    parsed_files: list[tuple[Path, dict[str, Any]]] = []
    for path in (selected_source, selected_header):
        if path is None:
            continue
        parsed = (
            parse_cpp_file(path)
            if load_cpp_analysis
            else _lightweight_source(path)
        )
        parsed_files.append((path, parsed))
    if load_cpp_analysis:
        _classify_namespace_qualified_definitions(parsed_files)
    return parsed_files


def _classify_namespace_qualified_definitions(
    parsed_files: list[tuple[Path, dict[str, Any]]],
) -> None:
    known_namespaces = {
        namespace
        for _path, parsed in parsed_files
        for namespace in observed_namespace_names(
            parsed["namespace_scopes"]
        )
    }
    for _path, parsed in parsed_files:
        member_definitions: list[dict[str, Any]] = []
        for definition in parsed["external_definitions"]:
            qualifier = str(definition["qualifier"])
            namespace = resolve_observed_namespace(
                qualifier,
                namespace_at(
                    parsed["namespace_scopes"],
                    int(definition["_token_index"]),
                ),
                known_namespaces,
            )
            if namespace is None:
                member_definitions.append(definition)
                continue
            parsed["free_functions"].append(
                {
                    "name": definition["name"],
                    "parameters": definition["parameters"],
                    "signature": definition["signature"],
                    "location": definition["location"],
                    "body_range": definition["body_range"],
                    "_token_index": definition["_token_index"],
                    "_name_index": definition["_name_index"],
                    "_explicit_namespace": namespace,
                }
            )
        parsed["external_definitions"] = member_definitions
        parsed["free_functions"].sort(
            key=lambda item: int(item["_token_index"])
        )


def _collect_include_facts(
    parsed_files: list[tuple[Path, dict[str, Any]]],
    records: list[dict[str, Any]],
    project_root: Path,
    engine_root: Path | None,
    header_locations: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    includes: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    messages = {
        "ambiguous": "Include resolved to multiple filesystem candidates",
        "not_found": "Include could not be located in known source roots",
        "macro_unresolved": "Include macro could not be resolved statically",
    }
    retained_unresolved = {
        "generated_header",
        "generated_source",
        "system_or_sdk_unresolved",
    }
    for path, parsed in parsed_files:
        unit = _source_unit_kind(path)
        for include in extract_includes(str(parsed["text"])):
            resolution = resolve_include(
                include,
                path,
                records,
                project_root,
                engine_root,
            )
            resolved_locations = [
                *(
                    [resolution["location"]]
                    if "location" in resolution
                    else []
                ),
                *[
                    candidate["location"]
                    for candidate in resolution.get("candidates", [])
                ],
            ]
            if any(
                location in header_locations
                for location in resolved_locations
            ):
                continue

            fact = {
                "spelling": include["spelling"],
                "conditions": include["conditions"],
                "evidence": {
                    "unit": unit,
                    "line": int(include["line"]),
                },
                "resolution": resolution,
            }
            status = str(resolution["status"])
            if status == "resolved":
                fact["resolution"] = {
                    key: value
                    for key, value in resolution.items()
                    if key != "status"
                }
                includes.append(fact)
            elif status in retained_unresolved:
                includes.append(fact)
            else:
                problems.append(
                    {
                        "severity": "warning",
                        "code": (
                            f"source-include-{status.replace('_', '-')}"
                        ),
                        "include": fact,
                        "message": messages.get(
                            status,
                            "Include provenance could not be resolved",
                        ),
                    }
                )
    return includes, problems


def _source_context_problems(
    engine_result: dict[str, Any],
    source_owner: dict[str, Any] | None,
    source: Path,
    source_is_header: bool,
    companion_candidates: list[Path],
    parsed_files: list[tuple[Path, dict[str, Any]]],
    project_root: Path,
    engine_root: Path | None,
) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    if engine_result["status"] != "resolved":
        problems.append(
            {
                "severity": "warning",
                "code": "source-unit-engine-unresolved",
                "message": (
                    "Engine provenance could not be resolved; project source "
                    "facts remain available but Engine ownership may be "
                    "incomplete"
                ),
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
                "message": (
                    "Multiple automatically derived companion "
                    f"{companion_kind} files were found"
                ),
            }
        )
    for path, parsed in parsed_files:
        problems.extend(
            {
                **problem,
                "source": rooted_path(path, project_root, engine_root),
            }
            for problem in parsed["problems"]
        )
    return problems


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
        project,
        str(descriptor.get("EngineAssociation") or ""),
        engine_override,
    )
    engine_root = (
        Path(engine_result["engine_root"]).resolve()
        if engine_result["status"] == "resolved"
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
    header_candidates = (
        [source] if source_is_header else companion_candidates
    )
    header_locations = [
        rooted_path(candidate, project_root, engine_root)
        for candidate in header_candidates
    ]
    parsed_files = _parse_source_pair(
        selected_source,
        selected_header,
        load_cpp_analysis=load_cpp_analysis,
    )
    includes, include_problems = (
        _collect_include_facts(
            parsed_files,
            records,
            project_root,
            engine_root,
            header_locations,
        )
        if load_includes
        else ([], [])
    )
    problems = _source_context_problems(
        engine_result,
        source_owner,
        source,
        source_is_header,
        companion_candidates,
        parsed_files,
        project_root,
        engine_root,
    )

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
                "status": engine_result["status"],
                "version": engine_result.get("version"),
            },
            "source_owner": public_owner(source_owner),
        },
        "source_unit": {
            "source": source_fact,
            "header": header_fact,
        },
        "includes": includes,
        "include_problems": include_problems,
        "parsed_files": parsed_files,
        "parsed_by_path": {path: parsed for path, parsed in parsed_files},
        "project_root": project_root,
        "engine_root": engine_root,
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
        if "syntax_tree" in parsed
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
            "Only the selected .h/.hpp/.cpp/.cc file and one unambiguous automatically derived companion are read as C++ source.",
            *boundaries,
            "The result does not decide required dependencies, feature meaning, implementation correctness, or build-rule changes.",
            "Validation reports input and locally observable structural problems; ok does not prove compilation or runtime behavior.",
        ],
    )
