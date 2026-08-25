#!/usr/bin/env python3
"""Index TargetRules classes, variables, and functions in one Target.cs file."""

from ue_project_tools.common import cli_parser, run_single_path_tool
from ue_project_tools.rule_source import inspect_target_rules


SCHEMA_VERSION = "ue_inspect_target_rules"
RESPONSIBILITY = (
    "Index TargetRules classes and their member variables and functions from one "
    "Target.cs file."
)


def main() -> int:
    parser = cli_parser(
        "索引单个 Target.cs 中的 TargetRules 类、继承、成员变量和函数。",
        "Index TargetRules classes, inheritance, member variables, and functions from one Target.cs file.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.add_argument(
        "--target",
        required=True,
        metavar="FILE",
        help="Target.cs 文件路径 / Path to one Target.cs file",
    )
    return run_single_path_tool(parser, "target", inspect_target_rules)


if __name__ == "__main__":
    raise SystemExit(main())
