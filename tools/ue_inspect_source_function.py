#!/usr/bin/env python3
"""Inspect one explicitly selected C++ function body."""

from pathlib import Path

from ue_project_tools.common import cli_error_document, cli_parser, json_text
from ue_project_tools.source_unit import inspect_source_function


SCHEMA_VERSION = "ue-itps.source-function.v1"
RESPONSIBILITY = (
    "Report operations and control facts for one explicitly selected function definition."
)


def main() -> int:
    parser = cli_parser(
        "读取一个显式选择的 C++ 函数体操作事实。",
        "Read operation facts from one explicitly selected C++ function body.",
    )
    parser.add_argument("--source", required=True, metavar="FILE", help="显式选择的 .cpp/.cc 文件 / Explicitly selected .cpp/.cc file")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--function", metavar="NAME", help="函数名称 / Function name")
    selector.add_argument(
        "--function-id",
        metavar="ID",
        help="稳定函数标识 / Stable function identifier",
    )
    parser.add_argument("--owner", metavar="TYPE", help="可选的所属类型名称 / Optional owning type name")
    parser.add_argument("--parameters", metavar="TEXT", help="重载消歧所需的原始参数文本 / Raw parameter text for overload disambiguation")
    parser.add_argument("--header", metavar="FILE", help="可选的显式配套 .h/.hpp 文件 / Optional explicit companion .h/.hpp file")
    parser.add_argument("--engine-root", metavar="PATH", help="显式 Engine 根目录覆盖 / Explicit Engine root override")
    args = parser.parse_args()
    try:
        result = inspect_source_function(
            Path(args.source),
            args.function,
            function_id=args.function_id,
            owner=args.owner,
            parameters=args.parameters,
            header_file=Path(args.header) if args.header else None,
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
