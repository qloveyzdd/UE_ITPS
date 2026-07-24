from __future__ import annotations

import os
from pathlib import Path

from .common import SKIP_DIRS, normalized, result_document


def discover_uprojects(root: Path) -> list[Path]:
    if root.is_file():
        return [root.resolve()] if root.suffix.casefold() == ".uproject" else []

    matches: list[Path] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        for name in files:
            if name.casefold().endswith(".uproject"):
                matches.append((Path(current) / name).resolve())
    return sorted(matches, key=lambda item: normalized(item).casefold())


def find_nearest_uproject(source: Path) -> Path:
    """Find the unique .uproject at the nearest ancestor of a source file."""
    source_path = source.resolve()
    for directory in (source_path.parent, *source_path.parents[1:]):
        candidates = sorted(
            (
                path.resolve()
                for path in directory.iterdir()
                if path.is_file() and path.suffix.casefold() == ".uproject"
            ),
            key=lambda item: normalized(item).casefold(),
        )
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            formatted = "\n".join(
                f"  - {normalized(path)}" for path in candidates
            )
            raise ValueError(
                "Multiple .uproject files found at the nearest source ancestor "
                f"{normalized(directory)}:\n{formatted}"
            )
    raise ValueError(
        "No .uproject file found in the source file's ancestor directories: "
        f"{normalized(source_path)}"
    )


def select_uproject(project: str | None, search_root: str) -> tuple[Path, list[Path]]:
    search_input = Path(project or search_root).expanduser()
    candidates = discover_uprojects(search_input)
    if not candidates:
        raise RuntimeError("No .uproject file found")
    if len(candidates) > 1:
        formatted = "\n".join(f"  - {normalized(path)}" for path in candidates)
        raise RuntimeError(
            f"Multiple .uproject files found; pass --project explicitly:\n{formatted}"
        )
    return candidates[0], candidates


def discovery_result(root: Path) -> dict[str, object]:
    candidates = discover_uprojects(root.expanduser())
    status = (
        "not-found"
        if not candidates
        else ("selected" if len(candidates) == 1 else "ambiguous")
    )
    problems: list[dict[str, str]] = []
    if status != "selected":
        problems.append(
            {
                "severity": "error",
                "code": f"project-discovery-{status}",
                "message": (
                    "No .uproject file was found under the search root"
                    if status == "not-found"
                    else (
                        "Multiple .uproject files were found; pass one "
                        "project explicitly"
                    )
                ),
            }
        )
    return result_document(
        "ue-itps.project-discovery.v1",
        {
            "search_root": normalized(root.expanduser()),
            "status": status,
            "candidate_count": len(candidates),
            "candidates": [normalized(path) for path in candidates],
        },
        problems,
        responsibility="Discover .uproject files under one search root.",
        boundaries=[
            "The tool does not choose between multiple candidates.",
            "Discovery does not parse, validate, build, or run a project.",
        ],
    )
