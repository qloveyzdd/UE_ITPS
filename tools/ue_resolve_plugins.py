#!/usr/bin/env python3
"""Resolve direct .uproject plugin references for one explicit profile."""

import argparse
from pathlib import Path

from ue_project_tools.common import json_text, read_json
from ue_project_tools.descriptor import resolve_internal_directories
from ue_project_tools.plugins import resolve_project_plugins


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--engine-root", required=True)
    parser.add_argument("--operation", default="scan")
    parser.add_argument("--platform", default="Win64")
    parser.add_argument("--target-type", default="Editor")
    parser.add_argument("--configuration", default="Development")
    args = parser.parse_args()
    project = Path(args.project).resolve()
    try:
        descriptor = read_json(project)
        roots, _ = resolve_internal_directories(
            project.parent, descriptor, "AdditionalPluginDirectories"
        )
        result = resolve_project_plugins(
            project.parent,
            Path(args.engine_root).resolve(),
            descriptor.get("Plugins", []),
            roots,
            args.operation,
            args.platform,
            args.target_type,
            args.configuration,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
