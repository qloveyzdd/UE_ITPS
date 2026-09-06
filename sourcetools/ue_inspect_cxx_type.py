#!/usr/bin/env python3
"""Inspect class or struct definitions matching one exact qualified name."""

from pathlib import Path

from ue_project_tools.common import cli_error_document, cli_parser, json_text
from ue_project_tools.source_unit import inspect_source_type


SCHEMA_VERSION = "ue_inspect_cxx_type"
RESPONSIBILITY = "Inspect one class or struct by its exact qualified name."


def main() -> int:
    parser = cli_parser(
        "按完整限定名解析所给文件中的类或结构体。",
        "Inspect a class or struct by its exact qualified name.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.add_argument(
        "--source",
        required=True,
        nargs="+",
        metavar="FILE",
        help="一至两个显式文件；两个文件必须为同名源文件和头文件 / One or two explicit files; two files must be a same-basename source and header",
    )
    parser.add_argument("--engine-root", metavar="PATH", help="显式 Engine 根目录覆盖 / Explicit Engine root override")
    parser.add_argument("--type", required=True, metavar="QUALIFIED_NAME", help="类型完整限定名 / Exact qualified type name")
    args = parser.parse_args()
    try:
        result = inspect_source_type(
            [Path(value) for value in args.source],
            args.type,
            engine_override=Path(args.engine_root) if args.engine_root else None,
        )
    except (OSError, ValueError) as exc:
        result = cli_error_document(
            SCHEMA_VERSION,
            code="source-input-failure",
            message=str(exc),
            responsibility=RESPONSIBILITY,
        )
        print(json_text(result), end="")
        return 2
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
