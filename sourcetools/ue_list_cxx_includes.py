#!/usr/bin/env python3
"""List direct include facts from one or two explicitly selected C++ files."""

from pathlib import Path

from ue_project_tools.common import cli_error_document, cli_parser, json_text
from ue_project_tools.source_unit import list_source_includes


SCHEMA_VERSION = "ue_list_cxx_includes"
RESPONSIBILITY = (
    "Report direct include spellings and deterministic filesystem provenance."
)


def main() -> int:
    parser = cli_parser(
        "列出一至两个显式选择的 C++ 文件中的直接引用事实。",
        "List direct include facts from one or two explicitly selected C++ files.",
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
    args = parser.parse_args()
    try:
        result = list_source_includes(
            [Path(value) for value in args.source],
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
