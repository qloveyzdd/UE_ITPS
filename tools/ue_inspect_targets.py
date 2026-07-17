#!/usr/bin/env python3
"""Discover project Target.cs files and native-project evidence."""

from pathlib import Path

from ue_project_tools.code_inventory import inspect_targets
from ue_project_tools.common import cli_parser, json_text


def main() -> int:
    parser = cli_parser(
        "发现项目 Target.cs 文件和原生 Target 证据。",
        "Discover project Target.cs files and native Target evidence.",
    )
    parser.add_argument(
        "--project",
        required=True,
        metavar="FILE",
        help=".uproject 文件路径 / Path to the .uproject file",
    )
    args = parser.parse_args()
    project = Path(args.project).resolve()
    result = inspect_targets(project.parent)
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
