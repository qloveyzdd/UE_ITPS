#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from ue_editor_tools.config_graph import scan_config_graph
from ue_editor_tools.contracts import parser, result_document, write_json


SCHEMA_VERSION = "ue_scan_config_graph"
RESPONSIBILITY = "Read project-local UE ini declarations, array operations, and explicit logical references."


def main() -> int:
    cli = parser(
        "扫描项目本地 UE 配置声明与逻辑引用。",
        "Scan project-local UE configuration declarations and logical references.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    cli.add_argument("--project", required=True, metavar="FILE")
    args = cli.parse_args()
    try:
        facts = scan_config_graph(Path(args.project))
    except (OSError, RuntimeError, ValueError) as exc:
        cli.error(str(exc))
    write_json(
        result_document(
            SCHEMA_VERSION,
            facts,
            [],
            responsibility=RESPONSIBILITY,
            boundaries=[
                "Only repository-local Config, Plugins, and Platforms ini files are read.",
                "observed_values applies deterministic local file order and is not the authoritative UE runtime config hierarchy.",
                "Only explicit UE object paths and tag-shaped values under tag-related keys become graph references.",
            ],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
