#!/usr/bin/env python3
"""Inspect declared TargetRules mutations in one Target.cs file."""

from pathlib import Path

from ue_project_tools.common import cli_parser, json_text
from ue_project_tools.rule_source import inspect_target_rules


def main() -> int:
    parser = cli_parser(
        "读取单个 Target.cs 声明的 TargetRules 设置变更和引用。",
        "Read declared TargetRules mutations and references from one Target.cs file.",
    )
    parser.add_argument(
        "--target",
        required=True,
        metavar="FILE",
        help="Target.cs 文件路径 / Path to one Target.cs file",
    )
    args = parser.parse_args()
    try:
        result = inspect_target_rules(Path(args.target))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
