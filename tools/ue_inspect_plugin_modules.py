#!/usr/bin/env python3
"""Locate module artifacts for one explicit .uplugin descriptor."""

from pathlib import Path

from ue_project_tools.common import cli_parser, json_text
from ue_project_tools.plugin_modules import inspect_plugin_modules


def main() -> int:
    parser = cli_parser(
        "对账单个插件的 Module 声明、Build.cs 和入口候选。",
        "Reconcile Module declarations, Build.cs, and entrypoint candidates for one plugin.",
    )
    parser.add_argument(
        "--plugin",
        required=True,
        metavar="FILE",
        help=".uplugin 文件路径 / Path to one .uplugin file",
    )
    args = parser.parse_args()
    try:
        result = inspect_plugin_modules(Path(args.plugin))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
