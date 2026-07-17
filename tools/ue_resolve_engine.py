#!/usr/bin/env python3
"""Resolve EngineAssociation to one Engine root and actual Build.version."""

from pathlib import Path

from ue_project_tools.common import cli_parser, json_text, read_json
from ue_project_tools.engine import resolve_engine


def main() -> int:
    parser = cli_parser(
        "将 EngineAssociation 解析到唯一 Engine，并读取 Build.version。",
        "Resolve EngineAssociation to one Engine and read Build.version.",
    )
    parser.add_argument(
        "--project",
        required=True,
        metavar="FILE",
        help=".uproject 文件路径 / Path to the .uproject file",
    )
    parser.add_argument(
        "--engine-root",
        metavar="PATH",
        help="显式 Engine 根目录覆盖 / Explicit Engine root override",
    )
    args = parser.parse_args()
    project = Path(args.project).resolve()
    try:
        descriptor = read_json(project)
        result = resolve_engine(
            project,
            str(descriptor.get("EngineAssociation") or ""),
            Path(args.engine_root) if args.engine_root else None,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
