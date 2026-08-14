from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import normalized, read_json, result_document


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
    target_allow_list: list[dict[str, Any]] = []
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
        if declared_enabled:
            enabled.append(name)
        else:
            disabled.append(name)

        if "TargetAllowList" not in raw:
            continue
        targets = raw["TargetAllowList"]
        if not isinstance(targets, list) or any(
            not isinstance(target, str) or not target for target in targets
        ):
            problems.append(
                {
                    "severity": "error",
                    "code": "invalid-plugin-target-allow-list",
                    "descriptor_pointer": f"{pointer}/TargetAllowList",
                    "message": (
                        f"Plugin TargetAllowList at {pointer} must be an array "
                        "of non-empty strings"
                    ),
                }
            )
            continue
        if targets:
            target_allow_list.append(
                {
                    "name": name,
                    "targets": list(targets),
                }
            )

    return (
        {
            "enabled": enabled,
            "disabled": disabled,
            "target_allow_list": target_allow_list,
        },
        problems,
    )


def classify_module_declarations(
    declarations: Any,
) -> tuple[list[str], list[dict[str, Any]]]:
    names: list[str] = []
    problems: list[dict[str, Any]] = []
    first_pointer_by_name: dict[str, str] = {}

    if not isinstance(declarations, list):
        return names, [
            {
                "severity": "error",
                "code": "invalid-module-declarations",
                "message": ".uproject Modules must be an array",
            }
        ]

    for index, raw in enumerate(declarations):
        pointer = f"/Modules/{index}"
        if (
            not isinstance(raw, dict)
            or not isinstance(raw.get("Name"), str)
            or not raw["Name"]
        ):
            problems.append(
                {
                    "severity": "error",
                    "code": "invalid-module-declaration",
                    "descriptor_pointer": pointer,
                    "message": (
                        f"Module declaration at {pointer} requires a non-empty "
                        "string Name"
                    ),
                }
            )
            continue

        name = raw["Name"]
        names.append(name)
        folded_name = name.casefold()
        first_pointer = first_pointer_by_name.get(folded_name)
        if first_pointer:
            problems.append(
                {
                    "severity": "error",
                    "code": "duplicate-module-declaration",
                    "descriptor_pointer": pointer,
                    "descriptor_pointers": [first_pointer, pointer],
                    "message": (
                        f"Module {name} is declared more than once at "
                        f"{first_pointer} and {pointer}"
                    ),
                }
            )
        else:
            first_pointer_by_name[folded_name] = pointer

    return names, problems


def declared_module_file_problems(
    project_file: Path,
    descriptor: dict[str, Any],
) -> list[dict[str, Any]]:
    from .code_inventory import discover_module_build_rules

    declarations = descriptor.get("Modules", [])
    if not isinstance(declarations, list):
        return []

    additional_roots, _ = resolve_internal_directories(
        project_file,
        descriptor,
        "AdditionalRootDirectories",
    )
    search_roots = [
        project_file.parent / "Source",
        project_file.parent / "Platforms",
        *additional_roots,
    ]
    rules_by_module, _ = discover_module_build_rules(search_roots)
    declared_names: dict[str, str] = {}
    for raw in declarations:
        if (
            isinstance(raw, dict)
            and isinstance(raw.get("Name"), str)
            and raw["Name"]
        ):
            declared_names.setdefault(raw["Name"].casefold(), raw["Name"])

    problems: list[dict[str, Any]] = []
    for module_key, name in declared_names.items():
        candidates = rules_by_module.get(module_key, [])
        if len(candidates) == 1:
            continue
        problems.append(
            {
                "severity": "error",
                "code": (
                    "project-module-build-rules-missing"
                    if not candidates
                    else "project-module-build-rules-ambiguous"
                ),
                "module_name": name,
                "candidates": [normalized(path) for path in candidates],
                "message": (
                    f"Declared project module {name} has {len(candidates)} "
                    "matching Build.cs files"
                ),
            }
        )
    return problems


