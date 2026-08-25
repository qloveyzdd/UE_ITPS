#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import (
    READ_ONLY_BOUNDARIES,
    add_connection_arguments,
    append_dirty_package_warning,
)
from ue_editor_tools.content_scanner import scan_asset_graph
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.remote_client import EditorSession, editor_identity


SCHEMA_VERSION = "ue_editor_export_asset_graph"
RESPONSIBILITY = (
    "Export project content assets and direct Asset Registry dependency categories."
)


def main() -> int:
    cli = parser(
        "导出项目资产及 Asset Registry 直接依赖。",
        "Export project assets and direct Asset Registry dependencies.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    add_connection_arguments(cli)
    cli.add_argument("--root", action="append", default=[], help="资产根路径，可重复")
    cli.add_argument(
        "--asset", action="append", default=[], help="只保留指定包，可重复"
    )
    cli.add_argument(
        "--class",
        dest="class_name",
        action="append",
        default=[],
        help="只保留指定资产类，可重复",
    )
    cli.add_argument(
        "--dependency-kind",
        action="append",
        choices=[
            "hard_package",
            "soft_package",
            "hard_manage",
            "soft_manage",
            "searchable_name",
        ],
        default=[],
    )
    cli.add_argument("--batch-size", type=int, default=50)
    args = cli.parse_args()
    try:
        with EditorSession(args.node_id, discovery_timeout=args.timeout) as session:
            facts = scan_asset_graph(
                session,
                roots=args.root or None,
                assets=args.asset or None,
                dependency_kinds=args.dependency_kind or None,
                class_names=args.class_name or None,
                batch_size=args.batch_size,
            )
            editor = editor_identity(session.node or {})
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    problems = []
    append_dirty_package_warning(
        problems,
        facts.get("editor_state", {}).get("dirty_packages", []),
        "asset metadata reflects live state.",
    )
    write_json(
        result_document(
            SCHEMA_VERSION,
            {"editor": editor, **facts},
            problems,
            responsibility=RESPONSIBILITY,
            boundaries=READ_ONLY_BOUNDARIES
            + [
                "Dependencies are direct Asset Registry facts and do not prove runtime loading or reachability."
            ],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
