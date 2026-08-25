#!/usr/bin/env python3
"""Read direct module dependency names from one Build.cs file."""

from ue_project_tools.common import cli_parser, run_single_path_tool
from ue_project_tools.rule_source import inspect_module_rules


SCHEMA_VERSION = "ue_inspect_module_rules"
RESPONSIBILITY = (
    "Report public, private, and dynamically loaded module dependency names "
    "from one Build.cs file."
)


def main() -> int:
    parser = cli_parser(
        "读取单个 Build.cs 声明的公共、私有和动态加载模块依赖。",
        "Read public, private, and dynamically loaded module dependencies from one Build.cs file.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.add_argument(
        "--rules",
        required=True,
        metavar="FILE",
        help="Build.cs 文件路径 / Path to one Build.cs file",
    )
    return run_single_path_tool(parser, "rules", inspect_module_rules)


if __name__ == "__main__":
    raise SystemExit(main())
