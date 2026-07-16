#!/usr/bin/env python3
"""Composer for the small UE project inspection tools.

Use the focused ue_*.py commands for individual Codex/MCP capabilities. This
entrypoint only composes their service results and renders the versioned
snapshot/report format.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ue_project_tools.common import json_text, normalized, write_text
from ue_project_tools.report import markdown_report
from ue_project_tools.snapshot import build_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project")
    parser.add_argument("--search-root", default=".")
    parser.add_argument("--engine-root")
    parser.add_argument(
        "--operation",
        choices=("scan", "open_editor", "build_editor", "run_game", "cook_package"),
        default="scan",
    )
    parser.add_argument("--platform", default="Win64")
    parser.add_argument("--target-type", default="Editor")
    parser.add_argument("--configuration", default="Development")
    parser.add_argument("--json-out")
    parser.add_argument("--markdown-out")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = build_snapshot(
            project=args.project,
            search_root=args.search_root,
            engine_root=args.engine_root,
            operation=args.operation,
            platform=args.platform,
            target_type=args.target_type,
            configuration=args.configuration,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json_out:
        write_text(Path(args.json_out), json_text(manifest))
    if args.markdown_out:
        write_text(Path(args.markdown_out), markdown_report(manifest))

    if not args.json_out and not args.markdown_out:
        print(json_text(manifest), end="")
    else:
        print(
            json_text(
                {
                    "project": manifest["project"]["descriptor"],
                    "engine_version": manifest["engine"]["version"],
                    "modules": manifest["modules"]["count"],
                    "targets": manifest["targets"]["count"],
                    "plugins": manifest["plugins"]["count"],
                    "validation": manifest["validation"]["status"],
                    "json_out": (
                        normalized(Path(args.json_out)) if args.json_out else None
                    ),
                    "markdown_out": (
                        normalized(Path(args.markdown_out))
                        if args.markdown_out
                        else None
                    ),
                }
            ),
            end="",
        )
    return 0 if manifest["validation"]["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