def declared_plugin_file_problems(
    project_file: Path,
    descriptor: dict[str, Any],
) -> list[dict[str, Any]]:
    from .engine import resolve_engine
    from .plugins import descriptor_index

    declarations = descriptor.get("Plugins", [])
    if not isinstance(declarations, list):
        return []

    declared_plugins: dict[str, dict[str, Any]] = {}
    for raw in declarations:
        if (
            isinstance(raw, dict)
            and isinstance(raw.get("Name"), str)
            and raw["Name"]
            and type(raw.get("Enabled")) is bool
        ):
            declared_plugins.setdefault(raw["Name"].casefold(), raw)
    if not declared_plugins:
        return []

    additional_roots, additional_findings = resolve_internal_directories(
        project_file,
        descriptor,
        "AdditionalPluginDirectories",
    )
    problems = directory_finding_problems(
        "AdditionalPluginDirectories",
        additional_findings,
        warn_external=True,
    )
    project_roots = [
        ("project", project_file.parent / "Plugins"),
        ("project-platform", project_file.parent / "Platforms"),
        ("project-mods", project_file.parent / "Mods"),
        *(
            (f"additional-project-{index}", root)
            for index, root in enumerate(additional_roots)
        ),
    ]
    matches = descriptor_index(
        project_roots,
        {raw["Name"] for raw in declared_plugins.values()},
    )
    unresolved = {
        plugin_key
        for plugin_key in declared_plugins
        if not matches.get(plugin_key)
    }

    if unresolved:
        association = descriptor.get("EngineAssociation")
        engine_info = resolve_engine(
            project_file,
            association if isinstance(association, str) else "",
        )
        if engine_info["status"] == "resolved":
            engine_root = Path(str(engine_info["engine_root"]))
            engine_matches = descriptor_index(
                [
                    ("engine", engine_root / "Engine" / "Plugins"),
                    ("engine-platform", engine_root / "Engine" / "Platforms"),
                ],
                {
                    declared_plugins[plugin_key]["Name"]
                    for plugin_key in unresolved
                },
            )
            for plugin_key, candidates in engine_matches.items():
                matches.setdefault(plugin_key, []).extend(candidates)
        else:
            unresolved_plugins = [
                declared_plugins[plugin_key]
                for plugin_key in sorted(unresolved)
            ]
            has_enabled_plugin = any(
                raw["Enabled"] for raw in unresolved_plugins
            )
            problems.append(
                {
                    "severity": "error" if has_enabled_plugin else "info",
                    "code": "plugin-descriptor-search-incomplete",
                    "plugin_names": [raw["Name"] for raw in unresolved_plugins],
                    "message": (
                        "Engine could not be resolved, so declared Plugin "
                        "descriptors could not be checked in Engine roots"
                        + (
                            ""
                            if has_enabled_plugin
                            else "; these Plugins are not enabled, so this "
                            "does not affect the current project"
                        )
                    ),
                }
            )
            return problems

    for plugin_key, raw in declared_plugins.items():
        if matches.get(plugin_key):
            continue
        declared_enabled = raw["Enabled"]
        problems.append(
            {
                "severity": "error" if declared_enabled else "info",
                "code": "declared-plugin-descriptor-missing",
                "plugin_name": raw["Name"],
                "declared_enabled": declared_enabled,
                "message": (
                    f"Declared Plugin {raw['Name']} has no matching .uplugin file"
                    + (
                        ""
                        if declared_enabled
                        else "; the Plugin is not enabled, so this does not "
                        "affect the current project"
                    )
                ),
            }
        )
    return problems


def descriptor_result(project_file: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    project_file = project_file.resolve()
    descriptor = read_json(project_file)
    problems: list[dict[str, Any]] = []
    plugin_declarations, plugin_problems = classify_plugin_declarations(
        descriptor.get("Plugins", [])
    )
    problems.extend(plugin_problems)
    module_declarations = descriptor.get("Modules", [])
    declared_modules, module_problems = classify_module_declarations(
        module_declarations
    )
    problems.extend(module_problems)
    problems.extend(declared_module_file_problems(project_file, descriptor))
    problems.extend(declared_plugin_file_problems(project_file, descriptor))

    result = result_document(
        "ue_read_project_descriptor",
        {
            "declared_modules": declared_modules,
            "plugin_declarations": plugin_declarations,
        },
        problems,
        responsibility=(
            "Read project Module names and direct Plugin declarations, then "
            "validate matching Build.cs and .uplugin files."
        ),
        boundaries=[
            "Only Module names, Plugin enabled states, and explicit non-empty Plugin TargetAllowList values are reported.",
            "Other .uproject fields and Plugin reference fields are outside this tool's responsibility.",
            "Module existence requires one same-named Build.cs; Plugin existence requires at least one same-named .uplugin in supported project or resolved Engine roots.",
            "Filesystem validation does not prove that modules or plugins compile, load, or apply to an effective build profile.",
        ],
    )
    return descriptor, result
