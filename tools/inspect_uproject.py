#!/usr/bin/env python3
"""Composer for the small UE project inspection tools.

Use the focused ue_*.py commands for individual Codex/MCP capabilities. This
entrypoint only composes their service results and renders the versioned
snapshot/report format.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ue_project_tools.common import cli_parser, json_text, write_text
from ue_project_tools.report import markdown_report
from ue_project_tools.snapshot import build_snapshot


def parse_args() -> argparse.Namespace:
    parser = cli_parser(
        "组合所有聚焦检查结果，并可归档 JSON 与 Markdown 报告。",
        "Compose all focused inspections and optionally archive JSON and Markdown.",
    )
    parser.add_argument(
        "--project",
        metavar="FILE",
        help="显式 .uproject 路径 / Explicit .uproject path",
    )
    parser.add_argument(
        "--search-root",
        default=".",
        metavar="PATH",
        help="未指定项目时的搜索根目录 / Search root when project is omitted",
    )
    parser.add_argument(
        "--engine-root",
        metavar="PATH",
        help="显式 Engine 根目录覆盖 / Explicit Engine root override",
    )
    parser.add_argument(
        "--operation",
        choices=("scan", "open_editor", "build_editor", "run_game", "cook_package"),
        default="scan",
        help="操作上下文 / Operation context (default: scan)",
    )
    parser.add_argument(
        "--platform",
        default="Win64",
        metavar="NAME",
        help="目标平台 / Target platform (default: Win64)",
    )
    parser.add_argument(
        "--target-type",
        default="Editor",
        metavar="NAME",
        help="Target 类型 / Target type (default: Editor)",
    )
    parser.add_argument(
        "--configuration",
        default="Development",
        metavar="NAME",
        help="构建配置 / Build configuration (default: Development)",
    )
    parser.add_argument(
        "--json-out",
        metavar="FILE",
        help="可选 JSON 归档路径 / Optional JSON archive path",
    )
    parser.add_argument(
        "--markdown-out",
        metavar="FILE",
        help="可选 Markdown 报告路径 / Optional Markdown report path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = build_snapshot(
            project=args.project,
            search_root=args.search_root,
            engine_root=args.engine_root,
            operation=args.operation,
            platform=args.platform,
            target_type=args.target_type,
            configuration=args.configuration,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json_out:
        write_text(Path(args.json_out), json_text(manifest))
    if args.markdown_out:
        write_text(Path(args.markdown_out), markdown_report(manifest))

    print(json_text(manifest), end="")
    return 1 if manifest["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
