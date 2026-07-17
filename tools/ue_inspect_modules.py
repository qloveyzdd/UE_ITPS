#!/usr/bin/env python3
"""Locate Build.cs and entrypoint evidence for declared project modules."""

from pathlib import Path

from ue_project_tools.code_inventory import inspect_modules
from ue_project_tools.common import cli_parser, json_text, read_json
from ue_project_tools.descriptor import resolve_internal_directories


def main() -> int:
    parser = cli_parser(
        "对账 .uproject Module 声明、Build.cs 和模块入口证据。",
        "Reconcile .uproject Modules with Build.cs and entrypoint evidence.",
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
        descriptor = read_json(project)
        roots, _ = resolve_internal_directories(
            project.parent, descriptor, "AdditionalRootDirectories"
        )
        result = inspect_modules(project.parent, descriptor.get("Modules", []), roots)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
