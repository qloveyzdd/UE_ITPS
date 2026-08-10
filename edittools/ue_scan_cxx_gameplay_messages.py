#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from ue_editor_tools.contracts import parser, result_document, write_json
from ue_editor_tools.cxx_messages import scan_cxx_gameplay_messages


SCHEMA_VERSION = "ue_scan_cxx_gameplay_messages"
RESPONSIBILITY = "Scan project-local C++ for direct Gameplay Message publish, subscribe, and unsubscribe calls."


def main() -> int:
    cli = parser(
        "扫描项目本地 C++ Gameplay Message 调用。",
        "Scan project-local C++ Gameplay Message calls.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    cli.add_argument("--project", required=True, metavar="FILE")
    args = cli.parse_args()
    try:
        facts = scan_cxx_gameplay_messages(Path(args.project))
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    problems = list(facts.pop("problems", []))
    write_json(
        result_document(
            SCHEMA_VERSION,
            facts,
            problems,
            responsibility=RESPONSIBILITY,
            boundaries=[
                "Only project-local C++ text is scanned.",
                "Direct supported API calls are reported; overload resolution, aliases, wrappers, and runtime control flow are not inferred.",
                "Unresolved channel and payload expressions remain explicit evidence.",
            ],
        )
    )
    return 1 if any(item.get("severity") == "error" for item in problems) else 0


if __name__ == "__main__":
    raise SystemExit(main())
