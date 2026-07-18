from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import normalized, result_document
from .ue_json import read_ue_json


KNOWN_PLUGIN_FIELDS = {
    "FileVersion",
    "Version",
    "VersionName",
    "FriendlyName",
    "Description",
    "Category",
    "CreatedBy",
    "CreatedByURL",
    "DocsURL",
    "MarketplaceURL",
    "SupportURL",
    "EngineVersion",
    "EngineVersionRange",
    "EnabledByDefault",
    "CanContainContent",
    "CanContainVerse",
    "IsBetaVersion",
    "IsExperimentalVersion",
    "Installed",
    "ExplicitlyLoaded",
    "EditorCustomVirtualPath",
    "SupportedTargetPlatforms",
    "SupportedPrograms",
    "HasExplicitPlatforms",
    "RequiresBuildPlatform",
    "Sealed",
    "NoCode",
    "Modules",
    "Plugins",
    "LocalizationTargets",
    "PreBuildSteps",
    "PostBuildSteps",
}


def _module_declarations(raw: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    modules: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    if raw is None:
        return modules, problems
    if not isinstance(raw, list):
        return modules, [
            {
                "severity": "error",
                "code": "invalid-plugin-modules",
                "descriptor_pointer": "/Modules",
                "message": ".uplugin Modules must be an array",
            }
        ]
    for index, value in enumerate(raw):
        pointer = f"/Modules/{index}"
        if not isinstance(value, dict) or not isinstance(value.get("Name"), str) or not value["Name"]:
            problems.append(
                {
                    "severity": "error",
                    "code": "invalid-plugin-module",
                    "descriptor_pointer": pointer,
                    "message": "Plugin module requires a non-empty string Name",
                }
            )
            continue
        restrictions = {
            key: item
            for key, item in value.items()
            if key.endswith("AllowList")
            or key.endswith("DenyList")
            or key in {"SupportedTargetPlatforms", "HasExplicitPlatforms"}
        }
        additional = {
            key: item
            for key, item in value.items()
            if key not in {"Name", "Type", "LoadingPhase"} and key not in restrictions
        }
        modules.append(
            {
                "name": value["Name"],
                "type": value.get("Type"),
                "loading_phase": value.get("LoadingPhase", "Default"),
                "descriptor_pointer": pointer,
                "restrictions": restrictions,
                "additional_fields": additional,
            }
        )
    return modules, problems


def _plugin_dependencies(raw: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dependencies: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    if raw is None:
        return dependencies, problems
    if not isinstance(raw, list):
        return dependencies, [
            {
                "severity": "error",
                "code": "invalid-plugin-dependencies",
                "descriptor_pointer": "/Plugins",
                "message": ".uplugin Plugins must be an array",
            }
        ]
    for index, value in enumerate(raw):
        pointer = f"/Plugins/{index}"
        if not isinstance(value, dict) or not isinstance(value.get("Name"), str) or not value["Name"]:
            problems.append(
                {
                    "severity": "error",
                    "code": "invalid-plugin-dependency",
                    "descriptor_pointer": pointer,
                    "message": "Plugin dependency requires a non-empty string Name",
                }
            )
            continue
        if "Enabled" in value and type(value["Enabled"]) is not bool:
            problems.append(
                {
                    "severity": "error",
                    "code": "invalid-plugin-dependency-enabled",
                    "descriptor_pointer": pointer + "/Enabled",
                    "message": "Plugin dependency Enabled must be a boolean when present",
                }
            )
        dependencies.append(
            {
                "name": value["Name"],
                "enabled": value.get("Enabled"),
                "descriptor_pointer": pointer,
                "fields": {key: item for key, item in value.items() if key not in {"Name", "Enabled"}},
            }
        )
    return dependencies, problems


def plugin_descriptor_facts(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolved = path.resolve()
    raw, syntax_extensions, duplicate_fields = read_ue_json(resolved)
    modules, module_problems = _module_declarations(raw.get("Modules"))
    dependencies, dependency_problems = _plugin_dependencies(raw.get("Plugins"))
    problems = [*module_problems, *dependency_problems]
    if type(raw.get("FileVersion")) is not int:
        problems.append(
            {
                "severity": "error",
                "code": "invalid-plugin-file-version",
                "descriptor_pointer": "/FileVersion",
                "message": f"Unsupported .uplugin FileVersion: {raw.get('FileVersion')!r}",
            }
        )
    for field in duplicate_fields:
        problems.append(
            {
                "severity": "warning",
                "code": "duplicate-plugin-descriptor-field",
                "field": field,
                "message": f".uplugin field {field} is repeated; the last value is used for modeled facts",
            }
        )
    fields = {
        key: raw[key]
        for key in raw
        if key in KNOWN_PLUGIN_FIELDS
        and key not in {"FileVersion", "Modules", "Plugins", "LocalizationTargets", "PreBuildSteps", "PostBuildSteps"}
    }
    facts = {
        "descriptor_path": normalized(resolved),
        "file_version": raw.get("FileVersion"),
        "syntax_extensions": syntax_extensions,
        "duplicate_fields": duplicate_fields,
        "fields": fields,
        "modules": modules,
        "plugin_dependencies": dependencies,
        "localization_targets": raw.get("LocalizationTargets", []),
        "build_steps": {
            key: raw[key]
            for key in ("PreBuildSteps", "PostBuildSteps")
            if key in raw
        },
        "descriptor_top_level_fields": sorted(raw),
        "unmodeled_top_level_fields": sorted(set(raw) - KNOWN_PLUGIN_FIELDS),
    }
    return facts, problems


def read_plugin_descriptor(path: Path) -> dict[str, Any]:
    facts, problems = plugin_descriptor_facts(path)
    return result_document(
        "ue-itps.plugin-descriptor.v1",
        facts,
        problems,
        responsibility="Read modeled facts from one explicitly selected .uplugin descriptor.",
        boundaries=[
            "Only the selected descriptor is read.",
            "Plugin dependencies are declarations; their descriptors are not resolved or traversed.",
            "Module declarations are not reconciled with Build.cs or entrypoint source by this tool.",
            "Unmodeled fields are preserved as an inventory and are not declared invalid.",
        ],
    )
