#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import READ_ONLY_BOUNDARIES, add_connection_arguments
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.remote_client import EditorSession


SCHEMA_VERSION = "ue_editor_find_tag_referencers"
RESPONSIBILITY = "Find assets whose searchable names reference one Gameplay Tag."


def main() -> int:
    cli = parser(
        "查找引用指定 Gameplay Tag 的资产。",
        "Find assets referencing one Gameplay Tag.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    add_connection_arguments(cli)
    cli.add_argument("--tag", required=True, help="完全限定 Gameplay Tag")
    args = cli.parse_args()
    try:
        with EditorSession(args.node_id, discovery_timeout=args.timeout) as session:
            facts = session.invoke("find_tag_referencers", {"tag": args.tag})
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    write_json(
        result_document(
            SCHEMA_VERSION,
            facts,
            [],
            responsibility=RESPONSIBILITY,
            boundaries=READ_ONLY_BOUNDARIES
            + [
                "A searchable-name reference does not by itself prove publish or subscribe semantics."
            ],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
