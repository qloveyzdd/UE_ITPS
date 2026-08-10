#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.project_context import (
    resolve_project_context,
    validate_engine_root,
)
from ue_editor_tools.remote_client import discover_sessions


SCHEMA_VERSION = "ue_editor_list_sessions"
RESPONSIBILITY = "Discover running Unreal Editor Python Remote Execution sessions."


def main() -> int:
    cli = parser(
        "发现运行中的 Unreal Editor 会话。",
        "Discover running Unreal Editor sessions.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    cli.add_argument(
        "--project", metavar="FILE", help="用于解析 Engine 并匹配会话的 .uproject"
    )
    cli.add_argument(
        "--engine-root", metavar="DIR", help="Engine 安装根目录或项目解析覆盖"
    )
    cli.add_argument("--timeout", type=float, default=3.0)
    args = cli.parse_args()
    if not args.project and not args.engine_root:
        cli.argument_error("one of --project or --engine-root is required")
    try:
        context = (
            resolve_project_context(args.project, args.engine_root)
            if args.project
            else None
        )
        engine_root, version = (
            (context.engine_root, context.engine_version)
            if context
            else validate_engine_root(args.engine_root)
        )
        sessions = discover_sessions(engine_root, args.timeout)
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    matches = []
    if context:
        expected = str(context.project_root).replace("\\", "/").rstrip("/").casefold()
        matches = [
            item
            for item in sessions
            if str(item.get("project_root", ""))
            .replace("\\", "/")
            .rstrip("/")
            .casefold()
            == expected
        ]
    problems = []
    if not sessions:
        problems.append(
            {
                "severity": "warning",
                "code": "no-editor-sessions",
                "message": "No Editor sessions responded before the timeout.",
            }
        )
    write_json(
        result_document(
            SCHEMA_VERSION,
            {
                "engine_root": str(engine_root).replace("\\", "/"),
                "engine_version": version,
                "sessions": sessions,
                "matching_sessions": matches,
            },
            problems,
            responsibility=RESPONSIBILITY,
            boundaries=[
                "Discovery does not execute commands or modify an Editor session."
            ],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
