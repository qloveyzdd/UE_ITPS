#!/usr/bin/env python3
"""Find .uproject candidates and report ambiguity without selecting arbitrarily."""

import argparse
from pathlib import Path

from ue_project_tools.common import json_text
from ue_project_tools.discovery import discovery_result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-root", default=".")
    args = parser.parse_args()
    result = discovery_result(Path(args.search_root))
    print(json_text(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
