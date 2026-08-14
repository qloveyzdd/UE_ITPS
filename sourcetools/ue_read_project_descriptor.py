#!/usr/bin/env python3
"""Read and validate project Module and direct Plugin declarations."""

from pathlib import Path

from ue_project_tools.common import cli_parser, json_text
from ue_project_tools.descriptor import descriptor_result


SCHEMA_VERSION = "ue_read_project_descriptor"
RESPONSIBILITY = (
    "Read project Module names and direct Plugin declarations, then validate "
    "matching Build.cs and .uplugin files."
)


def main() -> int:
    parser = cli_parser(
        "读取一个 .uproject 的工程模块和插件声明，并检查同名 Build.cs 与 .uplugin。",
        "Read Module and Plugin declarations and validate matching descriptor files.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.add_argument(
        "--project",
        required=True,
        metavar="FILE",
        help=".uproject 文件路径 / Path to the .uproject file",
    )
    args = parser.parse_args()
    try:
        _, result = descriptor_result(Path(args.project))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
