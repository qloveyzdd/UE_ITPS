#!/usr/bin/env python3
"""Resolve direct .uproject plugin references for one explicit profile."""

from pathlib import Path

from ue_project_tools.common import cli_parser, json_text, read_json
from ue_project_tools.descriptor import resolve_internal_directories
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
        required=True,
        metavar="PATH",
        help="已解析的 Engine 根目录 / Resolved Engine root",
    )
    parser.add_argument(
        "--operation",
        default="scan",
        metavar="NAME",
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
    parser.add_argument(
        "--configuration",
        default="Development",
        metavar="NAME",
        help="构建配置，默认 Development / Build configuration; default: Development",
    )
    args = parser.parse_args()
    project = Path(args.project).resolve()
    try:
        descriptor = read_json(project)
        roots, _ = resolve_internal_directories(
            project.parent, descriptor, "AdditionalPluginDirectories"
        )
        result = resolve_project_plugins(
            project,
            project.parent,
            Path(args.engine_root).resolve(),
            descriptor.get("Plugins", []),
            roots,
            args.operation,
            args.platform,
            args.target_type,
            args.configuration,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
