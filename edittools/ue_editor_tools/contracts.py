from __future__ import annotations

import argparse
import json
import sys
from typing import Any, NoReturn


class ToolArgumentParser(argparse.ArgumentParser):
    def __init__(
        self, *args: Any, schema_version: str, responsibility: str, **kwargs: Any
    ) -> None:
        self.schema_version = schema_version
        self.responsibility = responsibility
        self._parsing = False
        super().__init__(*args, **kwargs)

    def parse_args(
        self, args: list[str] | None = None, namespace: argparse.Namespace | None = None
    ) -> argparse.Namespace:
        self._parsing = True
        try:
            return super().parse_args(args, namespace)
        finally:
            self._parsing = False

    def error(self, message: str) -> NoReturn:
        write_json(
            error_document(
                self.schema_version,
                kind="argument" if self._parsing else "input",
                code="argument-error" if self._parsing else "input-error",
                message=message,
                responsibility=self.responsibility,
            )
        )
        raise SystemExit(2)

    def argument_error(self, message: str) -> NoReturn:
        write_json(
            error_document(
                self.schema_version,
                kind="argument",
                code="argument-error",
                message=message,
                responsibility=self.responsibility,
            )
        )
        raise SystemExit(2)


def parser(
    description_zh: str,
    description_en: str,
    *,
    schema_version: str,
    responsibility: str,
) -> ToolArgumentParser:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    return ToolArgumentParser(
        description=f"{description_zh}\n{description_en}",
        epilog=(
            "输出契约 / Output contract:\n"
            "  所有 JSON 写入 stdout，stderr 保持为空。\n"
            "  All JSON is written to stdout; stderr remains empty.\n\n"
            "退出码 / Exit codes:\n"
            "  0  成功或非阻断警告 / Success or non-blocking warnings\n"
            "  1  扫描完成但存在阻断问题 / Completed with blocking problems\n"
            "  2  参数、输入、连接或读取失败 / Argument, input, connection, or read failure"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        schema_version=schema_version,
        responsibility=responsibility,
    )


def validation(problems: list[dict[str, Any]]) -> dict[str, Any]:
    severities = {str(item.get("severity")) for item in problems}
    status = (
        "error"
        if "error" in severities
        else "warning"
        if "warning" in severities
        else "ok"
    )
    return {"status": status, "problem_count": len(problems), "problems": problems}


def result_document(
    schema_version: str,
    content: dict[str, Any],
    problems: list[dict[str, Any]],
    *,
    responsibility: str,
    boundaries: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        **content,
        "validation": validation(problems),
        "limits": {"responsibility": responsibility, "boundaries": boundaries},
    }


def error_document(
    schema_version: str,
    *,
    kind: str,
    code: str,
    message: str,
    responsibility: str,
) -> dict[str, Any]:
    return result_document(
        schema_version,
        {"request": {"status": "failed", "kind": kind}},
        [{"severity": "error", "code": code, "message": message}],
        responsibility=responsibility,
        boundaries=[
            "The requested editor inspection did not complete, so no domain facts are authoritative."
        ],
    )


def write_json(value: Any) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
