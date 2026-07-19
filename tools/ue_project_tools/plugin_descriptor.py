from __future__ import annotations

from pathlib import Path
from typing import Any

from .code_inventory import discover_module_build_rules
from .common import normalized, result_document
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
VERSE_SCOPES = {"PublicAPI", "InternalAPI", "PublicUser", "InternalUser"}
LOCALIZATION_LOADING_POLICIES = {
    "Never",
    "Always",
    "Editor",
    "Game",
    "PropertyNames",
    "ToolTips",
}
LOCALIZATION_CONFIG_POLICIES = {"Never", "User", "Auto"}

TOP_LEVEL_STRING_FIELDS = {
    "VersionName",
    "FriendlyName",
    "Description",
    "Category",
    "CategoryPath",
    "CreatedBy",
    "CreatedByURL",
    "DocsURL",
    "MarketplaceURL",
    "SupportURL",
    "EngineVersion",
    "EngineVersionRange",
    "DeprecatedEngineVersion",
    "EditorCustomVirtualPath",
    "VersePath",
}
TOP_LEVEL_BOOL_FIELDS = {
    "EnabledByDefault",
    "CanContainContent",
    "CanContainVerse",
    "IsBetaVersion",
    "IsExperimentalVersion",
    "Installed",
    "ExplicitlyLoaded",
    "HasExplicitPlatforms",
    "RequiresBuildPlatform",
    "Sealed",
    "NoCode",
    "CanBeUsedWithUnrealHeaderTool",
    "bIsPluginExtension",
    "EnableSceneGraph",
    "EnableVerseAssetReflection",
}
TOP_LEVEL_STRING_ARRAY_FIELDS = {
    "SupportedTargetPlatforms",
    "SupportedPrograms",
}

