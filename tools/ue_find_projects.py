#!/usr/bin/env python3
"""查找 .uproject 候选文件，并在存在歧义时如实报告而不擅自选择。"""

import argparse
from pathlib import Path

from ue_project_tools.common import json_text
from ue_project_tools.discovery import discovery_result


def main() -> int:
    """查找搜索根目录下的 Unreal 项目，并以 JSON 格式输出结果。"""
    parser = argparse.ArgumentParser(description=__doc__)
    # 默认使用调用者的当前目录，使工具可以从任意仓库根目录运行。
    parser.add_argument("--search-root", default=".")
    args = parser.parse_args()

    # discovery_result 会明确报告零个、一个或多个候选项目，绝不会随意选择
    # 某个 .uproject 文件来掩盖工作区中存在的歧义。
    result = discovery_result(Path(args.search_root))

    # json_text 负责生成供脚本和 Skill 使用的稳定序列化格式。
    print(json_text(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
