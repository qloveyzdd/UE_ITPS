#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import (
    READ_ONLY_BOUNDARIES,
    add_connection_arguments,
    context_from_args,
)
from ue_editor_tools.content_scanner import scan_data_tables
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.remote_client import EditorSession, editor_identity


SCHEMA_VERSION = "ue_editor_scan_data_tables"
RESPONSIBILITY = (
    "Scan DataTable row structures, row identities, and typed path or tag references."
)


def main() -> int:
    cli = parser(
        "扫描 DataTable 行结构和逻辑引用。",
        "Scan DataTable rows and logical references.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    add_connection_arguments(cli)
    cli.add_argument("--root", action="append", default=[], help="资产根路径，可重复")
    cli.add_argument(
        "--asset", action="append", default=[], help="DataTable 包路径，可重复"
    )
    cli.add_argument(
        "--include-values", action="store_true", help="在输出中保留完整行值"
    )
    cli.add_argument("--batch-size", type=int, default=20)
    args = cli.parse_args()
    try:
        context = context_from_args(args)
        with EditorSession(
            context, node_id=args.node_id, discovery_timeout=args.timeout
        ) as session:
            facts = scan_data_tables(
                session,
                roots=args.root or None,
                assets=args.asset or None,
                include_values=args.include_values,
                batch_size=args.batch_size,
            )
            editor = editor_identity(context, session.node or {})
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    problems = list(facts.pop("problems", []))
    dirty = list(facts.get("editor_state", {}).get("dirty_packages", []))
    if dirty:
        problems.append(
            {
                "severity": "warning",
                "code": "dirty-editor-packages",
                "message": f"Editor has {len(dirty)} dirty packages; DataTable rows reflect live state.",
            }
        )
    write_json(
        result_document(
            SCHEMA_VERSION,
            {"editor": editor, **facts},
            problems,
            responsibility=RESPONSIBILITY,
            boundaries=READ_ONLY_BOUNDARIES
            + [
                "References are extracted from exported row values; custom serialization semantics are not inferred."
            ],
        )
    )
    return 1 if any(item.get("severity") == "error" for item in problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
