#!/usr/bin/env python3
from ue_project_tools.common import cli_parser, json_text
from ue_project_tools.tool_pool import tool_pool_result

SCHEMA_VERSION = "ue_list_tools"
RESPONSIBILITY = "List all probes in the project tool pool."


def main() -> int:
    parser = cli_parser(
        "列出项目工具池中的全部只读探针。",
        "List every read-only probe in the project tool pool.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.parse_args()
    result = tool_pool_result()
    print(json_text(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
