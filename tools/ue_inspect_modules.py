#!/usr/bin/env python3
"""Locate Build.cs and entrypoint evidence for declared project modules."""

import argparse
from pathlib import Path

from ue_project_tools.code_inventory import inspect_modules
from ue_project_tools.common import json_text, read_json
from ue_project_tools.descriptor import resolve_internal_directories


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    project = Path(args.project).resolve()
    try:
        descriptor = read_json(project)
        roots, _ = resolve_internal_directories(
            project.parent, descriptor, "AdditionalRootDirectories"
        )
        result = inspect_modules(
            project.parent, descriptor.get("Modules", []), roots
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
