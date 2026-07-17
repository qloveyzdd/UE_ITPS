#!/usr/bin/env python3
"""Classify standard project paths without inferring runtime use."""

from pathlib import Path

from ue_project_tools.common import cli_parser, json_text
from ue_project_tools.structure import classify_project_paths


def main() -> int:
    parser = cli_parser(
        "分类项目根目录中的输入、生成物、缓存和本地状态。",
        "Classify project-root inputs, generated data, cache, and local state.",
    )
    parser.add_argument(
        "--project",
        required=True,
        metavar="FILE",
        help=".uproject 文件路径 / Path to the .uproject file",
    )
    args = parser.parse_args()
    project = Path(args.project).resolve()
    result = classify_project_paths(project.parent, project)
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
