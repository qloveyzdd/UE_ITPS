from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import iter_files, normalized, result_document


def find_build_descriptor(
    project_file: Path,
    *,
    kind: str,
    name: str,
    engine_build_version: Path | None = None,
) -> dict[str, Any]:
    """Find one same-named Build.cs or .uplugin under selected search roots."""
    if kind not in {"module", "plugin"}:
        raise ValueError(f"Unsupported build descriptor kind: {kind}")

    project = project_file.resolve()
    project_root = project.parent

    suffix = ".Build.cs" if kind == "module" else ".uplugin"
    candidates_by_path: dict[str, str] = {}
    roots = [project_root]
    if engine_build_version is not None:
        build_version = engine_build_version.expanduser().resolve()
        if not build_version.is_file():
            raise ValueError(f"Engine Build.version is not a file: {build_version}")
        if (
            build_version.name.casefold() != "build.version"
            or build_version.parent.name.casefold() != "build"
            or build_version.parent.parent.name.casefold() != "engine"
        ):
            raise ValueError(
                "Expected an Engine/Build/Build.version file: "
                f"{build_version}"
            )
        roots.append(build_version.parents[1])
    for root in roots:
        for path in iter_files(root, suffix, {name}):
            normalized_path = normalized(path)
            candidates_by_path.setdefault(
                normalized_path.casefold(),
                normalized_path,
            )

    candidates = sorted(
        candidates_by_path.values(),
        key=str.casefold,
    )
    status = (
        "selected"
        if len(candidates) == 1
        else ("not-found" if not candidates else "ambiguous")
    )
    problems: list[dict[str, Any]] = []
    if status == "not-found":
        if engine_build_version is not None:
            problems.append(
                {
                    "severity": "error",
                    "code": "build-descriptor-not-found",
                    "message": (
                        f"No {name}{suffix} file was found under the project "
                        "or explicitly selected Engine roots"
                    ),
                }
            )
        else:
            problems.append(
                {
                    "severity": "warning",
                    "code": "build-descriptor-not-found-in-project",
                    "message": (
                        f"No {name}{suffix} file was found under the project root; "
                        "it may exist in an Engine. Rerun with "
                        "--engine-build-version FILE to include Engine files"
                    ),
                }
            )
    elif status == "ambiguous":
        problems.append(
            {
                "severity": "error",
                "code": "build-descriptor-ambiguous",
                "message": (
                    f"{len(candidates)} {name}{suffix} files were found; "
                    "no candidate was selected"
                ),
            }
        )

    return result_document(
        "ue_find_build_descriptor",
        {"candidates": candidates},
        problems,
        responsibility=(
            "Find one same-named Module Build.cs or Plugin .uplugin under a "
            "project root and, when requested, an explicitly selected Engine root."
        ),
        boundaries=[
            "Filename matching is case-insensitive and does not evaluate UnrealBuildTool rules.",
            "A unique physical file does not prove that the Module or Plugin is enabled for a build profile.",
            "Engine directories are searched only when --engine-build-version explicitly selects an Engine.",
            "External project directories are not searched.",
            "Generated, binary, cache, and local-state directories are excluded from traversal.",
        ],
    )
