#!/usr/bin/env python3
"""Read Modules and Plugins from one explicit .uplugin descriptor."""

from ue_project_tools.common import cli_parser, run_single_path_tool
from ue_project_tools.plugin_descriptor import read_plugin_descriptor


SCHEMA_VERSION = "ue_read_plugin_descriptor"
RESPONSIBILITY = (
    "Read and validate the Modules and Plugins declarations from one "
    "explicitly selected .uplugin descriptor."
)


def main() -> int:
    parser = cli_parser(
        "读取单个 .uplugin 的 Modules 和 Plugins 声明。",
        "Read Modules and Plugins from one explicit .uplugin descriptor.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.add_argument(
        "--plugin",
        required=True,
        metavar="FILE",
        help=".uplugin 文件路径 / Path to one .uplugin file",
    )
    return run_single_path_tool(parser, "plugin", read_plugin_descriptor)


if __name__ == "__main__":
    raise SystemExit(main())
