#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import (
    READ_ONLY_BOUNDARIES,
    add_connection_arguments,
    append_dirty_package_warning,
)
from ue_editor_tools.content_scanner import scan_blueprint_structures
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.remote_client import EditorSession, editor_identity


SCHEMA_VERSION = "ue_editor_scan_blueprint_structure"
RESPONSIBILITY = "Scan Blueprint type structure, graphs, variables, interfaces, and direct references."


def main() -> int:
    cli = parser(
        "扫描 Blueprint 的逻辑结构与直接引用。",
        "Scan Blueprint logical structure and direct references.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    add_connection_arguments(cli)
    cli.add_argument("--root", action="append", default=[], help="资产根路径，可重复")
    cli.add_argument(
        "--asset", action="append", default=[], help="Blueprint 包路径，可重复"
    )
    cli.add_argument("--batch-size", type=int, default=20)
    args = cli.parse_args()
    try:
        with EditorSession(args.node_id, discovery_timeout=args.timeout) as session:
            facts = scan_blueprint_structures(
                session,
                roots=args.root or None,
                assets=args.asset or None,
                batch_size=args.batch_size,
            )
            editor = editor_identity(session.node or {})
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    problems = list(facts.pop("problems", []))
    append_dirty_package_warning(
        problems,
        facts.get("editor_state", {}).get("dirty_packages", []),
        "Blueprint structure reflects live state.",
    )
    write_json(
        result_document(
            SCHEMA_VERSION,
            {"editor": editor, **facts},
            problems,
            responsibility=RESPONSIBILITY,
            boundaries=READ_ONLY_BOUNDARIES
            + [
                "Node references are direct serialized values; arbitrary Blueprint data flow is not inferred."
            ],
        )
    )
    return 1 if any(item.get("severity") == "error" for item in problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
