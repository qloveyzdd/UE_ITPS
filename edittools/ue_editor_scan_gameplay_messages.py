#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import (
    READ_ONLY_BOUNDARIES,
    add_connection_arguments,
    context_from_args,
)
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.remote_client import EditorSession, editor_identity
from ue_editor_tools.scanner import scan_gameplay_messages


SCHEMA_VERSION = "ue_editor_scan_gameplay_messages"
RESPONSIBILITY = (
    "Scan Blueprint assets for Gameplay Message publish and subscribe operations."
)


def main() -> int:
    cli = parser(
        "扫描 Blueprint 中的 Gameplay Message 发布与订阅关系。",
        "Scan Blueprint Gameplay Message publish and subscribe relations.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    add_connection_arguments(cli)
    cli.add_argument(
        "--root", action="append", default=[], help="限制资产根路径，可重复，例如 /Game"
    )
    cli.add_argument(
        "--asset", action="append", default=[], help="只扫描指定 Blueprint，可重复"
    )
    cli.add_argument(
        "--tag",
        action="append",
        default=[],
        help="额外查询资产引用者的已知消息 Tag，可重复",
    )
    cli.add_argument("--batch-size", type=int, default=20)
    cli.add_argument("--skip-referencers", action="store_true")
    args = cli.parse_args()
    try:
        context = context_from_args(args)
        with EditorSession(
            context, node_id=args.node_id, discovery_timeout=args.timeout
        ) as session:
            facts = scan_gameplay_messages(
                session,
                roots=args.root or None,
                assets=args.asset or None,
                tags=args.tag or None,
                batch_size=args.batch_size,
                include_referencers=not args.skip_referencers,
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
                "message": f"Editor has {len(dirty)} dirty packages; the scan reflects live state.",
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
                "Dynamic channels are preserved as unresolved expressions with direct pin connections."
            ],
        )
    )
    return 1 if any(item.get("severity") == "error" for item in problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
