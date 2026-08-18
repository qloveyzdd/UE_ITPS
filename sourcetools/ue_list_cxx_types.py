#!/usr/bin/env python3
"""List declaration anchors from one explicitly selected C++ source unit."""

from pathlib import Path

from ue_project_tools.common import cli_error_document, cli_parser, json_text
from ue_project_tools.source_unit import list_source_types


SCHEMA_VERSION = "ue_list_cxx_types"
RESPONSIBILITY = (
    "Index class, struct, enum, interface-candidate, global-variable, "
    "free-function, and class/struct member anchors."
)


def main() -> int:
    parser = cli_parser(
        "列出一个显式选择的 C++ 源码单元中的类型事实。",
        "List declaration anchors from one explicitly selected C++ source unit.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.add_argument("--source", required=True, metavar="FILE", help="显式选择的 .h/.hpp/.cpp/.cc 文件 / Explicitly selected .h/.hpp/.cpp/.cc file")
    parser.add_argument("--engine-root", metavar="PATH", help="显式 Engine 根目录覆盖 / Explicit Engine root override")
    args = parser.parse_args()
    try:
        result = list_source_types(
            Path(args.source),
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
