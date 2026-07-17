from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import normalized, read_json, result_document, sha256_file


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
    project_file: Path, descriptor: dict[str, Any], field: str
) -> tuple[list[Path], list[dict[str, Any]]]:
    """Resolve descriptor paths relative to the directory containing .uproject."""
    project_root = project_file.resolve().parent
    roots: list[Path] = []
    findings: list[dict[str, Any]] = []
    raw_entries = descriptor.get(field, [])
    if not isinstance(raw_entries, list):
        return roots, [
            {
                "descriptor_pointer": f"/{field}",
                "raw": raw_entries,
                "resolved": None,
                "status": "invalid",
            }
        ]

    for index, raw in enumerate(raw_entries):
        pointer = f"/{field}/{index}"
        if not isinstance(raw, str) or not raw:
            findings.append(
                {
                    "descriptor_pointer": pointer,
                    "raw": raw,
                    "resolved": None,
                    "status": "invalid",
                }
            )
            continue
        try:
            candidate = Path(raw).expanduser()
            candidate = (
                candidate if candidate.is_absolute() else project_root / candidate
            ).resolve()
        except (OSError, RuntimeError, ValueError):
            findings.append(
                {
                    "descriptor_pointer": pointer,
                    "raw": raw,
                    "resolved": None,
                    "status": "invalid",
                }
            )
            continue
        try:
            candidate.relative_to(project_root.resolve())
            roots.append(candidate)
            status = "internal"
        except ValueError:
            status = "skipped_external"
        findings.append(
            {
                "descriptor_pointer": pointer,
                "raw": raw,
                "resolved": normalized(candidate),
                "status": status,
            }
        )
    return roots, findings


def directory_finding_problems(
    field: str,
    findings: list[dict[str, Any]],
    *,
    warn_external: bool = False,
) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    for finding in findings:
        status = finding["status"]
        if status == "invalid":
            problems.append(
                {
                    "severity": "error",
                    "code": "invalid-additional-directory",
                    "descriptor_pointer": finding["descriptor_pointer"],
                    "message": (
                        f"{field} entries must be non-empty path strings"
                    ),
                }
            )
        elif status == "skipped_external" and warn_external:
            problems.append(
                {
                    "severity": "warning",
                    "code": "external-additional-plugin-directory-skipped",
                    "descriptor_pointer": finding["descriptor_pointer"],
                    "message": (
                        "External AdditionalPluginDirectories entry was not scanned: "
                        f"{finding['resolved']}"
                    ),
                }
            )
    return problems


def classify_plugin_declarations(
    declarations: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    enabled: list[str] = []
    disabled: list[str] = []
    extended: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    first_pointer_by_name: dict[str, str] = {}

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
        folded_name = name.casefold()
        first_pointer = first_pointer_by_name.get(folded_name)
        if first_pointer:
            problems.append(
                {
                    "severity": "error",
                    "code": "duplicate-plugin-reference",
                    "descriptor_pointer": pointer,
                    "descriptor_pointers": [first_pointer, pointer],
                    "message": (
                        f"Plugin {name} is declared more than once at "
                        f"{first_pointer} and {pointer}"
                    ),
                }
            )
        else:
            first_pointer_by_name[folded_name] = pointer
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
    file_version = descriptor.get("FileVersion", descriptor.get("ProjectFileVersion"))
    problems: list[dict[str, Any]] = []
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
    module_declarations = descriptor.get("Modules", [])
    declared_modules = (
        [
            raw["Name"]
            for raw in module_declarations
            if isinstance(raw, dict) and isinstance(raw.get("Name"), str)
        ]
        if isinstance(module_declarations, list)
        else []
    )

    _, additional_roots = resolve_internal_directories(
        project_file, descriptor, "AdditionalRootDirectories"
    )
    _, additional_plugins = resolve_internal_directories(
        project_file, descriptor, "AdditionalPluginDirectories"
    )
    problems.extend(
        directory_finding_problems("AdditionalRootDirectories", additional_roots)
    )
    problems.extend(
        directory_finding_problems(
            "AdditionalPluginDirectories",
            additional_plugins,
            warn_external=True,
        )
    )
    result = result_document(
        "ue-itps.project-descriptor.v4",
        {
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
            "declared_modules": declared_modules,
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
            "descriptor_top_level_fields": sorted(descriptor.keys()),
            "unmodeled_top_level_fields": {
                key: value
                for key, value in descriptor.items()
                if key not in KNOWN_TOP_LEVEL_FIELDS
            },
        },
        problems,
        responsibility="Read explicit facts declared by one .uproject file.",
        boundaries=[
            "The result does not locate Engine, Module, Target, or Plugin files.",
            "Extended Plugin declarations are indexed, not fully interpreted.",
            "Unmodeled top-level fields are preserved without being judged invalid.",
        ],
    )
    return descriptor, result
