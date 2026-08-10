#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from ue_editor_tools.cli import read_json_object
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.knowledge_graph import (
    build_knowledge_graph,
    has_dirty_packages,
    validate_graph,
)


SCHEMA_VERSION = "ue_build_knowledge_graph"
RESPONSIBILITY = "Merge supported source and Editor fact documents into one deterministic logical knowledge graph."


def main() -> int:
    cli = parser(
        "合并 UE 逻辑事实为统一知识图谱。",
        "Merge UE logical facts into one knowledge graph.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    cli.add_argument("--input", action="append", required=True, metavar="JSON")
    cli.add_argument("--allow-dirty", action="store_true")
    args = cli.parse_args()
    try:
        documents = [
            (str(Path(value).resolve()), read_json_object(value))
            for value in args.input
        ]
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    problems = []
    dirty_inputs = [
        path for path, document in documents if has_dirty_packages(document)
    ]
    if dirty_inputs and not args.allow_dirty:
        problems.append(
            {
                "severity": "error",
                "code": "dirty-editor-packages",
                "inputs": dirty_inputs,
                "message": "Knowledge graph build refused because Editor evidence contains dirty packages.",
            }
        )
        graph = {
            "project": "",
            "nodes": [],
            "relations": [],
            "evidence": [],
            "counts": {"nodes": 0, "relations": 0, "evidence": 0},
        }
        adapter_problems = []
    else:
        graph, adapter_problems = build_knowledge_graph(documents)
        problems.extend(validate_graph(graph))
    problems.extend(adapter_problems)
    write_json(
        result_document(
            SCHEMA_VERSION,
            {
                "source_schemas": sorted(
                    {
                        str(document.get("schema_version", ""))
                        for _, document in documents
                    }
                ),
                "graph": graph,
            },
            problems,
            responsibility=RESPONSIBILITY,
            boundaries=[
                "The graph merges explicit supported evidence and does not infer runtime reachability.",
                "Map assets remain asset-level logical entities; Actor and Component instances are excluded.",
            ],
        )
    )
    return 1 if any(item.get("severity") == "error" for item in problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
