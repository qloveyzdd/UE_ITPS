#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ue_itps_information_pool import query_information_pool


OPERATIONS = (
    "lookup",
    "search",
    "hierarchy",
    "impact",
    "callers",
    "cycles",
    "path",
    "test-scope",
    "diff",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="查询 UE ITPS 工程信息池的激活或历史快照。",
    )
    parser.add_argument("--pool", required=True, metavar="DIRECTORY")
    parser.add_argument("--operation", required=True, choices=OPERATIONS)
    parser.add_argument("--selector")
    parser.add_argument("--target")
    parser.add_argument("--snapshot", help="快照 ID、提交前缀或 active")
    parser.add_argument("--against", help="diff 对比的快照 ID 或提交前缀")
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--relation-kind", action="append", dest="relation_kinds")
    args = parser.parse_args()
    try:
        result = query_information_pool(
            Path(args.pool),
            args.operation,
            selector=args.selector,
            target=args.target,
            snapshot=args.snapshot,
            against=args.against,
            depth=args.depth,
            limit=args.limit,
            relation_kinds=(
                tuple(args.relation_kinds) if args.relation_kinds else None
            ),
        )
    except (OSError, ValueError) as exc:
        result = {
            "schema_version": "ue-itps.information-pool.query",
            "operation": args.operation,
            "status": "error",
            "message": str(exc),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
