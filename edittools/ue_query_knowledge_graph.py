#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import read_json_object
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.graph_query import KnowledgeGraphQuery, QUERY_LEVELS, SCHEMA_VERSION
from ue_editor_tools.knowledge_graph import validate_graph


RESPONSIBILITY = "Expose tiered, read-only queries over a validated UE knowledge graph without querying raw fact documents."


def main() -> int:
    cli = parser(
        "按层级查询已构建的 UE 知识图谱。",
        "Query a built UE knowledge graph by information level.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    cli.add_argument("--input", required=True, metavar="JSON", help="ue_build_knowledge_graph JSON 文件")
    cli.add_argument("--level", choices=QUERY_LEVELS, default="overview", help="查询层级，默认 overview")
    cli.add_argument("--select", action="append", default=[], help="实体、系统或关系选择器，可重复")
    cli.add_argument("--query", default="", help="按名称、路径、类型或系统名称筛选")
    cli.add_argument("--max-nodes", type=int, default=120, metavar="N")
    cli.add_argument("--max-relations", type=int, default=120, metavar="N")
    args = cli.parse_args()
    if args.max_nodes < 1 or args.max_relations < 1:
        cli.argument_error("--max-nodes and --max-relations must be positive")
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
        result = query_engine.query(args.level, selectors=args.select, query=args.query)
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    content = {
        "source_schema": "ue_build_knowledge_graph",
        "project": query_engine.project,
        "level": args.level,
        "request": {
            "level": args.level,
            "select": list(args.select),
            "query": args.query,
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
            "overview and system levels expose projections and counts; they do not include raw evidence payloads.",
            "entity level exposes compact nodes, one-hop relations, and stable source identifiers.",
            "evidence level expands only evidence attached to selected entities or relations.",
            "The query reads a built graph and does not scan, modify, or infer new facts from raw project files.",
        ],
    )
    write_json(output)
    return 1 if any(item.get("severity") == "error" for item in problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())

