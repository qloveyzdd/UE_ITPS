#!/usr/bin/env python3
"""Classify project-root directory facts without reading project contents."""

from pathlib import Path

from ue_project_tools.common import cli_parser, json_text, read_json
from ue_project_tools.structure import classify_project_paths


def main() -> int:
    parser = cli_parser(
        "读取 .uproject 的显式目录证据，并分类项目根路径状态。",
        "Read explicit .uproject directory evidence and classify project-root paths.",
    )
    parser.add_argument(
        "--project",
        required=True,
        metavar="FILE",
        help=".uproject 文件路径 / Path to the .uproject file",
    )
    args = parser.parse_args()
    project = Path(args.project).resolve()
    try:
        if not project.is_file():
            raise ValueError(f"Expected an existing .uproject file: {project}")
        descriptor = read_json(project)
        result = classify_project_paths(project, descriptor)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
