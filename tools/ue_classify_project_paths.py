#!/usr/bin/env python3
"""Classify standard project paths without inferring runtime use."""

import argparse
from pathlib import Path

from ue_project_tools.common import json_text
from ue_project_tools.structure import classify_project_paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    project = Path(args.project).resolve()
    result = classify_project_paths(project.parent, project)
    print(json_text(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
