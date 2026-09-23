#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import READ_ONLY_BOUNDARIES, add_connection_arguments, append_dirty_package_warning
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.remote_client import EditorSession, editor_identity


SCHEMA_VERSION = "ue_editor_scan_level_actors"
RESPONSIBILITY = "Read the currently loaded Editor world, Level Blueprint, Actor instances, components, and common instance properties."


def main() -> int:
    cli = parser(
        "读取当前编辑器关卡中的 World、Level Blueprint、Actor 和组件实例。",
        "Inspect the current Editor world, Level Blueprint, Actor and component instances.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    add_connection_arguments(cli)
    cli.add_argument("--actor-class", default="", help="按 Actor 类路径子串过滤")
    cli.add_argument("--max-actors", type=int, default=0, help="最多返回 Actor 数量，0 表示不限")
    cli.add_argument("--no-components", action="store_true", help="不返回组件层级")
    args = cli.parse_args()
    if args.max_actors < 0:
        cli.error("--max-actors cannot be negative")
    try:
        with EditorSession(args.node_id, discovery_timeout=args.timeout) as session:
            facts = session.invoke(
                "scan_level_actors",
                {
                    "actor_class": args.actor_class,
                    "max_actors": args.max_actors,
                    "include_components": not args.no_components,
                },
            )
            editor_state = session.invoke("editor_state")
            editor = editor_identity(session.node or {})
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    problems: list[dict[str, object]] = []
    append_dirty_package_warning(
        problems,
        editor_state.get("dirty_packages", []),
        "level instance facts reflect live state.",
    )
    write_json(
        result_document(
            SCHEMA_VERSION,
            {"editor": editor, "editor_state": editor_state, **facts},
            problems,
            responsibility=RESPONSIBILITY,
            boundaries=READ_ONLY_BOUNDARIES
            + [
                "This command reads the currently loaded Editor world; it does not load or save maps.",
                "Instance property coverage is limited to properties exposed by the current Unreal Python wrapper.",
            ],
        )
    )
    return 1 if any(item.get("severity") == "error" for item in problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
