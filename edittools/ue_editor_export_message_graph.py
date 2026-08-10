#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import read_json_object
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.graph_export import export_message_graph


SCHEMA_VERSION = "ue_editor_export_message_graph"
RESPONSIBILITY = "Transform one Gameplay Message Editor scan into deterministic graph nodes, relations, and evidence."


def main() -> int:
    cli = parser(
        "把 Gameplay Message 扫描结果转换成知识图谱事实。",
        "Export a Gameplay Message scan as graph facts.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    cli.add_argument(
        "--input",
        required=True,
        metavar="JSON",
        help="ue_editor_scan_gameplay_messages 输出文件",
    )
    cli.add_argument(
        "--allow-dirty", action="store_true", help="允许来自含未保存资产的 Editor 扫描"
    )
    args = cli.parse_args()
    try:
        scan = read_json_object(args.input)
        if scan.get("schema_version") != "ue_editor_scan_gameplay_messages":
            raise ValueError("Input is not a ue_editor_scan_gameplay_messages document")
        dirty = list(scan.get("editor_state", {}).get("dirty_packages", []))
        problems = []
        if dirty and not args.allow_dirty:
            problems.append(
                {
                    "severity": "error",
                    "code": "dirty-editor-packages",
                    "message": "Graph export refused because the source scan contains dirty Editor packages.",
                }
            )
            graph = {
                "project": str(scan.get("editor", {}).get("project", "")),
                "nodes": [],
                "relations": [],
                "evidence": [],
                "counts": {"nodes": 0, "relations": 0, "evidence": 0},
            }
        else:
            graph = export_message_graph(scan)
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    write_json(
        result_document(
            SCHEMA_VERSION,
            {"source_schema": scan["schema_version"], "graph": graph},
            problems,
            responsibility=RESPONSIBILITY,
            boundaries=[
                "The exporter transforms Editor evidence and does not rescan or modify the project.",
                "Unresolved dynamic channel expressions remain unresolved graph targets.",
            ],
        )
    )
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
