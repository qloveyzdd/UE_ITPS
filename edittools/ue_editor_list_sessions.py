#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.project_context import resolve_project_context
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
        "--project",
        required=True,
        metavar="FILE",
        help="用于解析 Engine 并匹配会话的 .uproject",
    )
    cli.add_argument("--timeout", type=float, default=3.0)
    args = cli.parse_args()
    try:
        context = resolve_project_context(args.project)
        engine_root = context.engine_root
        version = context.engine_version
        sessions = discover_sessions(engine_root, args.timeout)
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    expected = str(context.project_root).replace("\\", "/").rstrip("/").casefold()
    selected_sessions = [
        item
        for item in sessions
        if str(item.get("project_root", ""))
        .replace("\\", "/")
        .rstrip("/")
        .casefold()
        == expected
    ]
    problems = []
    if not selected_sessions:
        problems.append(
            {
                "severity": "warning",
                "code": "no-matching-editor-sessions",
                "message": "No Editor sessions matching the project responded before the timeout.",
            }
        )
    write_json(
        result_document(
            SCHEMA_VERSION,
            {
                "engine_root": str(engine_root).replace("\\", "/"),
                "engine_version": version,
                "sessions": selected_sessions,
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
