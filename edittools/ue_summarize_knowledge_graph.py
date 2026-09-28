#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from ue_editor_tools.cli import read_json_object
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.graph_summary import (
    SCHEMA_VERSION,
    SLICE_RULES,
    summarize_graph,
    write_projection_files,
)
from ue_editor_tools.knowledge_graph import validate_graph


RESPONSIBILITY = (
    "Create compact, human-oriented projections of a UE knowledge graph while retaining raw node, relation, and evidence identifiers."
)


def main() -> int:
    cli = parser(
        "提炼 UE 知识图谱为可阅读的工程总览、系统和业务切片。",
        "Project a UE knowledge graph into readable overview, system, and feature slices.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    cli.add_argument("--input", required=True, metavar="JSON")
    cli.add_argument(
        "--view",
        choices=("overview", "systems", "slice", "entity", "all"),
        default="all",
        help="输出视图，默认 all。 / Projection to emit; default all.",
    )
    cli.add_argument(
        "--slice",
        dest="slice_ids",
        action="append",
        choices=tuple(SLICE_RULES),
        help="选择业务切片，可重复。 / Slice id; repeatable.",
    )
    cli.add_argument(
        "--entity",
        dest="entity_ids",
        action="append",
        help="按 node_id、名称或对象路径输出实体详情，可重复。 / Entity selector; repeatable.",
    )
    cli.add_argument("--max-nodes", type=int, default=120, metavar="N")
    cli.add_argument("--max-relations", type=int, default=120, metavar="N")
    cli.add_argument(
        "--output-dir",
        metavar="DIR",
        help="可选：同时写入 overview.json/.md、systems 和 slices 文件。 / Write projection files.",
    )
    args = cli.parse_args()
    if args.max_nodes < 1 or args.max_relations < 1:
        cli.argument_error("--max-nodes and --max-relations must be positive")
    if args.view == "slice" and not args.slice_ids:
        cli.argument_error("--view slice requires at least one --slice")
    if args.view == "entity" and not args.entity_ids:
        cli.argument_error("--view entity requires at least one --entity")
    try:
        document = read_json_object(args.input)
        if document.get("schema_version") != "ue_build_knowledge_graph":
            raise ValueError("Input is not a ue_build_knowledge_graph document")
        if not isinstance(document.get("graph"), dict):
            raise ValueError("Input graph must be an object")
        for field in ("nodes", "relations", "evidence"):
            if field in document["graph"] and not isinstance(document["graph"].get(field), list):
                raise ValueError(f"Graph field {field} must be an array")
        problems = validate_graph(document["graph"])
        summary = summarize_graph(
            document,
            view=args.view,
            slice_ids=args.slice_ids or (),
            entity_ids=args.entity_ids or (),
            max_nodes=args.max_nodes,
            max_relations=args.max_relations,
        )
        artifacts: list[str] = []
        if args.output_dir:
            artifacts = write_projection_files(summary, Path(args.output_dir))
        summary["artifacts"] = artifacts
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    output = result_document(
        SCHEMA_VERSION,
        summary,
        problems,
        responsibility=RESPONSIBILITY,
        boundaries=[
            "Projection ranks business-facing entities and high-signal relations; it does not prove runtime reachability.",
            "Blueprint node/pin payloads and large asset registry dependencies remain available only through source_graph identifiers and the raw graph.",
            "Name-only Blueprint symbols and candidate matches retain their original uncertainty.",
        ],
    )
    write_json(output)
    return 1 if any(item.get("severity") == "error" for item in problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
