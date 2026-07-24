from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable


SKIP_DIRS = {
    ".git",
    ".idea",
    ".vs",
    "Binaries",
    "DerivedDataCache",
    "Intermediate",
    "Saved",
}

OPERATION_CHOICES = (
    "scan",
    "open_editor",
    "build_editor",
    "run_game",
    "cook_package",
)


CLI_EPILOG = """\
输出契约 / Output contract:
  schema_version -> 模块事实 / module facts -> validation -> limits

退出码 / Exit codes:
  0  扫描完成且无阻断问题 / Scan completed without blocking problems
  1  扫描完成但发现阻断问题 / Scan completed with blocking problems
  2  参数、输入或读取失败 / Argument, input, or read failure
"""


class BilingualArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
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


def cli_parser(
    description_zh: str,
    description_en: str,
    *,
    epilog: str | None = None,
) -> argparse.ArgumentParser:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    return BilingualArgumentParser(
        description=f"{description_zh}\n{description_en}",
        epilog=epilog or CLI_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


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
        },
    }


def cli_error_document(
    schema_version: str,
    *,
    code: str,
    message: str,
    responsibility: str,
) -> dict[str, Any]:
    """Return a machine-readable input/read failure for focused CLIs."""
    return result_document(
        schema_version,
        {"request": {"status": "failed"}},
        [
            {
                "severity": "error",
                "code": code,
                "message": message,
            }
        ],
        responsibility=responsibility,
        boundaries=[
            "The requested scan did not start because its input or source context could not be read.",
            "Command-line syntax errors still use argparse usage text and exit code 2.",
        ],
    )


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def normalized(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


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


def iter_files(root: Path, suffix: str) -> Iterable[Path]:
    if not root.is_dir():
        return []
    matches: list[Path] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        for name in files:
            if name.casefold().endswith(suffix.casefold()):
                matches.append((Path(current) / name).resolve())
    return matches


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"
