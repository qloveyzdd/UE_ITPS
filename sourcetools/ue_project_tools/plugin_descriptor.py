from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import result_document
from .ue_json import read_ue_json


MODULE_HOST_TYPES = {
    "Default",
    "Runtime",
    "RuntimeNoCommandlet",
    "RuntimeAndProgram",
    "CookedOnly",
    "UncookedOnly",
    "Developer",
    "DeveloperTool",
    "Editor",
    "EditorNoCommandlet",
    "EditorAndProgram",
    "Program",
    "ServerOnly",
    "ClientOnly",
    "ClientOnlyNoCommandlet",
    "External",
}

MODULE_LOADING_PHASES = {
    "Default",
    "PostDefault",
    "PreDefault",
    "EarliestPossible",
    "PostConfigInit",
    "PostSplashScreen",
    "PreEarlyLoadingScreen",
    "PreLoadingScreen",
    "PostEngineInit",
    "None",
}

TARGET_TYPES = {"Game", "Editor", "Client", "Server", "Program"}
TARGET_CONFIGURATIONS = {
    "Unknown",
    "Debug",
    "DebugGame",
    "Development",
    "Test",
    "Shipping",
}

MODULE_STRING_ARRAY_FIELDS = {
    "PlatformAllowList",
    "PlatformDenyList",
    "WhitelistPlatforms",
    "BlacklistPlatforms",
    "ProgramAllowList",
    "ProgramDenyList",
    "WhitelistPrograms",
    "BlacklistPrograms",
    "GameTargetAllowList",
    "GameTargetDenyList",
    "AdditionalDependencies",
    "SupportedTargetPlatforms",
}
MODULE_ENUM_ARRAY_FIELDS = {
    "TargetAllowList": TARGET_TYPES,
    "TargetDenyList": TARGET_TYPES,
    "WhitelistTargets": TARGET_TYPES,
    "BlacklistTargets": TARGET_TYPES,
    "TargetConfigurationAllowList": TARGET_CONFIGURATIONS,
    "TargetConfigurationDenyList": TARGET_CONFIGURATIONS,
    "WhitelistTargetConfigurations": TARGET_CONFIGURATIONS,
    "BlacklistTargetConfigurations": TARGET_CONFIGURATIONS,
}
PLUGIN_STRING_ARRAY_FIELDS = {
    "PlatformAllowList",
    "PlatformDenyList",
    "WhitelistPlatforms",
    "BlacklistPlatforms",
    "SupportedTargetPlatforms",
}
PLUGIN_ENUM_ARRAY_FIELDS = {
    "TargetAllowList": TARGET_TYPES,
    "TargetDenyList": TARGET_TYPES,
    "WhitelistTargets": TARGET_TYPES,
    "BlacklistTargets": TARGET_TYPES,
    "TargetConfigurationAllowList": TARGET_CONFIGURATIONS,
    "TargetConfigurationDenyList": TARGET_CONFIGURATIONS,
    "WhitelistTargetConfigurations": TARGET_CONFIGURATIONS,
    "BlacklistTargetConfigurations": TARGET_CONFIGURATIONS,
}


def _actual_type(value: Any) -> str:
    if value is None:
        return "null"
    return type(value).__name__


def _type_problem(
    problems: list[dict[str, Any]],
    *,
    code: str,
    pointer: str,
    field: str,
    expected: str,
    value: Any,
) -> None:
    problems.append(
        {
            "severity": "error",
            "code": code,
            "descriptor_pointer": pointer,
            "field": field,
            "expected": expected,
            "actual_type": _actual_type(value),
            "message": f"{field} must be {expected}",
        }
    )


def _validate_optional_exact_type(
    value: dict[str, Any],
    field: str,
    expected_type: type,
    pointer: str,
    problems: list[dict[str, Any]],
    code: str,
) -> None:
    if field in value and type(value[field]) is not expected_type:
        _type_problem(
            problems,
            code=code,
            pointer=f"{pointer}/{field}",
            field=field,
            expected=expected_type.__name__,
            value=value[field],
        )


def _validate_string_array(
    value: dict[str, Any],
    field: str,
    pointer: str,
    problems: list[dict[str, Any]],
    code: str,
) -> bool:
    if field not in value:
        return True
    raw = value[field]
    field_pointer = f"{pointer}/{field}"
    if not isinstance(raw, list):
        _type_problem(
            problems,
            code=code,
            pointer=field_pointer,
            field=field,
            expected="array of strings",
            value=raw,
        )
        return False
    valid = True
    for index, item in enumerate(raw):
        if not isinstance(item, str):
            valid = False
            _type_problem(
                problems,
                code=code,
                pointer=f"{field_pointer}/{index}",
                field=field,
                expected="string",
                value=item,
            )
    return valid


