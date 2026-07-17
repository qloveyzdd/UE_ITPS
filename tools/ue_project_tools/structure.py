from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import normalized, result_document


PROJECT_DIRECTORIES = (
    ("Source", "source"),
    ("Config", "configuration"),
    ("Content", "content"),
    ("Plugins", "plugins"),
    ("Build", "build"),
    ("Platforms", "platform-extensions"),
)

BUILD_AND_IDE_PATHS = (
    ("Binaries", "directory", "binaries"),
    ("Intermediate", "directory", "build-intermediate"),
)

CACHE_AND_LOCAL_STATE_PATHS = (
    ("DerivedDataCache", "directory", "derived-data-cache"),
    ("Saved", "directory", "saved-state"),
    (".vs", "directory", "visual-studio-state"),
    (".idea", "directory", "jetbrains-state"),
)


def path_kind(path: Path) -> str:
    if path.is_file():
        return "file"
    if path.is_dir():
        return "directory"
    if path.exists():
        return "other"
    return "missing"


def path_state(
    project_root: Path,
    path: Path,
    role: str,
    *,
    expected_type: str,
) -> dict[str, Any]:
    actual_type = path_kind(path)
    return {
        "project_relative_path": path.relative_to(project_root).as_posix(),
        "role": role,
        "expected_type": expected_type,
        "actual_type": actual_type,
    }


def type_problem(item: dict[str, Any], *, severity: str) -> dict[str, Any] | None:
    if item["actual_type"] in {"missing", item["expected_type"]}:
        return None
    return {
        "severity": severity,
        "code": "project-path-type-mismatch",
        "project_relative_path": item["project_relative_path"],
        "expected_type": item["expected_type"],
        "actual_type": item["actual_type"],
        "message": (
            f"Expected {item['project_relative_path']} to be a "
            f"{item['expected_type']}, "
            f"but found {item['actual_type']}"
        ),
    }


def classify_project_paths(
    project_file: Path, descriptor: dict[str, Any]
) -> dict[str, Any]:
    """Classify project-root paths using only explicit descriptor evidence."""
    project_file = project_file.resolve()
    project_root = project_file.parent
    problems: list[dict[str, Any]] = []

    descriptor_item = path_state(
        project_root,
        project_file,
        "project-descriptor",
        expected_type="file",
    )

    if descriptor_item["actual_type"] == "missing":
        problems.append(
            {
                "severity": "error",
                "code": "project-descriptor-missing",
                "project_relative_path": descriptor_item["project_relative_path"],
                "message": "The selected .uproject does not exist",
            }
        )
    else:
        problem = type_problem(descriptor_item, severity="error")
        if problem:
            problems.append(problem)

    project_directories = []
    for relative, role in PROJECT_DIRECTORIES:
        item = path_state(
            project_root,
            project_root / relative,
            role,
            expected_type="directory",
        )
        project_directories.append(item)
        problem = type_problem(item, severity="error")
        if problem:
            problems.append(problem)

    module_declarations = descriptor.get("Modules")
    additional_root_declarations = descriptor.get("AdditionalRootDirectories")
    has_declared_modules = (
        isinstance(module_declarations, list) and bool(module_declarations)
    )
    has_declared_additional_roots = (
        isinstance(additional_root_declarations, list)
        and any(
            isinstance(value, str) and bool(value)
            for value in additional_root_declarations
        )
    )
    source_item = next(
        item for item in project_directories if item["role"] == "source"
    )
    if (
        has_declared_modules
        and not has_declared_additional_roots
        and source_item["actual_type"] == "missing"
    ):
        problems.append(
            {
                "severity": "error",
                "code": "declared-modules-source-directory-missing",
                "descriptor_pointer": "/Modules",
                "project_relative_path": source_item["project_relative_path"],
                "message": (
                    ".uproject declares project Modules, no AdditionalRootDirectories "
                    "are declared, and the conventional Source directory is missing"
                ),
            }
        )

    build_and_ide_paths = [
        path_state(
            project_root,
            project_root / relative,
            role,
            expected_type=expected_type,
        )
        for relative, expected_type, role in BUILD_AND_IDE_PATHS
    ]
    build_and_ide_paths.append(
        path_state(
            project_root,
            project_root / f"{project_file.stem}.sln",
            "ide-workspace",
            expected_type="file",
        )
    )

    cache_and_local_state_paths = [
        path_state(
            project_root,
            project_root / relative,
            role,
            expected_type=expected_type,
        )
        for relative, expected_type, role in CACHE_AND_LOCAL_STATE_PATHS
    ]
    for item in [*build_and_ide_paths, *cache_and_local_state_paths]:
        problem = type_problem(item, severity="warning")
        if problem:
            problems.append(problem)

    known_directory_names = {
        *(relative.casefold() for relative, _ in PROJECT_DIRECTORIES),
        *(relative.casefold() for relative, _, _ in BUILD_AND_IDE_PATHS),
        *(relative.casefold() for relative, _, _ in CACHE_AND_LOCAL_STATE_PATHS),
    }
    unclassified_root_directories = []
    if project_root.is_dir():
        for child in sorted(project_root.iterdir(), key=lambda path: path.name.casefold()):
            if not child.is_dir() or child.name.casefold() in known_directory_names:
                continue
            item = path_state(
                project_root,
                child,
                "unclassified",
                expected_type="directory",
            )
            unclassified_root_directories.append(item)
            problems.append(
                {
                    "severity": "warning",
                    "code": "unclassified-project-root-directory",
                    "project_relative_path": item["project_relative_path"],
                    "message": "Project-root directory is not classified by this tool",
                }
            )

    return result_document(
        "ue-itps.project-paths.v3",
        {
            "project_root": normalized(project_root),
            "project_descriptor": descriptor_item,
            "project_directories": project_directories,
            "build_and_ide_paths": build_and_ide_paths,
            "cache_and_local_state_paths": cache_and_local_state_paths,
            "unclassified_root_directories": unclassified_root_directories,
        },
        problems,
        responsibility=(
            "Classify project-root path names, locations, and filesystem states."
        ),
        boundaries=[
            "The tool reads only explicit .uproject fields needed to diagnose directory presence.",
            "The tool does not read directory contents or locate Module, Target, Plugin, or asset files.",
            "The tool does not determine source authority, deletion safety, self-containment, or rebuildability.",
            "A missing Source directory is an error only when Modules are declared and no AdditionalRootDirectories may contain them.",
            "Binaries is reported by conventional role without deciding whether it is generated or required.",
            "Only unclassified root directories are reported; unclassified root files are outside this schema.",
        ],
    )
