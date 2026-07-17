from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    OPERATION_CHOICES,
    iter_files,
    normalized,
    result_document,
    sha256_file,
)
from .descriptor import classify_plugin_declarations


def plugin_item_defaults() -> dict[str, Any]:
    return {
        "declared_enabled": True,
        "optional": False,
        "applicable_for_context": True,
        "status": "resolved",
        "additional_fields": [],
        "alternate_descriptors": [],
        "filters": {},
    }


def descriptor_index(
    roots: list[tuple[str, Path]],
    declared_names: set[str],
) -> dict[str, list[dict[str, str]]]:
    if not declared_names:
        return {}
    index: dict[str, list[dict[str, str]]] = {}
    for origin, root in roots:
        for path in iter_files(root, ".uplugin"):
            folded_name = path.stem.casefold()
            if folded_name not in declared_names:
                continue
            index.setdefault(folded_name, []).append(
                {
                    "origin": origin,
                    "path": normalized(path),
                }
            )
    return index


def relative_descriptor_path(
    path: str | None,
    origin: str | None,
    project_root: Path,
    engine_root: Path | None,
) -> str | None:
    if not path or not origin:
        return path
    root = (
        engine_root
        if origin in {"engine", "engine-platform"}
        else project_root
    )
    if root is None:
        return path
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path


def sparse_plugin_item(
    item: dict[str, Any],
    defaults: dict[str, Any],
    problem_pointers: set[str],
) -> dict[str, Any]:
    problematic = (
        item["status"] != "resolved"
        or bool(item["alternate_descriptors"])
        or item["descriptor_pointer"] in problem_pointers
    )
    if problematic:
        return item

    sparse = {
        key: item[key]
        for key in ("name", "origin", "descriptor")
    }
    for key, default in defaults.items():
        if item[key] != default:
            sparse[key] = item[key]
    return sparse


def applicable(plugin: dict[str, Any], platform: str, target: str) -> bool:
    platform_allow = plugin.get("PlatformAllowList") or plugin.get(
        "SupportedTargetPlatforms"
    )
    platform_deny = plugin.get("PlatformDenyList") or []
    target_allow = plugin.get("TargetAllowList") or []
    target_deny = plugin.get("TargetDenyList") or []
    if platform_allow and platform not in platform_allow:
        return False
    if platform in platform_deny:
        return False
    if target_allow and target not in target_allow:
        return False
    if target in target_deny:
        return False
    return True


