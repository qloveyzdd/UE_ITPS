#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import (
    READ_ONLY_BOUNDARIES,
    add_connection_arguments,
    append_dirty_package_warning,
)
from ue_editor_tools.content_scanner import find_blueprint_references
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.remote_client import EditorSession, editor_identity


SCHEMA_VERSION = "ue_editor_find_blueprint_references"
RESPONSIBILITY = "Find Blueprint nodes and fields that reference requested C++ or Editor symbols."


def main() -> int:
    cli = parser(
        "查询 Blueprint 对 C++ 或 Editor 符号的引用。",
        "Find Blueprint references to C++ or Editor symbols.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    add_connection_arguments(cli)
    cli.add_argument("--target", action="append", required=True, help="目标符号或对象路径，可重复")
    cli.add_argument("--root", action="append", default=[], help="资产根路径，可重复")
    cli.add_argument("--asset", action="append", default=[], help="Blueprint 包路径，可重复")
    cli.add_argument("--batch-size", type=int, default=20)
    args = cli.parse_args()
    try:
        with EditorSession(args.node_id, discovery_timeout=args.timeout) as session:
            facts = find_blueprint_references(
                session,
                targets=args.target,
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
        "Blueprint references reflect live state.",
    )
    write_json(
        result_document(
            SCHEMA_VERSION,
            {"editor": editor, **facts},
            problems,
            responsibility=RESPONSIBILITY,
            boundaries=READ_ONLY_BOUNDARIES
            + [
                "Matching is based on serialized Blueprint symbol paths and reference values; unresolved dynamic expressions are reported only when their serialized value contains the target.",
            ],
        )
    )
    return 1 if any(item.get("severity") == "error" for item in problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
