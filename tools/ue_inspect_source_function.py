#!/usr/bin/env python3
"""Inspect all C++ function definitions matching one selected name."""

from pathlib import Path

from ue_project_tools.common import cli_error_document, cli_parser, json_text
from ue_project_tools.source_unit import inspect_source_function


SCHEMA_VERSION = "ue-itps.source-function.v1"
RESPONSIBILITY = (
    "Report external type and method references for all definitions matching one function name."
)


def main() -> int:
    parser = cli_parser(
        "读取指定名称的全部 C++ 函数定义及其外部类型和方法引用。",
        "Read external type and method references from all C++ function definitions matching one name.",
    )
    parser.add_argument("--source", required=True, metavar="FILE", help="显式选择的 .cpp/.cc 文件 / Explicitly selected .cpp/.cc file")
    parser.add_argument(
        "--function",
        required=True,
        metavar="NAME",
        help="函数名称；返回所有同名定义 / Function name; return all matching definitions",
    )
    parser.add_argument("--engine-root", metavar="PATH", help="显式 Engine 根目录覆盖 / Explicit Engine root override")
    args = parser.parse_args()
    try:
        result = inspect_source_function(
            Path(args.source),
            args.function,
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