def resolve_project_plugins(
    project_file: Path,
    project_root: Path,
    engine_root: Path | None,
    declarations: Any,
    additional_plugin_roots: list[Path],
    operation: str,
    platform: str,
    target: str,
    additional_plugin_findings: list[dict[str, Any]] | None = None,
    initial_problems: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    defaults = plugin_item_defaults()
    _, declaration_problems = classify_plugin_declarations(declarations)
    problems = [*(initial_problems or []), *declaration_problems]
    valid_declarations = declarations if isinstance(declarations, list) else []
    declared_names = {
        raw["Name"].casefold()
        for raw in valid_declarations
        if isinstance(raw, dict)
        and isinstance(raw.get("Name"), str)
        and raw["Name"]
        and type(raw.get("Enabled")) is bool
    }
    if operation not in OPERATION_CHOICES:
        problems.append(
            {
                "severity": "error",
                "code": "invalid-operation",
                "message": f"Unsupported operation: {operation}",
            }
        )
    roots: list[tuple[str, Path]] = [
        ("project", project_root / "Plugins"),
        ("project-platform", project_root / "Platforms"),
        ("project-mods", project_root / "Mods"),
    ]
    roots.extend(
        (f"additional-project-{index}", root)
        for index, root in enumerate(additional_plugin_roots)
    )
    if engine_root:
        roots.extend(
            [
                ("engine", engine_root / "Engine" / "Plugins"),
                ("engine-platform", engine_root / "Engine" / "Platforms"),
            ]
        )
    index = descriptor_index(roots, declared_names)
    results: list[dict[str, Any]] = []
    origin_rank = {
        "project": 0,
        "project-platform": 1,
        "project-mods": 2,
        "engine": 10,
        "engine-platform": 11,
    }

    def rank(origin: str) -> int:
        if origin.startswith("additional-project-"):
            return 3
        return origin_rank.get(origin, 99)

    for declaration_index, raw in enumerate(valid_declarations):
        if (
            not isinstance(raw, dict)
            or not isinstance(raw.get("Name"), str)
            or not raw["Name"]
            or type(raw.get("Enabled")) is not bool
        ):
            continue
        name = raw["Name"]
        matches = sorted(
            index.get(name.casefold(), []),
            key=lambda item: (
                rank(str(item["origin"])),
                str(item["path"]).casefold(),
            ),
        )
        selected = matches[0] if matches else None
        declared_enabled = raw["Enabled"]
        optional = raw.get("Optional") is True
        applies = applicable(raw, platform, target)
        status = "resolved" if selected else "not-found"
        if declared_enabled and applies and not selected:
            severity = "warning" if optional or operation == "scan" else "error"
            problems.append(
                {
                    "severity": severity,
                    "code": "plugin-not-found",
                    "descriptor_pointer": f"/Plugins/{declaration_index}",
                    "message": (
                        f"Plugin {name} is enabled for {platform}/{target} "
                        "but was not resolved"
                    ),
                }
            )
        results.append(
            {
                "name": name,
                "descriptor_pointer": f"/Plugins/{declaration_index}",
                "declared_enabled": declared_enabled,
                "optional": optional,
                "additional_fields": sorted(set(raw) - {"Name", "Enabled"}),
                "applicable_for_context": applies,
                "status": status,
                "origin": selected["origin"] if selected else None,
                "descriptor": (
                    relative_descriptor_path(
                        str(selected["path"]),
                        str(selected["origin"]),
                        project_root,
                        engine_root,
                    )
                    if selected
                    else None
                ),
                "alternate_descriptors": [
                    {
                        **match,
                        "path": relative_descriptor_path(
                            str(match["path"]),
                            str(match["origin"]),
                            project_root,
                            engine_root,
                        ),
                    }
                    for match in matches[1:]
                ],
                "filters": {
                    key: raw[key]
                    for key in (
                        "PlatformAllowList",
                        "PlatformDenyList",
                        "SupportedTargetPlatforms",
                        "TargetAllowList",
                        "TargetDenyList",
                        "TargetConfigurationAllowList",
                        "TargetConfigurationDenyList",
                        "HasExplicitPlatforms",
                    )
                    if key in raw
                },
            }
        )

    def is_project_origin(origin: str | None) -> bool:
        return bool(
            origin
            and (
                origin.startswith("project") or origin.startswith("additional-project-")
            )
        )

    try:
        project_descriptor_path = (
            project_file.resolve().relative_to(project_root.resolve()).as_posix()
        )
    except ValueError:
        project_descriptor_path = normalized(project_file)
    problem_pointers = {
        str(problem["descriptor_pointer"])
        for problem in problems
        if problem.get("descriptor_pointer")
    }
    for problem in problems:
        problem_pointers.update(
            str(pointer) for pointer in problem.get("descriptor_pointers", [])
        )

    return result_document(
        "ue-itps.project-plugin-references.v4",
        {
            "path_roots": {
                "project": normalized(project_root),
                "engine": normalized(engine_root) if engine_root else None,
            },
            "project_descriptor": {
                "path": project_descriptor_path,
                "sha256": sha256_file(project_file),
            },
            "additional_plugin_directories": additional_plugin_findings or [],
            "item_defaults": defaults,
            "profile": {
                "operation": operation,
                "platform": platform,
                "target_type": target,
            },
            "count": len(results),
            "declared_enabled_count": sum(
                1 for item in results if item["declared_enabled"]
            ),
            "declared_disabled_count": sum(
                1 for item in results if not item["declared_enabled"]
            ),
            "resolved_count": sum(
                1 for item in results if item["status"] == "resolved"
            ),
            "declared_enabled_applicable_count": sum(
                1
                for item in results
                if item["declared_enabled"] and item["applicable_for_context"]
            ),
            "declared_enabled_applicable_resolved_count": sum(
                1
                for item in results
                if item["declared_enabled"]
                and item["applicable_for_context"]
                and item["status"] == "resolved"
            ),
            "project_descriptor_count": sum(
                1 for item in results if is_project_origin(item["origin"])
            ),
            "engine_descriptor_count": sum(
                1 for item in results if item["origin"] in {"engine", "engine-platform"}
            ),
            "items": [
                sparse_plugin_item(item, defaults, problem_pointers)
                for item in results
            ],
        },
        problems,
        responsibility=(
            "Resolve direct .uproject Plugin references for one explicit profile."
        ),
        boundaries=[
            "Only direct .uproject plugin references are resolved.",
            "Effective defaults and transitive .uplugin dependency closure are not computed.",
            "Applicability evaluates platform and target filters; configuration and deeper UBT policy remain out of scope.",
            "Plugin descriptor contents and hashes are not read.",
            "Sparse items inherit omitted fields from item_defaults; problem items retain all modeled fields.",
            "Descriptor paths are relative to path_roots according to origin.",
        ],
    )
