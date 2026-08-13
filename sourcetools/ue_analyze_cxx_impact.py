#!/usr/bin/env python3
from pathlib import Path
from ue_project_tools.common import cli_error_document, cli_parser, json_text
from ue_project_tools.project_graph import impact_result

SCHEMA_VERSION = "ue_analyze_cxx_impact"
RESPONSIBILITY = "Trace reverse project-local C++ type dependencies."


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
        "分析一个 C++ 类型的反向影响范围。",
        "Analyze the reverse impact of one C++ type.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.add_argument(
        "--project",
        required=True,
        metavar="PATH",
        help=".uproject 文件或项目根目录 / .uproject file or project root",
    )
    parser.add_argument("--compile-database", metavar="PATH", help="compile_commands.json 或其目录 / compile_commands.json or its directory")
    parser.add_argument(
        "--symbol", required=True, metavar="NAME", help="类型名 / Type name"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        metavar="N",
        help="最大反向追踪深度，默认 3 / Maximum reverse depth; default 3",
    )
    args = parser.parse_args()
    try:
        if args.max_depth < 1:
            raise ValueError("--max-depth must be at least 1")
        result = impact_result(
            _root(args.project),
            args.symbol,
            args.max_depth,
            Path(args.compile_database) if args.compile_database else None,
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
