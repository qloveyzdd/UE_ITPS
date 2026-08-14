from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import iter_files, normalized, result_document
from .source_parser import registration_macros
from .source_tokens import lex_source


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


def _registration_items(source: Path) -> list[dict[str, Any]]:
    text = source.read_text(encoding="utf-8-sig", errors="replace")
    tokens = lex_source(text)
    return [
        item
        for item in registration_macros(text, tokens)
        if item["macro"] in _SUPPORTED_REGISTRATION_MACROS
    ]


def _header_candidates(source: Path, module_root: Path) -> list[Path]:
    candidate_bases = [source.parent / source.stem]
    relative = source.relative_to(module_root)
    if relative.parts and relative.parts[0].casefold() == "private":
        tail = Path(*relative.parts[1:]).with_suffix("")
        candidate_bases.extend(
            module_root / public_dir / tail
            for public_dir in ("Public", "Classes")
        )
    candidates = {
        candidate.resolve()
        for base in candidate_bases
        if (candidate := base.with_suffix(".h")).is_file()
    }
    return sorted(candidates, key=lambda path: normalized(path).casefold())


def _entrypoint(
    source: Path,
    registration: dict[str, Any],
    header: Path | None,
) -> dict[str, Any]:
    return {
        "header": normalized(header) if header else None,
        "source": normalized(source),
        "registration": {
            "macro": registration["macro"],
            "module_class": registration.get("module_class"),
            "module_name": registration.get("module_name"),
            "source_line": int(registration["location"]["line"]),
        },
    }


def inspect_module_entry(rules_path: Path) -> dict[str, Any]:
    rules, module_name = _validated_rules_path(rules_path)
    module_root = rules.parent.resolve()
    problems: list[dict[str, Any]] = []
    entrypoints: list[dict[str, Any]] = []

    for source in iter_files(module_root, ".cpp"):
        registrations = [
            item
            for item in _registration_items(source)
            if str(item.get("module_name", "")).casefold()
            == module_name.casefold()
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
        entrypoints.extend(
            _entrypoint(source, registration, header)
            for registration in registrations
        )

    entrypoints.sort(
        key=lambda item: (
            str(item["source"]).casefold(),
            int(item["registration"]["source_line"]),
            str(item["registration"]["macro"]),
        )
    )
    source_candidates = list(
        dict.fromkeys(str(item["source"]) for item in entrypoints)
    )
    if not entrypoints:
        problems.append(
            {
                "severity": "error",
                "code": "module-entry-registration-not-found",
                "module_name": module_name,
                "supported_macros": sorted(_SUPPORTED_REGISTRATION_MACROS),
                "message": (
                    "No matching IMPLEMENT_PRIMARY_GAME_MODULE or "
                    f"IMPLEMENT_MODULE registration was found for {module_name}"
                ),
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
        {
            "entrypoints": entrypoints,
        },
        problems,
        responsibility=(
            "Locate one module's .cpp registration entry and its uniquely matched "
            "same-named .h file."
        ),
        boundaries=[
            "The selected Build.cs parent directory defines the module source boundary.",
            "Only .cpp files are scanned for IMPLEMENT_PRIMARY_GAME_MODULE and IMPLEMENT_MODULE.",
            "Entrypoint source and header paths are absolute.",
            "Headers are matched by same basename in the source directory or conventional Public and Classes mirrors of Private.",
            "Header contents, module classes, functions, callbacks, lifecycle state, and runtime behavior are not analyzed.",
        ],
    )
