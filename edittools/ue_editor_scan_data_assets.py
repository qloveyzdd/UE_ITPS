#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import (
    READ_ONLY_BOUNDARIES,
    add_connection_arguments,
    append_dirty_package_warning,
)
from ue_editor_tools.content_scanner import scan_data_assets
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.remote_client import EditorSession, editor_identity


SCHEMA_VERSION = "ue_editor_scan_data_assets"
RESPONSIBILITY = (
    "Scan explicitly selected DataAsset properties and persistable semantic references."
)


def main() -> int:
    cli = parser(
        "扫描显式选择的 DataAsset 属性和语义引用。",
        "Scan properties and semantic references from explicitly selected DataAssets.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    add_connection_arguments(cli)
    cli.add_argument(
        "--asset", action="append", required=True, help="DataAsset 包或对象路径，可重复"
    )
    cli.add_argument(
        "--property", action="append", required=True, help="读取指定顶层属性，可重复"
    )
    cli.add_argument("--max-depth", type=int, default=3)
    cli.add_argument("--max-items", type=int, default=200)
    cli.add_argument("--batch-size", type=int, default=10)
    args = cli.parse_args()
    try:
        with EditorSession(args.node_id, discovery_timeout=args.timeout) as session:
            facts = scan_data_assets(
                session,
                assets=args.asset,
                property_names=args.property,
                max_depth=args.max_depth,
                max_items=args.max_items,
                batch_size=args.batch_size,
            )
            editor = editor_identity(session.node or {})
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    problems = list(facts.pop("problems", []))
    append_dirty_package_warning(
        problems,
        facts.get("editor_state", {}).get("dirty_packages", []),
        "DataAsset properties reflect live state.",
    )
    write_json(
        result_document(
            SCHEMA_VERSION,
            {"editor": editor, **facts},
            problems,
            responsibility=RESPONSIBILITY,
            boundaries=READ_ONLY_BOUNDARIES
            + [
                "Only explicitly requested DataAssets and top-level properties are read; the tool never performs project-wide discovery.",
                "Selected Editor-visible properties are serialized with explicit depth and collection-size limits.",
                "Referenced UObject values, including instanced subobjects, retain path and class identity but are not recursively expanded.",
                "Property values and references are evidence; domain-specific runtime meaning is not inferred.",
            ],
        )
    )
    return 1 if any(item.get("severity") == "error" for item in problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
