from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import normalized


def path_state(
    project_root: Path, relative: str, category: str, reason: str
) -> dict[str, Any]:
    path = project_root / relative
    return {
        "path": normalized(path),
        "relative_path": relative,
        "category": category,
        "exists": path.exists(),
        "reason": reason,
    }


def classify_project_paths(
    project_root: Path, project_file: Path
) -> dict[str, Any]:
    return {
        "schema_version": "ue-itps.project-paths.v1",
        "descriptor_root": [
            {
                "path": normalized(project_file),
                "relative_path": project_file.name,
                "category": "descriptor-mandated",
                "exists": True,
                "reason": "项目身份，以及顶层 Module/Plugin 声明",
            }
        ],
        "source_inputs": [
            path_state(
                project_root,
                "Source",
                "conditional",
                "项目拥有 C++ Target 或 Module 时需要",
            ),
            path_state(
                project_root,
                "Config",
                "conditional",
                "项目配置层级与运行默认值",
            ),
            path_state(
                project_root, "Content", "conditional", "项目自有资产与地图"
            ),
            path_state(
                project_root,
                "Plugins",
                "conditional",
                "项目本地插件的描述符、代码、配置与资产",
            ),
            path_state(
                project_root,
                "Build",
                "conditional",
                "BuildGraph、自动化、打包、平台与测试输入",
            ),
            path_state(
                project_root,
                "Platforms",
                "conditional",
                "项目级平台扩展与覆盖",
            ),
        ],
        "generated_or_local_state": [
            path_state(
                project_root,
                "Binaries",
                "generated/conditional",
                "源码项目中通常可重建；纯预编译分发中可能是条件输入",
            ),
            path_state(
                project_root,
                "Intermediate",
                "generated",
                "UBT/UHT 与构建中间状态",
            ),
            path_state(
                project_root,
                "DerivedDataCache",
                "cache",
                "资产派生缓存",
            ),
            path_state(
                project_root,
                "Saved",
                "runtime-state",
                "日志、自动保存、Cook 数据与本地运行输出",
            ),
            path_state(
                project_root,
                f"{project_file.stem}.sln",
                "generated",
                "由项目规则生成的 IDE 工作区",
            ),
            path_state(
                project_root, ".vs", "local-state", "Visual Studio 本地状态"
            ),
            path_state(
                project_root, ".idea", "local-state", "JetBrains 本地状态"
            ),
        ],
        "limits": [
            "Path classification does not prove runtime use or minimum-project necessity.",
            "Binaries may be a conditional input for precompiled-only distributions.",
        ],
    }
