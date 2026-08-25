#!/usr/bin/env python3
"""Locate one module's registration source and matching header."""

from ue_project_tools.common import cli_parser, run_single_path_tool
from ue_project_tools.module_entry import inspect_module_entry


SCHEMA_VERSION = "ue_inspect_module_entry"
RESPONSIBILITY = (
    "Locate one module's .cpp registration entry and its uniquely matched "
    "same-named .h file."
)


def main() -> int:
    parser = cli_parser(
        "定位单个模块的注册入口 .cpp 及其同名 .h 文件。",
        "Locate one module registration .cpp and its same-named .h file.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.add_argument(
        "--rules",
        required=True,
        metavar="FILE",
        help="模块 Build.cs 文件路径 / Path to the module Build.cs file",
    )
    return run_single_path_tool(parser, "rules", inspect_module_entry)


if __name__ == "__main__":
    raise SystemExit(main())
