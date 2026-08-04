#!/usr/bin/env python3
from pathlib import Path
from ue_project_tools.common import cli_error_document, cli_parser, json_text
from ue_project_tools.project_graph import hierarchy_result

SCHEMA_VERSION = "ue_query_cxx_hierarchy"
RESPONSIBILITY = "Report the project-local inheritance neighborhood of one C++ type."


def _root(value: str) -> Path:
    path = Path(value).resolve()
    if path.suffix.casefold() == ".uproject":
        if not path.is_file():
            raise ValueError(f"Project descriptor is not a file: {path}")
        root = path.parent
    else:
        root = path
    if not root.is_dir():
        raise ValueError(f"Project root is not a directory: {root}")
    return root


def main() -> int:
    parser = cli_parser(
        "查询一个 C++ 类型的继承关系。",
        "Query one C++ type's inheritance neighborhood.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.add_argument(
        "--project",
        required=True,
        metavar="PATH",
        help=".uproject 文件或项目根目录 / .uproject file or project root",
    )
    parser.add_argument(
        "--class",
        dest="class_name",
        required=True,
        metavar="NAME",
        help="C++ 类型名 / C++ type name",
    )
    args = parser.parse_args()
    try:
        result = hierarchy_result(_root(args.project), args.class_name)
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
