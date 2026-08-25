#!/usr/bin/env python3
"""Pair C++ headers and sources for one explicitly selected Module."""

from ue_project_tools.common import cli_parser, run_single_path_tool
from ue_project_tools.project_cxx_sources import list_module_cxx_sources


SCHEMA_VERSION = "ue_list_module_cxx_sources"
RESPONSIBILITY = (
    "Pair project-local, manually maintained C++ headers and sources for one "
    "explicitly selected Module."
)


def main() -> int:
    parser = cli_parser(
        "对显式选择的单个 Module 中人工维护的 C++ 头文件和源文件进行配对。",
        "Pair manually maintained C++ headers and sources for one explicitly selected Module.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.add_argument(
        "--rules",
        required=True,
        metavar="FILE",
        help="模块 Build.cs 文件路径 / Path to the module Build.cs file",
    )
    return run_single_path_tool(parser, "rules", list_module_cxx_sources)


if __name__ == "__main__":
    raise SystemExit(main())
