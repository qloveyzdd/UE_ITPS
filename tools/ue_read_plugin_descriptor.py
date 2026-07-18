#!/usr/bin/env python3
"""Read one explicit .uplugin descriptor."""

from pathlib import Path

from ue_project_tools.common import cli_parser, json_text
from ue_project_tools.plugin_descriptor import read_plugin_descriptor


def main() -> int:
    parser = cli_parser(
        "读取单个 .uplugin 描述符。",
        "Read one explicit .uplugin descriptor.",
    )
    parser.add_argument(
        "--plugin",
        required=True,
        metavar="FILE",
        help=".uplugin 文件路径 / Path to one .uplugin file",
    )
    args = parser.parse_args()
    try:
        result = read_plugin_descriptor(Path(args.plugin))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
