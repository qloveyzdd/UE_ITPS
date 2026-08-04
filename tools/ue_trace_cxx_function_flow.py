#!/usr/bin/env python3
from pathlib import Path
from ue_project_tools.common import cli_error_document, cli_parser, json_text
from ue_project_tools.project_graph import function_flow_result

SCHEMA_VERSION = "ue_trace_cxx_function_flow"
RESPONSIBILITY = (
    "Report local control flow and direct calls for selected C++ functions."
)


def main() -> int:
    parser = cli_parser(
        "追踪一个 C++ 函数的局部控制流和直接调用。",
        "Trace local control flow and direct calls for one C++ function.",
        schema_version=SCHEMA_VERSION,
        responsibility=RESPONSIBILITY,
    )
    parser.add_argument(
        "--source", required=True, metavar="FILE", help="C++ 源文件 / C++ source file"
    )
    parser.add_argument(
        "--function", required=True, metavar="NAME", help="函数名 / Function name"
    )
    args = parser.parse_args()
    try:
        source = Path(args.source).resolve()
        if (
            source.suffix.casefold() not in {".h", ".hpp", ".cpp", ".cc"}
            or not source.is_file()
        ):
            raise ValueError(f"Expected a C++ source file: {source}")
        result = function_flow_result(source, args.function)
    except (OSError, ValueError) as exc:
        result = cli_error_document(
            SCHEMA_VERSION,
            code="source-input-failure",
            message=str(exc),
            responsibility=RESPONSIBILITY,
        )
        print(json_text(result), end="")
        return 2
    print(json_text(result), end="")
    return 1 if result["validation"]["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
