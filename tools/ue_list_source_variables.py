#!/usr/bin/env python3
"""List variable declaration facts from one selected C++ source unit."""

from pathlib import Path

from ue_project_tools.common import cli_error_document, cli_parser, json_text
from ue_project_tools.source_unit import list_source_variables


SCHEMA_VERSION = "ue-itps.source-variables.v1"
RESPONSIBILITY = (
    "Index conservatively recognized file, member, parameter, and local variable declarations."
)


def main() -> int:
    parser = cli_parser(
        "列出一个显式选择的 C++ 源码单元中的变量声明事实。",
        "List variable declaration facts from one explicitly selected C++ source unit.",
    )
    parser.add_argument("--source", required=True, metavar="FILE", help="显式选择的 .cpp/.cc 文件 / Explicitly selected .cpp/.cc file")
    parser.add_argument("--header", metavar="FILE", help="可选的显式配套 .h/.hpp 文件 / Optional explicit companion .h/.hpp file")
    parser.add_argument("--engine-root", metavar="PATH", help="显式 Engine 根目录覆盖 / Explicit Engine root override")
    args = parser.parse_args()
    try:
        result = list_source_variables(
            Path(args.source),
            Path(args.header) if args.header else None,
            Path(args.engine_root) if args.engine_root else None,
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
