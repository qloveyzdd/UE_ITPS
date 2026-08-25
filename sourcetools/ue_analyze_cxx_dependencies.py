#!/usr/bin/env python3
from ue_project_tools.common import (
    cli_error_document,
    cli_parser,
    json_text,
    project_root_from_input,
)
from ue_project_tools.project_graph import dependency_result

SCHEMA_VERSION = "ue_analyze_cxx_dependencies"
RESPONSIBILITY = "Build a project-local C++ type dependency graph and detect cycles."

def main() -> int:
    parser = cli_parser(
        "分析项目本地 C++ 类型依赖与循环。",
        "Analyze project-local C++ type dependencies and cycles.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.add_argument(
        "--project",
        required=True,
        metavar="PATH",
        help=".uproject 文件或项目根目录 / .uproject file or project root",
    )
    args = parser.parse_args()
    try:
        result = dependency_result(
            project_root_from_input(args.project),
        )
    except (OSError, ValueError) as exc:
        result = cli_error_document(
            SCHEMA_VERSION,
            code="project-input-failure",
            message=str(exc),
            responsibility=RESPONSIBILITY,
        )
        print(json_text(result), end="")
        return 2
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