KNOWN_PLUGIN_FIELDS = {
    "FileVersion",
    "Version",
    *TOP_LEVEL_STRING_FIELDS,
    *TOP_LEVEL_BOOL_FIELDS,
    *TOP_LEVEL_STRING_ARRAY_FIELDS,
    "VerseScope",
    "VerseVersion",
    "DisallowedPlugins",
    "Modules",
    "Plugins",
    "LocalizationTargets",
    "PreBuildSteps",
    "PostBuildSteps",
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
    if field not in value:
        return
    item = value[field]
    valid = type(item) is expected_type
    if not valid:
        _type_problem(
            problems,
            code=code,
            pointer=f"{pointer}/{field}",
            field=field,
            expected=expected_type.__name__,
            value=item,
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
    allowed_by_key = {item.casefold(): item for item in allowed}
    if raw.casefold() not in allowed_by_key:
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


def _validate_top_level_fields(
    raw: dict[str, Any], problems: list[dict[str, Any]]
) -> None:
    for field in sorted(TOP_LEVEL_STRING_FIELDS):
        _validate_optional_exact_type(
            raw,
            field,
            str,
            "",
            problems,
            "invalid-plugin-descriptor-field-type",
        )
    for field in sorted(TOP_LEVEL_BOOL_FIELDS):
        _validate_optional_exact_type(
            raw,
            field,
            bool,
            "",
            problems,
            "invalid-plugin-descriptor-field-type",
        )
    for field in sorted(TOP_LEVEL_STRING_ARRAY_FIELDS):
        _validate_string_array(
            raw,
            field,
            "",
            problems,
            "invalid-plugin-descriptor-field-type",
        )
    _validate_optional_exact_type(
        raw,
        "Version",
        int,
        "",
        problems,
        "invalid-plugin-descriptor-field-type",
    )
    _validate_optional_exact_type(
        raw,
        "VerseVersion",
        int,
        "",
        problems,
        "invalid-plugin-descriptor-field-type",
    )
    if type(raw.get("VerseVersion")) is int and raw["VerseVersion"] < 0:
        problems.append(
            {
                "severity": "error",
                "code": "invalid-plugin-descriptor-field-value",
                "descriptor_pointer": "/VerseVersion",
                "field": "VerseVersion",
                "value": raw["VerseVersion"],
                "message": "VerseVersion must be a non-negative integer",
            }
        )
    _validate_enum(
        raw,
        "VerseScope",
        VERSE_SCOPES,
        "",
        problems,
        "invalid-plugin-descriptor-field-type",
        "invalid-plugin-descriptor-enum-value",
    )
    for field in ("PreBuildSteps", "PostBuildSteps"):
        if field not in raw:
            continue
        steps = raw[field]
        if not isinstance(steps, dict):
            _type_problem(
                problems,
                code="invalid-plugin-descriptor-field-type",
                pointer=f"/{field}",
                field=field,
                expected="object of string arrays",
                value=steps,
            )
            continue
        for platform in steps:
            _validate_string_array(
                steps,
                platform,
                f"/{field}",
                problems,
                "invalid-plugin-descriptor-field-type",
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
        additional = {
            key: item
            for key, item in value.items()
            if key not in {"Name", "Type", "LoadingPhase"}
            and key not in restrictions
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


def _reconcile_module_build_rules(
    descriptor_path: Path,
    modules: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    plugin_root = descriptor_path.parent
    source_root = plugin_root / "Source"
    search_roots = [source_root, plugin_root / "Platforms"]
    rules_by_module, discovered_names = discover_module_build_rules(search_roots)
    declaration_counts: dict[str, int] = {}
    for module in modules:
        key = str(module["name"]).casefold()
        declaration_counts[key] = declaration_counts.get(key, 0) + 1

    problems: list[dict[str, Any]] = []
    for module in modules:
        name = str(module["name"])
        key = name.casefold()
        candidates = rules_by_module.get(key, [])
        conventional_path = normalized(
            source_root / name / f"{name}.Build.cs"
        ).casefold()
        candidate_items = [
            {
                "path": normalized(candidate),
                "conventional": normalized(candidate).casefold()
                == conventional_path,
            }
            for candidate in candidates
        ]
        if declaration_counts[key] > 1:
            status = "duplicate-declaration"
        else:
            status = (
                "resolved"
                if len(candidates) == 1
                else ("missing" if not candidates else "ambiguous")
            )
            if status != "resolved":
                problems.append(
                    {
                        "severity": "error",
                        "code": f"plugin-module-build-rules-{status}",
                        "module_name": name,
                        "descriptor_pointer": module["descriptor_pointer"],
                        "candidates": candidate_items,
                        "message": (
                            f"Plugin module {name} has {len(candidates)} "
                            "Build.cs candidates"
                        ),
                    }
                )
        module["build_rules"] = {
            "status": status,
            "candidates": candidate_items,
        }

    declared_keys = set(declaration_counts)
    unlisted = [
        {"module_name": discovered_names[key], "path": normalized(candidate)}
        for key in sorted(
            set(rules_by_module) - declared_keys,
            key=lambda item: discovered_names[item].casefold(),
        )
        for candidate in rules_by_module[key]
    ]
    for item in unlisted:
        problems.append(
            {
                "severity": "error",
                "code": "plugin-module-build-rules-unlisted",
                **item,
                "message": (
                    f"Build.cs for {item['module_name']} is not declared by "
                    "the selected .uplugin"
                ),
            }
        )
    return unlisted, problems


def _localization_target_problems(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return [
            {
                "severity": "error",
                "code": "invalid-plugin-localization-targets",
                "descriptor_pointer": "/LocalizationTargets",
                "message": ".uplugin LocalizationTargets must be an array",
            }
        ]
    problems: list[dict[str, Any]] = []
    for index, value in enumerate(raw):
        pointer = f"/LocalizationTargets/{index}"
        if not isinstance(value, dict):
            _type_problem(
                problems,
                code="invalid-plugin-localization-target-field-type",
                pointer=pointer,
                field="LocalizationTargets",
                expected="object",
                value=value,
            )
            continue
        _validate_optional_exact_type(
            value,
            "Name",
            str,
            pointer,
            problems,
            "invalid-plugin-localization-target-field-type",
        )
        if not isinstance(value.get("Name"), str) or not value["Name"]:
            problems.append(
                {
                    "severity": "error",
                    "code": "invalid-plugin-localization-target",
                    "descriptor_pointer": pointer + "/Name",
                    "message": "Localization target requires a non-empty string Name",
                }
            )
        _validate_enum(
            value,
            "LoadingPolicy",
            LOCALIZATION_LOADING_POLICIES,
            pointer,
            problems,
            "invalid-plugin-localization-target-field-type",
            "invalid-plugin-localization-target-enum-value",
            required=True,
        )
        _validate_enum(
            value,
            "ConfigGenerationPolicy",
            LOCALIZATION_CONFIG_POLICIES,
            pointer,
            problems,
            "invalid-plugin-localization-target-field-type",
            "invalid-plugin-localization-target-enum-value",
        )
    return problems


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
    _validate_top_level_fields(raw, problems)
    problems.extend(_localization_target_problems(raw.get("LocalizationTargets")))
    if type(raw.get("FileVersion")) is not int:
        problems.append(
            {
                "severity": "error",
                "code": "missing-or-invalid-plugin-file-version",
                "descriptor_pointer": "/FileVersion",
                "message": ".uplugin FileVersion must be an integer",
            }
        )
    for duplicate in duplicate_fields:
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
    unlisted_build_rules, build_rule_problems = _reconcile_module_build_rules(
        resolved, modules
    )
    problems.extend(build_rule_problems)
    descriptor_fields = {
        key: raw[key]
        for key in raw
        if key in KNOWN_PLUGIN_FIELDS
        and key
        not in {
            "FileVersion",
            "Modules",
            "Plugins",
            "LocalizationTargets",
            "PreBuildSteps",
            "PostBuildSteps",
        }
    }
    facts = {
        "descriptor_path": normalized(resolved),
        "file_version": raw.get("FileVersion"),
        "descriptor_fields": descriptor_fields,
        "modules": modules,
        "unlisted_build_rules": unlisted_build_rules,
        "plugin_dependencies": dependencies,
    }
    if "LocalizationTargets" in raw:
        facts["localization_targets"] = raw["LocalizationTargets"]
    build_steps = {
        key: raw[key]
        for key in ("PreBuildSteps", "PostBuildSteps")
        if key in raw
    }
    if build_steps:
        facts["build_steps"] = build_steps
    facts["descriptor_top_level_fields"] = sorted(raw)
    facts["unmodeled_top_level_fields"] = sorted(
        set(raw) - KNOWN_PLUGIN_FIELDS
    )
    return facts, problems


def read_plugin_descriptor(path: Path) -> dict[str, Any]:
    facts, problems = plugin_descriptor_facts(path)
    public_facts = {
        key: value
        for key, value in facts.items()
        if key != "unlisted_build_rules"
    }
    return result_document(
        "ue-itps.plugin-descriptor.v2",
        public_facts,
        problems,
        responsibility=(
            "Read and validate modeled facts from one explicitly selected "
            ".uplugin descriptor, including recursive Build.cs reconciliation."
        ),
        boundaries=[
            "Only the selected descriptor and its Source and Platforms directories are read.",
            "Build.cs files are discovered recursively by basename; the conventional Source/<Name>/<Name>.Build.cs path is evidence, not a requirement.",
            "Plugin dependencies are declarations; their descriptors are not resolved or traversed.",
            "Build.cs and C++ bodies are not expanded by this tool.",
            "Enum validation follows the UE 5.6.1 UnrealBuildTool source model.",
            "Unmodeled fields are preserved as an inventory and are not declared invalid.",
        ],
    )
