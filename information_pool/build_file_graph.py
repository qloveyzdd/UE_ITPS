from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = ROOT / "sourcetools"
for candidate in (ROOT, TOOLS_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ue_file_graph import build_file_graph  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="建立 Unreal Engine 项目的第一阶段文件知识图谱。"
    )
    parser.add_argument("--project", required=True, type=Path, help="明确选择的 .uproject 文件")
    parser.add_argument("--output", required=True, type=Path, help="输出 SQLite 文件")
    arguments = parser.parse_args()

    try:
        summary = build_file_graph(arguments.project, arguments.output)
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False))
        return 2

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
