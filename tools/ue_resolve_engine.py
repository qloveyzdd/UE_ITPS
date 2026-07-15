#!/usr/bin/env python3
"""Resolve EngineAssociation to one Engine root and actual Build.version."""

import argparse
from pathlib import Path

from ue_project_tools.common import json_text, read_json
from ue_project_tools.engine import resolve_engine


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--engine-root")
    args = parser.parse_args()
    project = Path(args.project).resolve()
    try:
        descriptor = read_json(project)
        result = resolve_engine(
            project,
            str(descriptor.get("EngineAssociation") or ""),
            Path(args.engine_root) if args.engine_root else None,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 0 if result["status"] == "resolved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
