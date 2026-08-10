from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    OPERATION_CHOICES,
    iter_files,
    normalized,
    result_document,
)
from .descriptor import classify_plugin_declarations
from .dependency_graph import DependencyGraph
from .ue_json import read_ue_json


def descriptor_index(
    roots: list[tuple[str, Path]],
    declared_names: set[str] | None,
) -> dict[str, list[dict[str, str]]]:
    if declared_names == set():
        return {}
    index: dict[str, list[dict[str, str]]] = {}
    for origin, root in roots:
        for path in iter_files(root, ".uplugin", declared_names):
            folded_name = path.stem.casefold()
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
    project_root: Path,
    engine_root: Path | None,
    declarations: Any,
    additional_plugin_roots: list[Path],
    operation: str,
    platform: str,
    target: str,
    additional_plugin_findings: list[dict[str, Any]] | None = None,
    initial_problems: list[dict[str, Any]] | None = None,
    plugin_names: set[str] | None = None,
) -> dict[str, Any]:
    _, declaration_problems = classify_plugin_declarations(declarations)
    problems = [*(initial_problems or []), *declaration_problems]
    valid_declarations = declarations if isinstance(declarations, list) else []
    requested_names = (
        {name.casefold() for name in plugin_names}
        if plugin_names is not None
        else None
    )
    selected_declarations = [
        (declaration_index, raw)
        for declaration_index, raw in enumerate(valid_declarations)
        if requested_names is None
        or (
            isinstance(raw, dict)
            and isinstance(raw.get("Name"), str)
            and raw["Name"].casefold() in requested_names
        )
    ]
    declared_names = {
        raw["Name"].casefold()
        for _, raw in selected_declarations
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
    # One full deterministic walk supports both direct resolution and the
    # transitive descriptor graph. Re-walking Engine/Plugins for every edge
    # would make closure cost grow with dependency count.
    index = descriptor_index(roots, None if declared_names else set())
    results: list[dict[str, Any]] = []
    selected_paths: dict[str, Path] = {}
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

    for declaration_index, raw in selected_declarations:
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
        if selected:
            selected_paths[name.casefold()] = Path(str(selected["path"])).resolve()
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

    dependency_graph = DependencyGraph()
    queue: list[tuple[str, Path]] = sorted(
        (
            (str(item["name"]), selected_paths[str(item["name"]).casefold()])
            for item in results
            if str(item["name"]).casefold() in selected_paths
        ),
        key=lambda item: item[0].casefold(),
    )
    visited_descriptors: set[str] = set()
    while queue:
        plugin_name, descriptor_path = queue.pop(0)
        plugin_key = plugin_name.casefold()
        if plugin_key in visited_descriptors:
            continue
        visited_descriptors.add(plugin_key)
        dependency_graph.add_node(
            plugin_name,
            kind="plugin",
            file=relative_descriptor_path(
                normalized(descriptor_path),
                next(
                    (
                        origin
                        for origin, root in roots
                        if descriptor_path.is_relative_to(root.resolve())
                    ),
                    "project",
                ),
                project_root,
                engine_root,
            ) or normalized(descriptor_path),
        )
        try:
            raw_descriptor, _ = read_ue_json(descriptor_path)
        except (OSError, ValueError) as exc:
            problems.append(
                {
                    "severity": "warning",
                    "code": "plugin-dependency-descriptor-read-failure",
                    "plugin_name": plugin_name,
                    "message": str(exc),
                }
            )
            continue
        dependencies = raw_descriptor.get("Plugins")
        if not isinstance(dependencies, list):
            continue
        for declaration in dependencies:
            if not isinstance(declaration, dict) or not isinstance(declaration.get("Name"), str):
                continue
            dependency_name = declaration["Name"]
            dependency_graph.add_node(dependency_name, kind="plugin", file="")
            dependency_graph.add_edge(
                plugin_name,
                dependency_name,
                kind="plugin_reference",
                file=normalized(descriptor_path),
            )
            matches = sorted(
                index.get(dependency_name.casefold(), []),
                key=lambda item: (rank(str(item["origin"])), str(item["path"]).casefold()),
            )
            if matches:
                queue.append((dependency_name, Path(matches[0]["path"]).resolve()))
        queue.sort(key=lambda item: item[0].casefold())

    def is_project_origin(origin: str | None) -> bool:
        return bool(
            origin
            and (
                origin.startswith("project") or origin.startswith("additional-project-")
            )
        )

    return result_document(
        "ue_resolve_plugins",
        {
            "path_roots": {
                "project": normalized(project_root),
                "engine": normalized(engine_root) if engine_root else None,
            },
            "additional_plugin_directories": additional_plugin_findings or [],
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
            "items": results,
            "dependency_graph": dependency_graph.document(),
        },
        problems,
        responsibility=(
            "Resolve direct .uproject Plugin references for one explicit profile."
        ),
        boundaries=[
            "Direct .uproject plugin references are resolved first; readable .uplugin references are then followed into a static dependency graph.",
            "Transitive graph presence does not imply that every plugin is enabled or applicable for the selected build profile.",
            "Applicability evaluates platform and target filters; configuration and deeper UBT policy remain out of scope.",
            "Resolved descriptors are read only to project declared plugin dependencies; hashes and effective UBT policy are not computed.",
            "Every Plugin item retains all modeled fields.",
            "Descriptor paths are relative to path_roots according to origin.",
        ],
    )
