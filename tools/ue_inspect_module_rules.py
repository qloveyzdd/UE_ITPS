#!/usr/bin/env python3
"""Inspect declared setting mutations and references in one Build.cs file."""

from pathlib import Path

from ue_project_tools.common import cli_parser, json_text
from ue_project_tools.rule_source import inspect_module_rules


def main() -> int:
    parser = cli_parser(
        "提取单个 Build.cs 声明的设置变更和引用关系。",
        "Extract declared setting mutations and references from one Build.cs file.",
    )
    parser.add_argument(
        "--rules",
        required=True,
        metavar="FILE",
        help="Build.cs 文件路径 / Path to one Build.cs file",
    )
    args = parser.parse_args()
    try:
        result = inspect_module_rules(Path(args.rules))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