def _validate_enum(
    value: dict[str, Any],
    field: str,
    allowed: set[str],
    pointer: str,
    problems: list[dict[str, Any]],
    type_code: str,
    enum_code: str,
    *,
    required: bool = False,
) -> None:
    field_pointer = f"{pointer}/{field}"
    if field not in value:
        if required:
            _type_problem(
                problems,
                code=type_code,
                pointer=field_pointer,
                field=field,
                expected="string",
                value=None,
            )
        return
    raw = value[field]
    if not isinstance(raw, str):
        _type_problem(
            problems,
            code=type_code,
            pointer=field_pointer,
            field=field,
            expected="string",
            value=raw,
        )
        return
    if raw.casefold() not in {item.casefold() for item in allowed}:
        problems.append(
            {
                "severity": "error",
                "code": enum_code,
                "descriptor_pointer": field_pointer,
                "field": field,
                "value": raw,
                "allowed_values": sorted(allowed),
                "message": f"{field} has an unknown UE 5.6 value: {raw}",
            }
        )


def _validate_enum_array(
    value: dict[str, Any],
    field: str,
    allowed: set[str],
    pointer: str,
    problems: list[dict[str, Any]],
    type_code: str,
    enum_code: str,
) -> None:
    if not _validate_string_array(value, field, pointer, problems, type_code):
        return
    allowed_keys = {item.casefold() for item in allowed}
    for index, item in enumerate(value.get(field, [])):
        if item.casefold() not in allowed_keys:
            problems.append(
                {
                    "severity": "error",
                    "code": enum_code,
                    "descriptor_pointer": f"{pointer}/{field}/{index}",
                    "field": field,
                    "value": item,
                    "allowed_values": sorted(allowed),
                    "message": f"{field} has an unknown UE 5.6 value: {item}",
                }
            )


def _module_declarations(
    raw: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("Name"), str)
            or not value["Name"]
        ):
            problems.append(
                {
                    "severity": "error",
                    "code": "invalid-plugin-module",
                    "descriptor_pointer": pointer,
                    "message": "Plugin module requires a non-empty string Name",
                }
            )
            continue
        _validate_enum(
            value,
            "Type",
            MODULE_HOST_TYPES,
            pointer,
            problems,
            "invalid-plugin-module-field-type",
            "invalid-plugin-module-enum-value",
            required=True,
        )
        _validate_enum(
            value,
            "LoadingPhase",
            MODULE_LOADING_PHASES,
            pointer,
            problems,
            "invalid-plugin-module-field-type",
            "invalid-plugin-module-enum-value",
        )
        for field in sorted(MODULE_STRING_ARRAY_FIELDS):
            _validate_string_array(
                value,
                field,
                pointer,
                problems,
                "invalid-plugin-module-field-type",
            )
        for field, allowed in sorted(MODULE_ENUM_ARRAY_FIELDS.items()):
            _validate_enum_array(
                value,
                field,
                allowed,
                pointer,
                problems,
                "invalid-plugin-module-field-type",
                "invalid-plugin-module-enum-value",
            )
        _validate_optional_exact_type(
            value,
            "HasExplicitPlatforms",
            bool,
            pointer,
            problems,
            "invalid-plugin-module-field-type",
        )
        restrictions = {
            key: item
            for key, item in value.items()
            if key.endswith("AllowList")
            or key.endswith("DenyList")
            or key.startswith("Whitelist")
            or key.startswith("Blacklist")
            or key in {"SupportedTargetPlatforms", "HasExplicitPlatforms"}
        }
        modules.append(
            {
                "name": value["Name"],
                "type": value.get("Type"),
                "loading_phase": value.get("LoadingPhase", "Default"),
                "descriptor_pointer": pointer,
                "restrictions": restrictions,
                "additional_fields": {
                    key: item
                    for key, item in value.items()
                    if key not in {"Name", "Type", "LoadingPhase"}
                    and key not in restrictions
                },
            }
        )
    return modules, problems


