#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from ue_itps_information_pool import build_information_pool


def main() -> int:
    parser = argparse.ArgumentParser(
        description="构建并原子激活 UE ITPS 工程信息池快照。",
    )
    parser.add_argument("--project", required=True, metavar="FILE")
    parser.add_argument("--pool", required=True, metavar="DIRECTORY")
    parser.add_argument("--source-commit", metavar="REVISION")
    parser.add_argument("--engine-root", metavar="PATH")
    parser.add_argument("--cache-dir", metavar="PATH")
    parser.add_argument("--workers", type=int)
    args = parser.parse_args()
    last_progress = 0.0

    def report_progress(value: dict[str, object]) -> None:
        nonlocal last_progress
        now = time.monotonic()
        if value.get("completed") != value.get("total") and now - last_progress < 2.0:
            return
        last_progress = now
        print(
            json.dumps(
                {"event": "information-pool-progress", **value},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            file=sys.stderr,
            flush=True,
        )

    try:
        result = build_information_pool(
            Path(args.project),
            Path(args.pool),
            source_commit=args.source_commit,
            engine_override=Path(args.engine_root) if args.engine_root else None,
            cache_dir=Path(args.cache_dir) if args.cache_dir else None,
            workers=args.workers,
            progress=report_progress,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        result = {
            "schema_version": "ue-itps.information-pool.build",
            "status": "error",
            "message": str(exc),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
