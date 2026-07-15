from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import normalized, read_json, sha256_file


KNOWN_TOP_LEVEL_FIELDS = {
    "FileVersion",
    "ProjectFileVersion",
    "EngineAssociation",
    "Category",
    "Description",
    "Modules",
    "Plugins",
    "AdditionalRootDirectories",
    "AdditionalPluginDirectories",
    "TargetPlatforms",
    "DisableEnginePluginsByDefault",
    "Enterprise",
    "InitSteps",
    "PreBuildSteps",
    "PostBuildSteps",
    "EpicSampleNameHash",
}


def resolve_internal_directories(
    project_root: Path, descriptor: dict[str, Any], field: str
) -> tuple[list[Path], list[dict[str, str]]]:
    roots: list[Path] = []
    findings: list[dict[str, str]] = []
    for index, raw in enumerate(descriptor.get(field, [])):
        if not isinstance(raw, str):
            continue
        candidate = Path(raw).expanduser()
        candidate = (
            candidate if candidate.is_absolute() else project_root / candidate
        ).resolve()
        try:
            candidate.relative_to(project_root.resolve())
            roots.append(candidate)
            status = "internal"
        except ValueError:
            status = "skipped_external"
        findings.append(
            {
                "descriptor_pointer": f"/{field}/{index}",
                "raw": raw,
                "resolved": normalized(candidate),
                "status": status,
            }
        )
    return roots, findings


def descriptor_result(project_file: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    project_file = project_file.resolve()
    descriptor = read_json(project_file)
    file_version = descriptor.get(
        "FileVersion", descriptor.get("ProjectFileVersion")
    )
    problems: list[dict[str, str]] = []
    if not isinstance(file_version, int) or file_version not in {1, 2, 3}:
        problems.append(
            {
                "severity": "error",
                "code": "unsupported-project-file-version",
                "message": f"Unsupported .uproject FileVersion: {file_version!r}",
            }
        )

    _, additional_roots = resolve_internal_directories(
        project_file.parent, descriptor, "AdditionalRootDirectories"
    )
    _, additional_plugins = resolve_internal_directories(
        project_file.parent, descriptor, "AdditionalPluginDirectories"
    )
    result = {
        "schema_version": "ue-itps.project-descriptor.v1",
        "project": {
            "name": project_file.stem,
            "root": normalized(project_file.parent),
            "descriptor": normalized(project_file),
            "descriptor_sha256": sha256_file(project_file),
            "file_version": file_version,
            "engine_association": descriptor.get("EngineAssociation"),
            "category": descriptor.get("Category"),
            "description": descriptor.get("Description"),
        },
        "module_declarations": descriptor.get("Modules", []),
        "plugin_references": descriptor.get("Plugins", []),
        "additional_root_directories": additional_roots,
        "additional_plugin_directories": additional_plugins,
        "descriptor_options": {
            key: descriptor[key]
            for key in (
                "TargetPlatforms",
                "DisableEnginePluginsByDefault",
                "Enterprise",
                "InitSteps",
                "PreBuildSteps",
                "PostBuildSteps",
                "EpicSampleNameHash",
            )
            if key in descriptor
        },
        "top_level_fields": sorted(descriptor.keys()),
        "unmodeled_top_level_fields": {
            key: value
            for key, value in descriptor.items()
            if key not in KNOWN_TOP_LEVEL_FIELDS
        },
        "validation": {
            "status": "error" if problems else "ok",
            "problems": problems,
        },
    }
    return descriptor, result
