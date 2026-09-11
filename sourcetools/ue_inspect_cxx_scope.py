#!/usr/bin/env python3
"""Navigate explicit source scopes with progressively expanded evidence."""
from pathlib import Path

from ue_project_tools.common import cli_parser, json_text
from ue_project_tools.source_scope import SourceScope, RESPONSIBILITY, validate_scope_query


def main():
    parser = cli_parser("分层检索显式配置的 C++ 源码范围。", "Inspect a configured C++ source scope by level.",
                        schema_version="ue_inspect_cxx_scope", responsibility=RESPONSIBILITY)
    parser.add_argument("--project", required=True, metavar="FILE", help="明确选择的 .uproject / Selected project")
    parser.add_argument("--profile", required=True, metavar="FILE", help="职责与显式文件清单 / Scope profile")
    parser.add_argument("--level", choices=("system", "type", "function", "evidence"), default="system",
                        help="展开层级 / Navigation level")
    parser.add_argument("--select", metavar="ID", help="上一层返回的标识 / ID returned by a preceding query")
    parser.add_argument("--view", choices=("full", "behavior", "structure"), default="behavior",
                        help="检索目的 / Retrieval purpose")
    parser.add_argument("--focus", action="append", default=[], metavar="NAME", help="明确关注的名称，可重复 / Exact focus name; repeatable")
    parser.add_argument("--offset", type=int, default=0, help="分页起点 / Page offset")
    parser.add_argument("--limit", type=int, default=20, help="每页 1 至 100 项 / Page size from 1 to 100")
    parser.add_argument("--engine-root", metavar="PATH", help="显式 Engine 根目录 / Engine root override")
    args = parser.parse_args()
    try:
        validate_scope_query(args.level, args.select, args.view, args.focus, args.offset, args.limit)
        scope = SourceScope(Path(args.project), Path(args.profile), Path(args.engine_root) if args.engine_root else None)
        result = scope.query(level=args.level, select=args.select, view=args.view, focus=args.focus,
                             offset=args.offset, limit=args.limit)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
