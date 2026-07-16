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

PLUGIN_CORE_FIELDS = {"Name", "Enabled"}


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


def classify_plugin_declarations(
    declarations: Any,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    enabled: list[str] = []
    disabled: list[str] = []
    extended: list[dict[str, Any]] = []
    problems: list[dict[str, str]] = []

    if not isinstance(declarations, list):
        problems.append(
            {
                "severity": "error",
                "code": "invalid-plugin-references",
                "message": ".uproject Plugins must be an array",
            }
        )
        declarations = []

    for index, raw in enumerate(declarations):
        pointer = f"/Plugins/{index}"
        if (
            not isinstance(raw, dict)
            or not isinstance(raw.get("Name"), str)
            or not raw["Name"]
            or type(raw.get("Enabled")) is not bool
        ):
            problems.append(
                {
                    "severity": "error",
                    "code": "invalid-plugin-reference",
                    "descriptor_pointer": pointer,
                    "message": (
                        f"Plugin reference at {pointer} requires a non-empty "
                        "string Name and a boolean Enabled"
                    ),
                }
            )
            continue

        name = raw["Name"]
        declared_enabled = raw["Enabled"]
        additional_fields = sorted(set(raw) - PLUGIN_CORE_FIELDS)
        if additional_fields:
            extended.append(
                {
                    "name": name,
                    "declared_enabled": declared_enabled,
                    "descriptor_pointer": pointer,
                    "additional_fields": additional_fields,
                }
            )
        elif declared_enabled:
            enabled.append(name)
        else:
            disabled.append(name)

    return (
        {
            "count": len(declarations),
            "enabled_count": len(enabled),
            "disabled_count": len(disabled),
            "extended_count": len(extended),
            "invalid_count": len(problems),
            "enabled": enabled,
            "disabled": disabled,
            "extended": extended,
        },
        problems,
    )


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

    plugin_declarations, plugin_problems = classify_plugin_declarations(
        descriptor.get("Plugins", [])
    )
    problems.extend(plugin_problems)

    _, additional_roots = resolve_internal_directories(
        project_file.parent, descriptor, "AdditionalRootDirectories"
    )
    _, additional_plugins = resolve_internal_directories(
        project_file.parent, descriptor, "AdditionalPluginDirectories"
    )
    result = {
        "schema_version": "ue-itps.project-descriptor.v2",
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
        "declared_module_count": (
            len(descriptor["Modules"])
            if isinstance(descriptor.get("Modules", []), list)
            else 0
        ),
        "plugin_declarations": plugin_declarations,
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
