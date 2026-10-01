#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    _edittools_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(_edittools_root))

from ue_editor_tools.cli import read_json_object
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.knowledge_graph import validate_graph

from knowledge_query.graph_query import (
    CERTAINTIES,
    DIRECTIONS,
    LEGACY_LEVELS,
    OPERATIONS,
    SCHEMA_VERSION,
    KnowledgeGraphQuery,
)


RESPONSIBILITY = "Expose fine-grained, read-only queries over a validated UE knowledge graph without querying raw fact documents."
LEGACY_OPERATION = {"overview": "overview", "system": "domain", "entity": "inspect", "evidence": "evidence"}


def main() -> int:
    cli = parser(
        "按需求细粒度查询已构建的 UE 知识图谱。",
        "Query a built UE knowledge graph with fine-grained operations.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    cli.add_argument("--input", required=True, metavar="JSON", help="ue_build_knowledge_graph JSON 文件")
    cli.add_argument("--operation", choices=OPERATIONS, help="细粒度查询操作")
    cli.add_argument("--level", choices=LEGACY_LEVELS, help="兼容旧版 overview/system/entity/evidence 查询")
    cli.add_argument("--select", action="append", default=[], help="实体、系统、切片或关系选择器，可重复")
    cli.add_argument("--query", default="", help="按名称、路径、类型、关系或系统名称筛选")
    cli.add_argument("--kind", dest="node_kinds", action="append", default=[], help="节点类型，可重复")
    cli.add_argument("--relation", dest="relation_kinds", action="append", default=[], help="关系类型，可重复")
    cli.add_argument("--certainty", action="append", choices=CERTAINTIES, default=[], help="可信度过滤，可重复")
    cli.add_argument("--direction", choices=DIRECTIONS, default="both", help="neighbors/trace 的关系方向")
    cli.add_argument("--depth", type=int, default=1, metavar="N", help="trace/impact 最大关系深度，默认 1")
    cli.add_argument("--max-nodes", type=int, default=120, metavar="N")
    cli.add_argument("--max-relations", type=int, default=120, metavar="N")
    args = cli.parse_args()

    if args.operation and args.level:
        cli.argument_error("--operation and --level cannot be used together")
    if args.max_nodes < 1 or args.max_relations < 1:
        cli.argument_error("--max-nodes and --max-relations must be positive")
    if args.depth < 1 or args.depth > 8:
        cli.argument_error("--depth must be between 1 and 8")

    legacy_mode = args.operation is None
    if legacy_mode:
        args.level = args.level or "overview"
    operation = args.operation or LEGACY_OPERATION[args.level]
    if operation in {"inspect", "neighbors", "trace", "impact", "evidence"} and not args.select and not args.query.strip():
        cli.argument_error(f"--operation {operation} requires --select or --query")
    if operation == "compare" and len(args.select) != 2:
        cli.argument_error("--operation compare requires exactly two --select values")
    if args.level in {"entity", "evidence"} and not args.select and not args.query.strip():
        cli.argument_error(f"--level {args.level} requires --select or --query")

    try:
        document = read_json_object(args.input)
        graph = document.get("graph")
        if document.get("schema_version") != "ue_build_knowledge_graph":
            raise ValueError("Input is not a ue_build_knowledge_graph document")
        if not isinstance(graph, dict):
            raise ValueError("Input graph must be an object")
        problems = validate_graph(graph)
        query_engine = KnowledgeGraphQuery(
            document,
            max_nodes=args.max_nodes,
            max_relations=args.max_relations,
        )
        result = query_engine.query(
            args.level,
            operation=None if legacy_mode else operation,
            selectors=args.select,
            query=args.query,
            node_kinds=args.node_kinds,
            relation_kinds=args.relation_kinds,
            certainties=args.certainty,
            direction=args.direction,
            depth=args.depth,
        )
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))

    content = {
        "source_schema": "ue_build_knowledge_graph",
        "project": query_engine.project,
        "operation": operation,
        "level": args.level,
        "request": {
            "operation": operation,
            "level": args.level,
            "select": list(args.select),
            "query": args.query,
            "kind": list(args.node_kinds),
            "relation": list(args.relation_kinds),
            "certainty": list(args.certainty),
            "direction": args.direction,
            "depth": args.depth,
            "max_nodes": args.max_nodes,
            "max_relations": args.max_relations,
        },
        "result": result,
        "source_graph": {
            "schema_version": "ue_build_knowledge_graph",
            "project": query_engine.project,
            "counts": {
                "nodes": len(query_engine.summary.nodes),
                "relations": len(query_engine.summary.relations),
                "evidence": len(query_engine.summary.evidence),
            },
        },
    }
    output = result_document(
        SCHEMA_VERSION,
        content,
        problems,
        responsibility=RESPONSIBILITY,
        boundaries=[
            "search and domain return projections and identifiers; they do not include raw evidence payloads.",
            "inspect and neighbors expose compact entities and relations for the next LLM query step.",
            "trace and impact follow only declared graph relations and enforce depth and result limits.",
            "evidence expands only evidence attached to selected entities or relations.",
            "The query reads a built graph and does not scan, modify, or infer new facts from raw project files.",
        ],
    )
    write_json(output)
    return 1 if any(item.get("severity") == "error" for item in problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
