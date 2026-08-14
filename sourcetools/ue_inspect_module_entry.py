#!/usr/bin/env python3
"""Locate one module's registration source and matching header."""

from pathlib import Path

from ue_project_tools.common import cli_parser, json_text
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
    parser.add_argument(
        "--compile-database",
        metavar="FILE_OR_DIRECTORY",
        help="Clang compile_commands.json file or containing directory",
    )
    args = parser.parse_args()
    try:
        result = inspect_module_entry(
            Path(args.rules),
            Path(args.compile_database) if args.compile_database else None,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
