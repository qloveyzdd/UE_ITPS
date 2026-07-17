#!/usr/bin/env python3
"""Read only the explicit facts declared by one .uproject file."""

from pathlib import Path

from ue_project_tools.common import cli_parser, json_text
from ue_project_tools.descriptor import descriptor_result


def main() -> int:
    parser = cli_parser(
        "只读取一个 .uproject 文件明确声明的事实。",
        "Read only the explicit facts declared by one .uproject file.",
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
