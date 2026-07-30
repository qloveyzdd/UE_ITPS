#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ue_itps_v4 import query_graph


def main() -> int:
    parser = argparse.ArgumentParser(
        description="查询 UE ITPS v4 项目级符号关系数据库。"
    )
    parser.add_argument("--database", required=True, metavar="FILE")
    parser.add_argument("--symbol", required=True, metavar="SELECTOR")
    parser.add_argument("--depth", type=int, default=1)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    try:
        result = query_graph(
            Path(args.database),
            args.symbol,
            depth=args.depth,
            limit=args.limit,
        )
    except (OSError, ValueError) as exc:
        result = {
            "schema_version": "ue-itps.symbol-graph-query.v4",
            "status": "error",
            "message": str(exc),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "not_found" else 1


if __name__ == "__main__":
    raise SystemExit(main())
