#!/usr/bin/env python3
"""Inspect one module's registration and lifecycle entry source."""

from pathlib import Path

from ue_project_tools.common import cli_parser, json_text
from ue_project_tools.module_entry import inspect_module_entry


def main() -> int:
    parser = cli_parser(
        "读取单个模块的注册宏、生命周期和委托操作。",
        "Read registration macros, lifecycle methods, and delegate operations for one module.",
    )
    parser.add_argument(
        "--rules",
        required=True,
        metavar="FILE",
        help="模块 Build.cs 文件路径 / Path to the module Build.cs file",
    )
    args = parser.parse_args()
    try:
        result = inspect_module_entry(Path(args.rules))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
