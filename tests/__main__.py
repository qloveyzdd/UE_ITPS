"""按依赖前提选择 SourceTools 测试；默认不加载真实 Lyra 用例。"""
from __future__ import annotations

import argparse
import sys
import unittest

from tests.support import ROOT, LYRA_PROJECT


def selected_modules(suite: str) -> list[str]:
    return [
        "tests." + path.stem
        for path in sorted((ROOT / "tests").glob("test_*.py"))
        if suite == "all" or path.name.startswith("test_lyra") == (suite == "lyra")
    ]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="运行 SourceTools 核心或本地 Lyra 回归。")
    parser.add_argument("--suite", choices=("core", "lyra", "all"), default="core",
                        help="core 不依赖参考工程；lyra/all 要求本地 Lyra。")
    parser.add_argument("--list", action="store_true", help="只列出选中的测试模块。")
    parser.add_argument("-v", "--verbose", action="store_true")
    arguments = parser.parse_args()
    modules = selected_modules(arguments.suite)
    if arguments.list:
        print("\n".join(modules))
        return 0
    if arguments.suite in {"lyra", "all"} and not LYRA_PROJECT.is_file():
        parser.error(
            f"找不到 Lyra 工程：{LYRA_PROJECT}；请设置 UE_ITPS_LYRA_PROJECT，"
            "或运行 --suite core。"
        )
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=2 if arguments.verbose else 1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
