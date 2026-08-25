from __future__ import annotations

from pathlib import Path
from typing import Any

from .cpp_frontend import load_cpp_unit
from .common import iter_files, normalized, result_document
from .discovery import find_nearest_uproject


_SUPPORTED_REGISTRATION_MACROS = frozenset(
    {"IMPLEMENT_PRIMARY_GAME_MODULE", "IMPLEMENT_MODULE"}
)


def _validated_rules_path(rules_path: Path) -> tuple[Path, str]:
    rules = rules_path.resolve()
    if not rules.is_file():
        raise ValueError(f"Module Build.cs is not a file: {rules}")
    if not rules.name.casefold().endswith(".build.cs"):
        raise ValueError(f"Expected a Module Build.cs file: {rules}")
    module_name = rules.name[: -len(".Build.cs")]
    if not module_name:
        raise ValueError(f"Module Build.cs filename has no module name: {rules}")
    return rules, module_name


def registration_macros_for_source(
    source: Path,
    project_root: Path,
) -> list[dict[str, Any]]:
    model = load_cpp_unit(
        source.resolve(),
        [source.resolve()],
        project_root.resolve(),
    )
    source_key = str(source.resolve()).replace("\\", "/").casefold()
    results = []
    for macro in model["macros"]:
        if (
            macro["file"] != source_key
            or macro["name"] not in _SUPPORTED_REGISTRATION_MACROS
        ):
            continue
        arguments = list(macro.get("arguments", []))
        module_class = str(arguments[0].get("expression", "")) if arguments else None
        module_name = None
        if len(arguments) > 1:
            literal_values = list(arguments[1].get("literal_values", []))
            module_name = (
                str(literal_values[0])
                if literal_values
                else str(arguments[1].get("expression", ""))
            )
        results.append(
            {
                "macro": macro["name"],
                "module_class": module_class,
                "module_name": module_name,
                "location": {"line": int(macro["line"])},
            }
        )
    return results


def _header_candidates(source: Path, module_root: Path) -> list[Path]:
    candidate_bases = [source.parent / source.stem]
    relative = source.relative_to(module_root)
    if relative.parts and relative.parts[0].casefold() == "private":
        tail = Path(*relative.parts[1:]).with_suffix("")
        candidate_bases.extend(
            module_root / public_dir / tail for public_dir in ("Public", "Classes")
        )
    candidates = {
        candidate.resolve()
        for base in candidate_bases
        if (candidate := base.with_suffix(".h")).is_file()
    }
    return sorted(candidates, key=lambda path: normalized(path).casefold())


def inspect_module_entry(
    rules_path: Path,
) -> dict[str, Any]:
    rules, module_name = _validated_rules_path(rules_path)
    module_root = rules.parent.resolve()
    project_root = find_nearest_uproject(rules).parent.resolve()
    problems: list[dict[str, Any]] = []
    entrypoints: list[dict[str, Any]] = []
    for source in iter_files(module_root, ".cpp"):
        registrations = [
            item
            for item in registration_macros_for_source(source, project_root)
            if str(item.get("module_name", "")).casefold() == module_name.casefold()
        ]
        if not registrations:
            continue
        headers = _header_candidates(source, module_root)
        header = headers[0] if len(headers) == 1 else None
        if len(headers) > 1:
            problems.append(
                {
                    "severity": "warning",
                    "code": "module-entry-header-ambiguous",
                    "source": normalized(source),
                    "candidates": [normalized(candidate) for candidate in headers],
                    "message": "Multiple same-named module entry headers were found",
                }
            )
        for registration in registrations:
            entrypoints.append(
                {
                    "header": normalized(header) if header else None,
                    "source": normalized(source),
                    "registration": {
                        "macro": registration["macro"],
                        "module_class": registration["module_class"],
                        "module_name": registration["module_name"],
                        "source_line": int(registration["location"]["line"]),
                    },
                }
            )
    entrypoints.sort(
        key=lambda item: (
            str(item["source"]).casefold(),
            int(item["registration"]["source_line"]),
            str(item["registration"]["macro"]),
        )
    )
    source_candidates = list(dict.fromkeys(str(item["source"]) for item in entrypoints))
    if not entrypoints:
        problems.append(
            {
                "severity": "error",
                "code": "module-entry-registration-not-found",
                "module_name": module_name,
                "supported_macros": sorted(_SUPPORTED_REGISTRATION_MACROS),
                "message": f"No matching Tree-sitter C++ module registration was found for {module_name}",
            }
        )
    elif len(source_candidates) > 1:
        problems.append(
            {
                "severity": "warning",
                "code": "module-entry-source-ambiguous",
                "module_name": module_name,
                "candidates": source_candidates,
                "message": "Matching module registrations were found in multiple source files",
            }
        )
    return result_document(
        "ue_inspect_module_entry",
        {"entrypoints": entrypoints},
        problems,
        responsibility="Locate syntax-confirmed module registration entries.",
        boundaries=[
            "Each .cpp file is parsed independently with Tree-sitter C++.",
            "Registration macros are read from local source text without preprocessing.",
            "Headers are matched by conventional same-basename locations and are not analyzed.",
        ],
    )
