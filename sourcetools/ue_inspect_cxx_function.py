#!/usr/bin/env python3
"""Inspect C++ function definitions matching one simple or qualified name."""

from pathlib import Path

from ue_project_tools.common import cli_error_document, cli_parser, json_text
from ue_project_tools.source_unit import inspect_source_function


SCHEMA_VERSION = "ue_inspect_cxx_function"
RESPONSIBILITY = (
    "Report external symbols referenced by all definitions matching one function name."
)


def main() -> int:
    parser = cli_parser(
        "读取指定简单名称或完整限定名称的 C++ 函数定义及其引用的外部符号。",
        "Read external symbols referenced by C++ function definitions matching one simple or fully qualified name.",
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
    parser.add_argument(
        "--function",
        required=True,
        metavar="NAME_OR_QUALIFIED_NAME",
        help="简单函数名返回所有同名定义；完整限定名执行精确匹配 / Simple name returns all same-name definitions; fully qualified name matches exactly",
    )
    parser.add_argument(
        "--include-syntax-flow",
        action="store_true",
        help="包含调用与控制语法流 / Include call and control syntax flow",
    )
    parser.add_argument("--engine-root", metavar="PATH", help="显式 Engine 根目录覆盖 / Explicit Engine root override")
    args = parser.parse_args()
    try:
        result = inspect_source_function(
            [Path(value) for value in args.source],
            args.function,
            engine_override=Path(args.engine_root) if args.engine_root else None,
            include_syntax_flow=args.include_syntax_flow,
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
