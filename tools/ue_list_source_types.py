#!/usr/bin/env python3
"""List type facts from one explicitly selected C++ source unit."""

from pathlib import Path

from ue_project_tools.common import cli_error_document, cli_parser, json_text
from ue_project_tools.source_unit import list_source_types


SCHEMA_VERSION = "ue-itps.source-types.v1"
RESPONSIBILITY = (
    "Index class, struct, enum, inheritance, member-name, and UE type-macro facts."
)


def main() -> int:
    parser = cli_parser(
        "列出一个显式选择的 C++ 源码单元中的类型事实。",
        "List type facts from one explicitly selected C++ source unit.",
    )
    parser.add_argument("--source", required=True, metavar="FILE", help="显式选择的 .cpp/.cc 文件 / Explicitly selected .cpp/.cc file")
    parser.add_argument("--header", metavar="FILE", help="可选的显式配套 .h/.hpp 文件 / Optional explicit companion .h/.hpp file")
    parser.add_argument("--engine-root", metavar="PATH", help="显式 Engine 根目录覆盖 / Explicit Engine root override")
    args = parser.parse_args()
    try:
        result = list_source_types(
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
