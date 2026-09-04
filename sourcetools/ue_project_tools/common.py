from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Iterable, NoReturn


SKIP_DIRS = {
    ".git",
    ".idea",
    ".vs",
    "Binaries",
    "DerivedDataCache",
    "Intermediate",
    "Saved",
}

_TREE_SITTER_CSHARP_TOOLS = {
    "ue_inspect_module_rules",
    "ue_inspect_targets",
}
_TREE_SITTER_CPP_TOOLS = {
    "ue_inspect_cxx_function",
    "ue_list_cxx_includes",
    "ue_list_cxx_types",
    "ue_inspect_module_entry",
}
_GRAPH_TOOLS = {
    "ue_read_plugin_descriptor",
}


def analysis_engines(tool_name: str) -> list[str]:
    engines = ["ue-itps"]
    if tool_name in _TREE_SITTER_CSHARP_TOOLS:
        engines.append("tree-sitter/ast-outline+gdep")
    if tool_name in _TREE_SITTER_CPP_TOOLS:
        engines.append("tree-sitter/ue-cpp")
    if tool_name in _GRAPH_TOOLS:
        engines.append("gdep-adapted")
    return engines


CLI_EPILOG = """\
输出契约 / Output contract:
  成功 / success: schema_version -> 模块事实 / module facts -> validation -> limits
  失败 / failure: schema_version -> request -> validation -> limits
  所有 JSON 输出写入 stdout；stderr 保持为空。
  All JSON output is written to stdout; stderr remains empty.

退出码 / Exit codes:
  0  扫描完成且无阻断问题 / Scan completed without blocking problems
  1  扫描完成但发现阻断问题 / Scan completed with blocking problems
  2  参数、输入或读取失败 / Argument, input, or read failure
"""


class BilingualArgumentParser(argparse.ArgumentParser):
    def __init__(
        self,
        *args: Any,
        schema_version: str,
        responsibility: str,
        **kwargs: Any,
    ) -> None:
        self.schema_version = schema_version
        self.responsibility = responsibility
        self._parsing_arguments = False
        super().__init__(*args, **kwargs)
        self._positionals.title = "位置参数 / Positional arguments"
        self._optionals.title = "选项 / Options"
        for action in self._actions:
            if isinstance(action, argparse._HelpAction):
                action.help = "显示帮助并退出 / Show this help message and exit"

    def format_help(self) -> str:
        return super().format_help().replace("usage:", "用法 / usage:", 1)

    def format_usage(self) -> str:
        return super().format_usage().replace("usage:", "用法 / usage:", 1)

    def parse_args(
        self,
        args: list[str] | None = None,
        namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        self._parsing_arguments = True
        try:
            return super().parse_args(args, namespace)
        finally:
            self._parsing_arguments = False

    def error(self, message: str) -> NoReturn:
        failure_kind = "argument" if self._parsing_arguments else "input"
        result = cli_error_document(
            self.schema_version,
            kind=failure_kind,
            code=f"{failure_kind}-error",
            message=message,
            responsibility=self.responsibility,
        )
        sys.stdout.write(json_text(result))
        raise SystemExit(2)


def cli_parser(
    description_zh: str,
    description_en: str,
    *,
    schema_version: str,
    responsibility: str,
    epilog: str | None = None,
) -> BilingualArgumentParser:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    return BilingualArgumentParser(
        description=f"{description_zh}\n{description_en}",
        epilog=epilog or CLI_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        schema_version=schema_version,
        responsibility=responsibility,
    )


def run_single_path_tool(
    parser: BilingualArgumentParser,
    argument: str,
    operation: Callable[[Path], dict[str, Any]],
) -> int:
    args = parser.parse_args()
    try:
        result = operation(Path(getattr(args, argument)))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    sys.stdout.write(json_text(result))
    return 1 if result["validation"]["status"] == "error" else 0


def validation_result(problems: list[dict[str, Any]]) -> dict[str, Any]:
    severities = {str(problem.get("severity")) for problem in problems}
    status = (
        "error"
        if "error" in severities
        else ("warning" if "warning" in severities else "ok")
    )
    return {
        "status": status,
        "problem_count": len(problems),
        "problems": problems,
    }


def result_document(
    schema_version: str,
    content: dict[str, Any],
    problems: list[dict[str, Any]],
    *,
    responsibility: str,
    boundaries: list[str],
) -> dict[str, Any]:
    reserved = {"schema_version", "validation", "limits"}
    overlap = reserved.intersection(content)
    if overlap:
        raise ValueError(
            "Result content contains reserved fields: " + ", ".join(sorted(overlap))
        )
    return {
        "schema_version": schema_version,
        **content,
        "validation": validation_result(problems),
        "limits": {
            "responsibility": responsibility,
            "boundaries": boundaries,
            "analysis_engines": analysis_engines(schema_version),
        },
    }


def cli_error_document(
    schema_version: str,
    *,
    kind: str = "input",
    code: str,
    message: str,
    responsibility: str,
) -> dict[str, Any]:
    """Return the shared machine-readable request-failure envelope."""
    if kind not in {"argument", "input"}:
        raise ValueError(f"Unsupported CLI failure kind: {kind}")
    return result_document(
        schema_version,
        {
            "request": {
                "status": "failed",
                "kind": kind,
            }
        },
        [
            {
                "severity": "error",
                "code": code,
                "message": message,
            }
        ],
        responsibility=responsibility,
        boundaries=[
            "The requested scan did not start, so no domain facts are present.",
            "The failure is reported as JSON on stdout with exit code 2.",
        ],
    )


def normalized(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def project_root_from_input(value: str) -> Path:
    path = Path(value).resolve()
    if path.suffix.casefold() == ".uproject":
        if not path.is_file():
            raise ValueError(f"Project descriptor is not a file: {path}")
        return path.parent
    if not path.is_dir():
        raise ValueError(f"Project root is not a directory: {path}")
    return path


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"Non-standard JSON constant is not allowed: {value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON object key: {key!r}")
        value[key] = item
    return value


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(
            handle,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def iter_files(
    root: Path,
    suffix: str,
    exact_names: set[str] | None = None,
) -> Iterable[Path]:
    if not root.is_dir():
        return []
    expected_filenames = (
        {f"{name}{suffix}".casefold() for name in exact_names}
        if exact_names is not None
        else None
    )
    matches: list[Path] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        for name in files:
            folded_name = name.casefold()
            if expected_filenames is not None:
                if folded_name not in expected_filenames:
                    continue
            elif not folded_name.endswith(suffix.casefold()):
                continue
            matches.append((Path(current) / name).resolve())
    return matches


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"
