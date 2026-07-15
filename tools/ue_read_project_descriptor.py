#!/usr/bin/env python3
"""Read only the explicit facts declared by one .uproject file."""

import argparse
from pathlib import Path

from ue_project_tools.common import json_text
from ue_project_tools.descriptor import descriptor_result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    try:
        _, result = descriptor_result(Path(args.project))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
