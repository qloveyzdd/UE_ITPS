#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import (
    READ_ONLY_BOUNDARIES,
    add_connection_arguments,
    context_from_args,
)
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.remote_client import EditorSession, editor_identity


SCHEMA_VERSION = "ue_editor_inspect_blueprint"
RESPONSIBILITY = (
    "Read Blueprint graphs, nodes, pins, values, types, and direct pin connections."
)


def main() -> int:
    cli = parser(
        "读取一个 Blueprint 的 Graph、节点和 Pin。",
        "Inspect graphs, nodes, and pins in one Blueprint.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    add_connection_arguments(cli)
    cli.add_argument(
        "--asset", required=True, help="Blueprint 包路径，例如 /Game/BP_Example"
    )
    cli.add_argument("--graph", default="", help="可选 Graph 名称")
    cli.add_argument("--title", default="", help="可选节点标题子串过滤")
    cli.add_argument(
        "--max-nodes", type=int, default=0, help="每个 Graph 最多返回节点数，0 表示不限"
    )
    args = cli.parse_args()
    if args.max_nodes < 0:
        cli.error("--max-nodes cannot be negative")
    try:
        context = context_from_args(args)
        with EditorSession(
            context, node_id=args.node_id, discovery_timeout=args.timeout
        ) as session:
            facts = session.invoke(
                "inspect_blueprint",
                {
                    "asset_path": args.asset,
                    "graph_name": args.graph,
                    "title_filter": args.title,
                    "max_nodes": args.max_nodes,
                },
            )
            editor = editor_identity(context, session.node or {})
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    write_json(
        result_document(
            SCHEMA_VERSION,
            {"editor": editor, **facts},
            [],
            responsibility=RESPONSIBILITY,
            boundaries=READ_ONLY_BOUNDARIES
            + [
                "Node and graph GUIDs are not exposed by the UE 5.8 Python wrapper; object paths are reported instead."
            ],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
