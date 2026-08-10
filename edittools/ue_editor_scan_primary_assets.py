#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import READ_ONLY_BOUNDARIES, add_connection_arguments
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.remote_client import EditorSession, editor_identity


SCHEMA_VERSION = "ue_editor_scan_primary_assets"
RESPONSIBILITY = (
    "Read resolved Primary Asset identifiers and types from active Asset Registry tags."
)


def main() -> int:
    cli = parser(
        "读取 Editor 已解析的 Primary Asset 类型和标识。",
        "Read Primary Asset types and resolved identifiers from the Editor.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    add_connection_arguments(cli)
    args = cli.parse_args()
    try:
        with EditorSession(args.node_id, discovery_timeout=args.timeout) as session:
            state = session.invoke("editor_state")
            facts = session.invoke("inspect_primary_assets")
            editor = editor_identity(session.node or {})
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    problems = []
    dirty = list(state.get("dirty_packages", []))
    if dirty:
        problems.append(
            {
                "severity": "warning",
                "code": "dirty-editor-packages",
                "message": f"Editor has {len(dirty)} dirty packages; resolved assets reflect live state.",
            }
        )
    write_json(
        result_document(
            SCHEMA_VERSION,
            {"editor": editor, "editor_state": state, **facts},
            problems,
            responsibility=RESPONSIBILITY,
            boundaries=READ_ONLY_BOUNDARIES
            + [
                "Resolved primary assets reflect active Asset Registry tags, not cook output.",
                "Primary Asset scan rules are read by ue_scan_config_graph from project-local configuration.",
            ],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
