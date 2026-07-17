#!/usr/bin/env python3
"""Resolve direct .uproject plugin references for one explicit profile."""

from pathlib import Path

from ue_project_tools.common import OPERATION_CHOICES, cli_parser, json_text, read_json
from ue_project_tools.descriptor import (
    directory_finding_problems,
    resolve_internal_directories,
)
from ue_project_tools.engine import resolve_engine
from ue_project_tools.plugins import resolve_project_plugins


def main() -> int:
    parser = cli_parser(
        "在一个显式 Profile 下定位 .uproject 的直接 Plugin 引用。",
        "Resolve direct .uproject Plugin references for one explicit profile.",
    )
    parser.add_argument(
        "--project",
        required=True,
        metavar="FILE",
        help=".uproject 文件路径 / Path to the .uproject file",
    )
    parser.add_argument(
        "--engine-root",
        metavar="PATH",
        help="显式 Engine 根目录覆盖 / Explicit Engine root override",
    )
    parser.add_argument(
        "--operation",
        choices=OPERATION_CHOICES,
        default="scan",
        help="操作上下文，默认 scan / Operation context; default: scan",
    )
    parser.add_argument(
        "--platform",
        default="Win64",
        metavar="NAME",
        help="目标平台，默认 Win64 / Target platform; default: Win64",
    )
    parser.add_argument(
        "--target-type",
        default="Editor",
        metavar="NAME",
        help="Target 类型，默认 Editor / Target type; default: Editor",
    )
    args = parser.parse_args()
    project = Path(args.project).resolve()
    try:
        descriptor = read_json(project)
        engine_info = resolve_engine(
            project,
            str(descriptor.get("EngineAssociation") or ""),
            Path(args.engine_root) if args.engine_root else None,
        )
        engine_root = (
            Path(engine_info["engine_root"])
            if engine_info["status"] == "resolved"
            else None
        )
        roots, directory_findings = resolve_internal_directories(
            project.parent, descriptor, "AdditionalPluginDirectories"
        )
        initial_problems = [
            *engine_info["validation"]["problems"],
            *directory_finding_problems(
                "AdditionalPluginDirectories",
                directory_findings,
                warn_external=True,
            ),
        ]
        result = resolve_project_plugins(
            project,
            project.parent,
            engine_root,
            descriptor.get("Plugins", []),
            roots,
            args.operation,
            args.platform,
            args.target_type,
            directory_findings,
            initial_problems,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
