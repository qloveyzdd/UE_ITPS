#!/usr/bin/env python3
"""Discover project Target.cs files and native-project evidence."""

import argparse
from pathlib import Path

from ue_project_tools.code_inventory import inspect_targets
from ue_project_tools.common import json_text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    project = Path(args.project).resolve()
    result = inspect_targets(project.parent)
    print(json_text(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
