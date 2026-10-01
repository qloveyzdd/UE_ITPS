"""按依赖前提选择项目测试。

默认只运行不依赖外部工程的 SourceTools 核心测试；组件测试和 Lyra
回归可以通过同一个入口选择，避免维护多套容易漂移的命令。
"""
from __future__ import annotations

import argparse
import sys
import unittest

from tests.support import ROOT, LYRA_PROJECT


def _root_modules(prefix: str) -> list[str]:
    return [
        "tests." + path.stem
        for path in sorted((ROOT / "tests").glob("test_*.py"))
        if path.name.startswith(prefix)
    ]


SUITE_MODULES = {
    "core": _root_modules("test_"),
    "lyra": _root_modules("test_lyra"),
    "components": [
        "edittools.tests.test_contracts",
        "edittools.tests.test_cxx_messages",
        "edittools.tests.test_message_resolution",
        "edittools.tests.test_offline_tools",
        "edittools.tests.test_question_router",
        "edittools.tests.test_runtime_helpers",
        "information_pool.tests.test_file_graph",
        "mcp_connection_pool.tests.test_pool",
    ],
}

# Core includes the Lyra modules by filename, so remove them explicitly.
SUITE_MODULES["core"] = [
    module for module in SUITE_MODULES["core"] if module not in SUITE_MODULES["lyra"]
]


def modules_for_suite(suite: str) -> list[str]:
    if suite == "all":
        return SUITE_MODULES["core"] + SUITE_MODULES["components"] + SUITE_MODULES["lyra"]
    return SUITE_MODULES[suite]


def selected_modules(suite: str) -> list[str]:
    """向后兼容的旧函数名，统一委托给显式套件清单。"""
    return modules_for_suite(suite)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    for package_root in (ROOT / "edittools", ROOT / "information_pool"):
        if str(package_root) not in sys.path:
            sys.path.insert(0, str(package_root))
    parser = argparse.ArgumentParser(description="运行项目核心、组件或本地 Lyra 回归。")
    parser.add_argument(
        "--suite",
        choices=("core", "components", "lyra", "all"),
        default="core",
        help="core 不依赖参考工程；components 覆盖辅助组件；lyra/all 要求本地 Lyra。",
    )
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
