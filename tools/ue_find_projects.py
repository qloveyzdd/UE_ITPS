#!/usr/bin/env python3
"""Find .uproject candidates and report ambiguity without selecting arbitrarily."""

import argparse
from pathlib import Path

from ue_project_tools.common import json_text
from ue_project_tools.discovery import discovery_result


def main() -> int:
    """Discover Unreal projects below a search root and emit the result as JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    # Keep the default relative to the caller so the tool works from any repository root.
    parser.add_argument("--search-root", default=".")
    args = parser.parse_args()

    # discovery_result reports zero, one, or multiple candidates explicitly; it never
    # hides an ambiguous workspace by selecting a .uproject file arbitrarily.
    result = discovery_result(Path(args.search_root))

    # json_text owns the stable serialization format consumed by scripts and the skill.
    print(json_text(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
