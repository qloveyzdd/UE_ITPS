from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .source_includes import rooted_path
from .source_tokens import Token, _raw, _split_arguments


_SOURCE_MACROS = {
    "UCLASS",
    "USTRUCT",
    "UENUM",
    "UINTERFACE",
    "UPROPERTY",
    "UFUNCTION",
    "GENERATED_BODY",
    "GENERATED_IINTERFACE_BODY",
    "GENERATED_UCLASS_BODY",
    "GENERATED_UINTERFACE_BODY",
    "GENERATED_USTRUCT_BODY",
}
_SOURCE_MACRO_PREFIXES = ("DECLARE_", "IMPLEMENT_")


def _file_evidence(
    path: Path,
    line: int,
    project_root: Path,
    engine_root: Path | None,
    *,
    end_line: int | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        **rooted_path(path, project_root, engine_root),
        "line": line,
    }
    if end_line is not None and end_line != line:
        result["end_line"] = end_line
    return result


def _public_location(
    path: Path,
    location: dict[str, Any],
    project_root: Path,
    engine_root: Path | None,
) -> dict[str, Any]:
    return _file_evidence(
        path,
        int(location["line"]),
        project_root,
        engine_root,
        end_line=int(location.get("end_line", location["line"])),
    )


def _source_macros(
    parsed: dict[str, Any],
    path: Path,
    project_root: Path,
    engine_root: Path | None,
) -> list[dict[str, Any]]:
    text = parsed["text"]
    tokens: list[Token] = parsed["tokens"]
    forward: dict[int, int] = parsed["forward"]
    macros: list[dict[str, Any]] = []
    for index, token in enumerate(tokens):
        if token.kind != "identifier":
            continue
        if token.value not in _SOURCE_MACROS and not token.value.startswith(
            _SOURCE_MACRO_PREFIXES
        ):
            continue
        item: dict[str, Any] = {
            "name": token.value,
            "evidence": _file_evidence(
                path,
                token.line,
                project_root,
                engine_root,
            ),
            "_expression": token.value,
            "_path": path,
            "_token_index": index,
            "_close_index": index,
        }
        if (
            index + 1 < len(tokens)
            and tokens[index + 1].value == "("
            and index + 1 in forward
        ):
            close = forward[index + 1]
            item["arguments"] = [
                _raw(text, tokens, start, end)
                for start, end in _split_arguments(
                    tokens,
                    index + 2,
                    close,
                )
            ]
            item["_expression"] = _raw(
                text,
                tokens,
                index,
                close + 1,
            )
            item["_close_index"] = close
        macros.append(item)
    return macros


def _callable_name(name: str, signature: str) -> str:
    return (
        f"~{name}"
        if re.search(rf"~\s*{re.escape(name)}\s*\(", signature)
        else name
    )
