#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from ue_itps_v4 import build_graph


def main() -> int:
    parser = argparse.ArgumentParser(
        description="构建 UE ITPS v4 项目级符号关系数据库。"
    )
    parser.add_argument("--project", required=True, metavar="FILE")
    parser.add_argument("--database", required=True, metavar="FILE")
    parser.add_argument("--engine-root", metavar="PATH")
    parser.add_argument("--cache-dir", metavar="PATH")
    parser.add_argument("--workers", type=int)
    args = parser.parse_args()
    last_progress = 0.0

    def report_progress(value: dict[str, object]) -> None:
        nonlocal last_progress
        now = time.monotonic()
        if (
            value.get("completed") != value.get("total")
            and now - last_progress < 2.0
        ):
            return
        last_progress = now
        print(
            json.dumps(
                {"event": "v4-progress", **value},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
            flush=True,
        )

    try:
        result = build_graph(
            Path(args.project),
            Path(args.database),
            engine_override=(
                Path(args.engine_root) if args.engine_root else None
            ),
            cache_dir=(
                Path(args.cache_dir) if args.cache_dir else None
            ),
            workers=args.workers,
            progress=report_progress,
        )
    except (OSError, ValueError) as exc:
        result = {
            "schema_version": "ue-itps.symbol-graph-build.v4",
            "status": "error",
            "message": str(exc),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
