from __future__ import annotations

from pathlib import Path
from typing import Any


def markdown_report(manifest: dict[str, Any]) -> str:
    project = manifest["project"]
    engine = manifest["engine"]
    modules = manifest["modules"]
    targets = manifest["targets"]
    plugins = manifest["plugins"]
    profile = manifest["scan_context"]
    native = manifest["native_project_evidence"]
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
        f"- 扫描到 Target：{targets['count']} 个（Target 不由 `.uproject` 声明）",
        (
            f"- 原生项目证据：根 `Source/*.Target.cs` 为 "
            f"{native['root_target_count']} 个；分类 `{native['classification']}`"
        ),
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
    lines.extend(
        ["", "### `.uproject` 直接引用的项目本地插件描述符", ""]
    )
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
            "## 项目根结构分类",
            "",
            "| 相对路径 | 分类 | 存在 | 含义 |",
            "|---|---|---|---|",
        ]
    )
    for group in ("descriptor_root", "source_inputs", "generated_or_local_state"):
        for item in manifest["structure"][group]:
            lines.append(
                f"| `{item['relative_path']}` | `{item['category']}` | "
                f"{'是' if item['exists'] else '否'} | {item['reason']} |"
            )

    lines.extend(
        [
            "",
            "## 当前结构树",
            "",
            "```text",
            f"{project['name']}/",
            f"├─ {Path(project['descriptor']).name}        # 唯一项目入口描述符",
            "├─ Source/                    # Target 与项目 C++ Module（条件必需）",
        ]
    )
    for index, module in enumerate(modules["items"]):
        branch = "│  └─" if index == len(modules["items"]) - 1 else "│  ├─"
        lines.append(f"{branch} {module['name']}/{module['name']}.Build.cs")
    lines.extend(
        [
            "├─ Plugins/                   # 项目本地插件（存在引用时需要）",
            "├─ Config/                    # 项目配置输入",
            "├─ Content/                   # 项目资产输入",
            "├─ Build/                     # 自动化/测试/打包输入",
            "├─ Platforms/                 # 平台扩展输入",
            "├─ Binaries/                  # 通常为生成物；纯预编译项目例外",
            "├─ Intermediate/              # 生成物",
            "├─ DerivedDataCache/          # 缓存",
            "└─ Saved/                     # 日志与本地运行状态",
            "```",
            "",
            "## 解释边界",
            "",
        ]
    )
    for limit in manifest["limits"]:
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
                f"- `{problem['severity']}` / `{problem['code']}`："
                f"{problem['message']}"
            )
        lines.append("")
    return "\n".join(lines)
