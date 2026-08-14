#!/usr/bin/env python3
"""Find one Module Build.cs or Plugin .uplugin by name."""

from pathlib import Path

from ue_project_tools.build_descriptor import find_build_descriptor
from ue_project_tools.common import cli_parser, json_text, read_json


SCHEMA_VERSION = "ue_find_build_descriptor"
RESPONSIBILITY = (
    "Find one same-named Module Build.cs or Plugin .uplugin under selected roots."
)


def main() -> int:
    parser = cli_parser(
        "按名称查找一个 Module Build.cs 或 Plugin .uplugin。",
        "Find one Module Build.cs or Plugin .uplugin by name.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.add_argument(
        "--project",
        required=True,
        metavar="FILE",
        help=".uproject 文件路径 / Path to the .uproject file",
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--modulename",
        metavar="NAME",
        help="要查找的 Module 名称 / Module name to find",
    )
    selection.add_argument(
        "--pluginname",
        metavar="NAME",
        help="要查找的 Plugin 名称 / Plugin name to find",
    )
    parser.add_argument(
        "--engine-build-version",
        metavar="FILE",
        help=(
            "显式选择引擎 Build.version 并查找该 Engine / "
            "Explicitly select an Engine Build.version and search that Engine"
        ),
    )
    args = parser.parse_args()

    project = Path(args.project).resolve()
    name = args.modulename if args.modulename is not None else args.pluginname
    kind = "module" if args.modulename is not None else "plugin"
    if not name or not name.strip():
        parser.error("Module or Plugin name must be a non-empty string")

    try:
        if not project.is_file():
            raise ValueError(f"Project descriptor is not a file: {project}")
        if project.suffix.casefold() != ".uproject":
            raise ValueError(f"Expected a .uproject file: {project}")
        read_json(project)
        result = find_build_descriptor(
            project,
            kind=kind,
            name=name.strip(),
            engine_build_version=(
                Path(args.engine_build_version)
                if args.engine_build_version
                else None
            ),
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
