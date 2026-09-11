#!/usr/bin/env python3
"""Pilot export: build a scope once, then use the ordinary source tools."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ue_project_tools.common import cli_parser, json_text
from ue_project_tools.source_scope import MAP_RESPONSIBILITY, SourceScope


def main():
    parser = cli_parser("导出供旧工具定位使用的源码检索地图。", "Export navigation hints for focused source tools.",
                        schema_version="source_navigation_map", responsibility=MAP_RESPONSIBILITY)
    parser.add_argument("--project", required=True, metavar="FILE", help="明确选择的 .uproject / Selected project")
    parser.add_argument("--profile", required=True, metavar="FILE", help="职责与显式文件清单 / Scope profile")
    parser.add_argument("--output", metavar="FILE", help="另存 JSON 地图 / Also save the JSON map")
    parser.add_argument("--engine-root", metavar="PATH", help="显式 Engine 根目录 / Engine root override")
    args = parser.parse_args()
    try:
        scope = SourceScope(Path(args.project), Path(args.profile), Path(args.engine_root) if args.engine_root else None)
        result = scope.navigation_map()
        output = json_text(result)
        if args.output and result["validation"]["status"] != "error":
            Path(args.output).write_text(output, encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(output, end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
