#!/usr/bin/env python3
"""Discover project Target.cs classes, types, modules, and inheritance."""

from pathlib import Path

from ue_project_tools.code_inventory import inspect_targets
from ue_project_tools.common import cli_parser, json_text


SCHEMA_VERSION = "ue_inspect_targets"
RESPONSIBILITY = (
    "Discover project Target.cs classes and report directly declared or inherited "
    "Target types and extra modules."
)


def main() -> int:
    parser = cli_parser(
        "发现项目 Target.cs 文件和原生 Target 证据。",
        "Discover project Target.cs classes, types, modules, and inheritance.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.add_argument(
        "--project",
        required=True,
        metavar="FILE",
        help=".uproject 文件路径 / Path to the .uproject file",
    )
    args = parser.parse_args()
    project = Path(args.project).resolve()
    if not project.is_file():
        parser.error(f"Expected an existing .uproject file: {project}")
    result = inspect_targets(project.parent)
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
