#!/usr/bin/env python3
"""Inspect external references for all C# methods matching one selected name."""

from pathlib import Path

from ue_project_tools.common import cli_error_document, cli_parser, json_text
from ue_project_tools.cs_source import (
    RESPONSIBILITY,
    SCHEMA_VERSION,
    inspect_cs_function,
)


def main() -> int:
    parser = cli_parser(
        "读取一个 C# 文件中指定名称的全部类成员函数及其外部类型和方法引用。",
        "Read external type and method references from all matching methods in one C# file.",
    )
    parser.add_argument(
        "--source",
        required=True,
        metavar="FILE",
        help="显式选择的 .cs 文件 / Explicitly selected .cs file",
    )
    parser.add_argument(
        "--function",
        required=True,
        metavar="NAME",
        help="函数名称；返回全部同名成员 / Function name; return all matching members",
    )
    args = parser.parse_args()
    try:
        result = inspect_cs_function(
            Path(args.source),
            args.function,
        )
    except (OSError, ValueError) as exc:
        result = cli_error_document(
            SCHEMA_VERSION,
            code="cs-input-failure",
            message=str(exc),
            responsibility=RESPONSIBILITY,
        )
        print(json_text(result), end="")
        return 2
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
