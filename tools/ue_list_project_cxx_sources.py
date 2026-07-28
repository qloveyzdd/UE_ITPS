#!/usr/bin/env python3
"""List project-local manually maintained C++ source candidates."""

from pathlib import Path

from ue_project_tools.common import cli_parser, json_text, read_json
from ue_project_tools.project_cxx_sources import list_project_cxx_sources


SCHEMA_VERSION = "ue-itps.project-cxx-sources.v1"
RESPONSIBILITY = (
    "List project-local, manually maintained C++ source candidates grouped "
    "by Module, Plugin, file kind, and visibility."
)


def main() -> int:
    parser = cli_parser(
        "列出项目及项目 Plugin 的人工 C++ 源码，并按 Module 和可见性分组。",
        "List project and project-Plugin C++ source candidates by Module and visibility.",
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
    project = Path(args.project).resolve()
    try:
        if project.suffix.casefold() != ".uproject":
            raise ValueError(f"Expected a .uproject file: {project}")
        descriptor = read_json(project)
        result = list_project_cxx_sources(project, descriptor)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
