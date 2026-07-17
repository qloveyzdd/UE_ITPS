from __future__ import annotations

from pathlib import Path
from typing import Any


PATH_ROLE_DESCRIPTIONS = {
    "project-descriptor": "所选项目描述符",
    "source": "UE 项目 C++ Target 与 Module 的约定目录",
    "configuration": "UE 项目配置的约定目录",
    "content": "UE 项目资产与地图的约定目录",
    "plugins": "UE 项目本地插件的约定目录",
    "build": "UE 项目构建、自动化与平台输入的约定目录",
    "platform-extensions": "UE 项目级平台扩展的约定目录",
    "binaries": "项目二进制目录；本报告不判断来源、必要性或删除安全性",
    "build-intermediate": "UBT/UHT 与构建中间状态的约定目录",
    "ide-workspace": "IDE 工作区文件的约定位置",
    "derived-data-cache": "资产派生缓存的约定目录",
    "saved-state": "日志、自动保存与本地运行状态目录",
    "visual-studio-state": "Visual Studio 本地状态目录",
    "jetbrains-state": "JetBrains 本地状态目录",
    "unclassified": "未由路径分类器建模的项目根目录",
}


def markdown_report(manifest: dict[str, Any]) -> str:
    project = manifest["project"]
    engine = manifest["engine"]
    modules = manifest["modules"]
    targets = manifest["targets"]
    plugins = manifest["plugins"]
    profile = manifest["scan_context"]
    lines = [
        "# `.uproject` 入口扫描报告",
        "",
        f"> 生成时间：`{manifest['generated_at']}`；Schema：`{manifest['schema_version']}`",
        "",
        "## 项目与引擎身份",
        "",
        "| 字段 | 结果 |",
        "|---|---|",
        f"| 项目 | `{project['name']}` |",
        f"| `.uproject` | `{project['descriptor']}` |",
        f"| FileVersion | `{project['file_version']}` |",
        f"| EngineAssociation | `{engine['association']}` |",
        f"| Engine 解析状态 | `{engine['status']}` |",
        f"| Engine 解析方法 | `{engine['resolution_method']}` |",
        f"| Engine 根目录 | `{engine['root']}` |",
        f"| Engine 真实版本 | `{engine['version']}` |",
        f"| 版本证据 | `{engine['build_version_file']}` |",
        "",
        "`EngineAssociation` 是关联键，不一定是版本号。真实版本来自所解析 Engine 的 `Build.version`。",
        "",
        (
            "本报告的必要性上下文为 "
            f"`{profile['operation']} / {profile['target_type']} / "
            f"{profile['platform']} / {profile['configuration']}`。"
            "`scan` 只陈述声明与定位证据，不证明运行或打包必需性。"
        ),
        "",
        "## `.uproject` 声明对账",
        "",
        f"- 成功对账的项目模块：{modules['reconciled_module_count']} 个",
        f"- 扫描到 Target：{len(targets['items'])} 个（Target 不由 `.uproject` 声明）",
        f"- 原生项目证据分类：`{targets['classification']}`",
        (
            f"- 插件引用：{plugins['count']} 个；声明启用 "
            f"{plugins['declared_enabled_count']}；声明禁用 "
            f"{plugins['declared_disabled_count']}；已定位 {plugins['resolved_count']}"
        ),
        (
            f"- 当前 Win64/Editor 上启用且适用："
            f"{plugins['declared_enabled_applicable_count']} 个；已定位 "
            f"{plugins['declared_enabled_applicable_resolved_count']} 个"
        ),
        "",
        "### 成功对账的项目模块",
        "",
        "| Module | Type | LoadingPhase | Build.cs | 入口候选 | 状态 |",
        "|---|---|---|---|---:|---|",
    ]
    for module in modules["items"]:
        build_rules = module["build_rules"]
        candidates = build_rules["candidates"]
        build_rules_display = (
            candidates[0]["path"]
            if build_rules["status"] == "resolved"
            else f"{len(candidates)} candidates"
        )
        lines.append(
            f"| `{module['name']}` | `{module['type']}` | "
            f"`{module['loading_phase']}` | "
            f"`{build_rules_display}` | "
            f"{len(module['actual']['module_entrypoint_candidates'])} | "
            f"`{build_rules['status']}` |"
        )

    lines.extend(["", "### Target 文件（扫描发现）", ""])
    for target in targets["items"]:
        lines.append(f"- `{target['name']}` → `{target['path']}`")

    local_plugins = [
        item
        for item in plugins["items"]
        if item["origin"]
        and (
            item["origin"].startswith("project")
            or item["origin"].startswith("additional-project-")
        )
    ]
    lines.extend(["", "### `.uproject` 直接引用的项目本地插件描述符", ""])
    for plugin in local_plugins:
        lines.append(f"- `{plugin['name']}` → `{plugin['descriptor']}`")
    lines.extend(
        [
            "",
            (
                f"其余已定位引用中，{plugins['engine_descriptor_count']} 个来自 "
                "Engine；完整逐项结果保存在机器可读 JSON 中。"
            ),
            "",
            "## 项目根目录事实",
            "",
            f"项目根：`{manifest['structure']['project_root']}`",
            "",
            "| 项目相对路径 | 约定角色 | 实际类型 | 含义 |",
            "|---|---|---|---|",
        ]
    )
    structure = manifest["structure"]
    structure_items = [
        structure["project_descriptor"],
        *structure["project_directories"],
        *structure["build_and_ide_paths"],
        *structure["cache_and_local_state_paths"],
        *structure["unclassified_root_directories"],
    ]
    for item in structure_items:
        lines.append(
            f"| `{item['project_relative_path']}` | `{item['role']}` | "
            f"`{item['actual_type']}` | {PATH_ROLE_DESCRIPTIONS[item['role']]} |"
        )

    lines.extend(
        [
            "",
            "## 当前结构树",
            "",
            "```text",
            f"{project['name']}/",
            f"├─ {Path(project['descriptor']).name}        # 唯一项目入口描述符",
            "├─ Source/                    # UE 约定的 C++ 代码目录",
        ]
    )
    for index, module in enumerate(modules["items"]):
        branch = "│  └─" if index == len(modules["items"]) - 1 else "│  ├─"
        lines.append(f"{branch} {module['name']}/{module['name']}.Build.cs")
    lines.extend(
        [
            "├─ Plugins/                   # UE 约定的项目插件目录",
            "├─ Config/                    # UE 约定的项目配置目录",
            "├─ Content/                   # UE 约定的项目资产目录",
            "├─ Build/                     # UE 约定的项目构建目录",
            "├─ Platforms/                 # UE 约定的平台扩展目录",
            "├─ Binaries/                  # 项目二进制目录（本层不判断来源）",
            "├─ Intermediate/              # 构建中间状态目录",
            "├─ DerivedDataCache/          # 缓存",
            "└─ Saved/                     # 日志与本地运行状态",
            "```",
            "",
            "## 解释边界",
            "",
            f"职责：{manifest['limits']['responsibility']}",
            "",
        ]
    )
    for limit in manifest["limits"]["boundaries"]:
        lines.append(f"- {limit}")

    problems = manifest["validation"]["problems"]
    error_count = sum(1 for item in problems if item["severity"] == "error")
    warning_count = sum(1 for item in problems if item["severity"] == "warning")
    lines.extend(
        [
            "",
            (
                f"验证状态：`{manifest['validation']['status']}`；错误 "
                f"{error_count}；警告 {warning_count}。"
            ),
            "",
        ]
    )
    if problems:
        lines.extend(["### 诊断", ""])
        for problem in problems:
            lines.append(
                f"- `{problem['severity']}` / `{problem['code']}`：{problem['message']}"
            )
        lines.append("")
    return "\n".join(lines)
