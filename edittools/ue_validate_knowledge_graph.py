#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import read_json_object
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.knowledge_graph import validate_graph


SCHEMA_VERSION = "ue_validate_knowledge_graph"
RESPONSIBILITY = (
    "Validate knowledge graph identity, endpoints, evidence, and declared counts."
)


def main() -> int:
    cli = parser(
        "校验 UE 知识图谱结构和证据链。",
        "Validate UE knowledge graph structure and evidence.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    cli.add_argument("--input", required=True, metavar="JSON")
    args = cli.parse_args()
    try:
        document = read_json_object(args.input)
        if document.get("schema_version") != "ue_build_knowledge_graph":
            raise ValueError("Input is not a ue_build_knowledge_graph document")
        graph = document.get("graph")
        if not isinstance(graph, dict):
            raise ValueError("Input graph must be an object")
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    problems = validate_graph(graph)
    write_json(
        result_document(
            SCHEMA_VERSION,
            {
                "input_schema": document["schema_version"],
                "counts": graph.get("counts", {}),
            },
            problems,
            responsibility=RESPONSIBILITY,
            boundaries=[
                "Validation checks structural integrity and evidence presence, not semantic truth or runtime reachability."
            ],
        )
    )
    return 1 if any(item.get("severity") == "error" for item in problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
