from __future__ import annotations

from pathlib import Path
from typing import Any

from .code_inventory import inspect_modules, inspect_targets
from .common import normalized, result_document, utc_now
from .descriptor import descriptor_result, resolve_internal_directories
from .discovery import select_uproject
from .engine import resolve_engine
from .plugins import resolve_project_plugins
from .structure import classify_project_paths


def build_snapshot(
    *,
    project: str | None = None,
    search_root: str = ".",
    engine_root: str | None = None,
    operation: str = "scan",
    platform: str = "Win64",
    target_type: str = "Editor",
    configuration: str = "Development",
) -> dict[str, Any]:
    project_file, candidates = select_uproject(project, search_root)
    project_root = project_file.parent
    descriptor, descriptor_info = descriptor_result(project_file)

    association = str(descriptor.get("EngineAssociation") or "")
    engine_info = resolve_engine(
        project_file,
        association,
        Path(engine_root) if engine_root else None,
    )
    additional_roots, additional_root_findings = resolve_internal_directories(
        project_root, descriptor, "AdditionalRootDirectories"
    )
    additional_plugin_roots, additional_plugin_findings = resolve_internal_directories(
        project_root, descriptor, "AdditionalPluginDirectories"
    )
    module_info = inspect_modules(
        project_root, descriptor.get("Modules", []), additional_roots
    )
    target_info = inspect_targets(project_root)
    resolved_engine_root = (
        Path(engine_info["engine_root"]) if engine_info.get("engine_root") else None
    )
    plugin_info = resolve_project_plugins(
        project_file,
        project_root,
        resolved_engine_root,
        descriptor.get("Plugins", []),
        additional_plugin_roots,
        operation,
        platform,
        target_type,
        configuration,
    )
    path_info = classify_project_paths(project_root, project_file)

    problems: list[dict[str, str]] = []
    problems.extend(descriptor_info["validation"]["problems"])
    problems.extend(engine_info["validation"]["problems"])
    problems.extend(module_info["validation"]["problems"])
    problems.extend(target_info["validation"]["problems"])
    problems.extend(plugin_info["validation"]["problems"])
    problems.extend(path_info["validation"]["problems"])

    descriptor_project = descriptor_info["project"]
    engine_compat = {
        "association": engine_info["association_raw"],
        "association_raw": engine_info["association_raw"],
        "status": engine_info["status"],
        "resolution_source": engine_info["resolution_method"],
        "resolution_method": engine_info["resolution_method"],
        "resolution_candidates": engine_info["resolution_candidates"],
        "root": engine_info["engine_root"],
        "build_version_file": engine_info["build_version_file"],
        "build_version_sha256": engine_info["build_version_sha256"],
        "version": engine_info["version"],
        "build": engine_info["build"],
    }
    project_compat = {
        **descriptor_project,
        "descriptor_top_level_fields": descriptor_info["descriptor_top_level_fields"],
        "additional_root_directories": additional_root_findings,
        "additional_plugin_directories": additional_plugin_findings,
        "descriptor_options": descriptor_info["descriptor_options"],
        "unmodeled_top_level_fields": descriptor_info["unmodeled_top_level_fields"],
    }
    module_compat = {
        "reconciled_module_count": module_info["reconciled_module_count"],
        "items": module_info["items"],
    }
    target_compat = {
        "items": target_info["items"],
        "classification": target_info["classification"],
    }
    plugin_compat = {
        key: value
        for key, value in plugin_info.items()
        if key not in {"schema_version", "profile", "validation", "limits"}
    }

    return result_document(
        "ue-itps.uproject-structure.v5",
        {
            "generated_at": utc_now(),
            "scan_context": {
                "operation": operation,
                "platform": platform,
                "target_type": target_type,
                "configuration": configuration,
                "requiredness_mode": (
                    "declared-and-located-only"
                    if operation == "scan"
                    else "profile-qualified-partial"
                ),
            },
            "discovery": {
                "search_root": normalized(Path(project or search_root)),
                "candidate_count": len(candidates),
                "candidates": [normalized(path) for path in candidates],
            },
            "project": project_compat,
            "engine": engine_compat,
            "modules": module_compat,
            "targets": target_compat,
            "plugins": plugin_compat,
            "structure": {
                key: value
                for key, value in path_info.items()
                if key not in {"schema_version", "validation", "limits"}
            },
            "component_schemas": {
                "descriptor": descriptor_info["schema_version"],
                "engine": engine_info["schema_version"],
                "modules": module_info["schema_version"],
                "targets": target_info["schema_version"],
                "plugins": plugin_info["schema_version"],
                "paths": path_info["schema_version"],
            },
        },
        problems,
        responsibility=(
            "Compose the focused UE project inspection results into one "
            "versioned entry snapshot."
        ),
        boundaries=[
            "`.uproject` 不声明 Target.cs；Target 来自对 Source 的扫描发现。",
            "`.uproject` 不给出 Build.cs 模块依赖图，也不展开 `.uplugin` 的传递依赖。",
            "目录存在不能证明它在运行时被使用、资产可达，或属于最小项目必需项。",
            "Module 下的 Public/Private 是 UE 约定，不是 `.uproject` 强制路径。",
            "当前只解析 `.uproject` 的显式 Plugin 引用；传递依赖闭包属于下一层扫描。",
            "项目外 Additional* 目录默认只报告 skipped_external，不越界遍历。",
            "Binaries 对源码 Lyra 是生成物；对纯预编译项目可能是条件输入。",
        ],
    )
