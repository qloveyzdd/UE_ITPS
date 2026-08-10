#!/usr/bin/env python3
from __future__ import annotations

from ue_editor_tools.cli import read_json_object
from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.knowledge_graph import diff_graphs


SCHEMA_VERSION = "ue_diff_knowledge_graph"
RESPONSIBILITY = (
    "Compare two deterministic logical knowledge graph documents by canonical identity."
)


def main() -> int:
    cli = parser(
        "比较两个 UE 知识图谱快照。",
        "Compare two UE knowledge graph snapshots.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    cli.add_argument("--current", required=True, metavar="JSON")
    cli.add_argument("--previous", required=True, metavar="JSON")
    args = cli.parse_args()
    try:
        current = read_json_object(args.current)
        previous = read_json_object(args.previous)
        if (
            current.get("schema_version") != "ue_build_knowledge_graph"
            or previous.get("schema_version") != "ue_build_knowledge_graph"
        ):
            raise ValueError("Both inputs must be ue_build_knowledge_graph documents")
        difference = diff_graphs(dict(current["graph"]), dict(previous["graph"]))
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    counts = {key: len(value) for key, value in difference.items()}
    write_json(
        result_document(
            SCHEMA_VERSION,
            {"counts": counts, "difference": difference},
            [],
            responsibility=RESPONSIBILITY,
            boundaries=[
                "Diff compares canonical entities, relation triples, and node properties; evidence-only changes are not reported."
            ],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
