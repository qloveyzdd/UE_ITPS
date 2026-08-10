from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .project_context import ProjectContext, resolve_project_context


READ_ONLY_BOUNDARIES = [
    "The tool reads the live Editor state and never saves, compiles, or modifies assets.",
    "Runtime Editor facts may differ from committed asset files when packages are dirty.",
    "A successful result is editor evidence, not proof of runtime message delivery.",
]


def add_connection_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        required=True,
        metavar="FILE",
        help=".uproject 文件 / .uproject file",
    )
    parser.add_argument(
        "--engine-root",
        metavar="DIR",
        help="可选 Engine 安装根目录 / Optional Engine installation root",
    )
    parser.add_argument(
        "--node-id", help="精确选择 Editor 节点 / Select one Editor node"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="发现 Editor 的秒数，默认 3 / Editor discovery timeout in seconds",
    )


def context_from_args(args: Any) -> ProjectContext:
    return resolve_project_context(args.project, args.engine_root)


def read_json_object(path_value: str) -> dict[str, Any]:
    import json

    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"Input JSON does not exist: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Input JSON root must be an object: {path}")
    return value
