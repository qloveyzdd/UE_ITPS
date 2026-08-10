#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import READ_ONLY_BOUNDARIES, add_connection_arguments
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.remote_client import EditorSession


SCHEMA_VERSION = "ue_editor_list_gameplay_tags"
RESPONSIBILITY = "List Gameplay Tags registered in one running Unreal Editor project."


def main() -> int:
    cli = parser(
        "列出运行中 UE 项目注册的 Gameplay Tag。",
        "List registered Gameplay Tags in a running UE project.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    add_connection_arguments(cli)
    cli.add_argument("--parent-tag", default="", help="只列出指定父标签的后代")
    cli.add_argument(
        "--include-info", action="store_true", help="读取注释、来源和直接子标签"
    )
    args = cli.parse_args()
    try:
        with EditorSession(args.node_id, discovery_timeout=args.timeout) as session:
            facts = session.invoke(
                "list_gameplay_tags",
                {"parent_tag": args.parent_tag, "include_info": args.include_info},
            )
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    write_json(
        result_document(
            SCHEMA_VERSION,
            facts,
            [],
            responsibility=RESPONSIBILITY,
            boundaries=READ_ONLY_BOUNDARIES,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
