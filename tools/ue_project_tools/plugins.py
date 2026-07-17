from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import iter_files, normalized, result_document, sha256_file
from .descriptor import classify_plugin_declarations


def descriptor_index(
    roots: list[tuple[str, Path]],
) -> dict[str, list[dict[str, str | None]]]:
    index: dict[str, list[dict[str, str | None]]] = {}
    for origin, root in roots:
        for path in iter_files(root, ".uplugin"):
            index.setdefault(path.stem.casefold(), []).append(
                {
                    "origin": origin,
                    "path": normalized(path),
                    "sha256": sha256_file(path),
                }
            )
    return index


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
    declarations: list[Any],
    additional_plugin_roots: list[Path],
    operation: str,
    platform: str,
    target: str,
    configuration: str,
) -> dict[str, Any]:
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
    index = descriptor_index(roots)
    results: list[dict[str, Any]] = []
    _, problems = classify_plugin_declarations(declarations)
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

    for declaration_index, raw in enumerate(declarations):
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
                "descriptor": selected["path"] if selected else None,
                "descriptor_sha256": selected["sha256"] if selected else None,
                "alternate_descriptors": matches[1:],
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

    return result_document(
        "ue-itps.project-plugin-references.v3",
        {
            "project_descriptor": {
                "path": normalized(project_file),
                "sha256": sha256_file(project_file),
            },
            "profile": {
                "operation": operation,
                "platform": platform,
                "target_type": target,
                "configuration": configuration,
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
        },
        problems,
        responsibility=(
            "Resolve direct .uproject Plugin references for one explicit profile."
        ),
        boundaries=[
            "Only direct .uproject plugin references are resolved.",
            "Effective defaults and transitive .uplugin dependency closure are not computed.",
            "Applicability currently evaluates platform and target filters; deeper UBT policy remains out of scope.",
        ],
    )