def _plugin_dependencies(
    raw: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("Name"), str)
            or not value["Name"]
        ):
            problems.append(
                {
                    "severity": "error",
                    "code": "invalid-plugin-dependency",
                    "descriptor_pointer": pointer,
                    "message": "Plugin dependency requires a non-empty string Name",
                }
            )
            continue
        if "Enabled" not in value or type(value["Enabled"]) is not bool:
            _type_problem(
                problems,
                code="invalid-plugin-dependency-field-type",
                pointer=pointer + "/Enabled",
                field="Enabled",
                expected="bool",
                value=value.get("Enabled"),
            )
        for field in ("Optional", "Activate", "HasExplicitPlatforms"):
            _validate_optional_exact_type(
                value,
                field,
                bool,
                pointer,
                problems,
                "invalid-plugin-dependency-field-type",
            )
        for field in ("Description", "MarketplaceURL"):
            _validate_optional_exact_type(
                value,
                field,
                str,
                pointer,
                problems,
                "invalid-plugin-dependency-field-type",
            )
        _validate_optional_exact_type(
            value,
            "Version",
            int,
            pointer,
            problems,
            "invalid-plugin-dependency-field-type",
        )
        for field in sorted(PLUGIN_STRING_ARRAY_FIELDS):
            _validate_string_array(
                value,
                field,
                pointer,
                problems,
                "invalid-plugin-dependency-field-type",
            )
        for field, allowed in sorted(PLUGIN_ENUM_ARRAY_FIELDS.items()):
            _validate_enum_array(
                value,
                field,
                allowed,
                pointer,
                problems,
                "invalid-plugin-dependency-field-type",
                "invalid-plugin-dependency-enum-value",
            )
        dependencies.append(
            {
                "name": value["Name"],
                "enabled": value.get("Enabled"),
                "descriptor_pointer": pointer,
                "additional_fields": {
                    key: item
                    for key, item in value.items()
                    if key not in {"Name", "Enabled"}
                },
            }
        )
    return dependencies, problems


def _duplicate_declaration_problems(
    items: list[dict[str, Any]],
    *,
    code: str,
    kind: str,
) -> list[dict[str, Any]]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_name.setdefault(str(item["name"]).casefold(), []).append(item)
    return [
        {
            "severity": "error",
            "code": code,
            f"{kind}_name": duplicates[0]["name"],
            "descriptor_pointers": [
                item["descriptor_pointer"] for item in duplicates
            ],
            "message": (
                f"{kind.replace('_', ' ').title()} {duplicates[0]['name']} "
                "is declared more than once"
            ),
        }
        for duplicates in by_name.values()
        if len(duplicates) > 1
    ]


def _validated_plugin_path(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.suffix.casefold() != ".uplugin":
        raise ValueError(f"Expected a .uplugin file: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"Plugin descriptor is not a file: {resolved}")
    return resolved


def plugin_descriptor_facts(
    path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolved = _validated_plugin_path(path)
    raw, duplicate_fields = read_ue_json(resolved)
    modules, module_problems = _module_declarations(raw.get("Modules"))
    dependencies, dependency_problems = _plugin_dependencies(raw.get("Plugins"))
    problems = [*module_problems, *dependency_problems]
    for duplicate in duplicate_fields:
        if duplicate["field"] not in {"Modules", "Plugins"}:
            continue
        problems.append(
            {
                "severity": "error",
                "code": "duplicate-plugin-descriptor-field",
                **duplicate,
                "message": (
                    f".uplugin field {duplicate['field']} is repeated at "
                    f"{duplicate['descriptor_pointer']}; the last value is "
                    "used for modeled facts"
                ),
            }
        )
    problems.extend(
        _duplicate_declaration_problems(
            modules,
            code="plugin-module-declaration-duplicate",
            kind="module",
        )
    )
    problems.extend(
        _duplicate_declaration_problems(
            dependencies,
            code="plugin-dependency-declaration-duplicate",
            kind="plugin_dependency",
        )
    )
    return {
        "modules": modules,
        "plugin_dependencies": dependencies,
    }, problems


def read_plugin_descriptor(path: Path) -> dict[str, Any]:
    facts, problems = plugin_descriptor_facts(path)
    return result_document(
        "ue_read_plugin_descriptor",
        facts,
        problems,
        responsibility=(
            "Read and validate the Modules and Plugins declarations from one "
            "explicitly selected .uplugin descriptor."
        ),
        boundaries=[
            "Only the selected descriptor's Modules and Plugins fields are modeled.",
            "All other top-level descriptor fields are ignored without validation.",
            "Build.cs files, dependency descriptors, and C++ bodies are not read.",
            "Module and Plugin enum validation follows the UE 5.6.1 UnrealBuildTool source model.",
        ],
    )
