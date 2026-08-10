from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_TOOLS = REPOSITORY_ROOT / "sourcetools"
if str(SOURCE_TOOLS) not in sys.path:
    sys.path.insert(0, str(SOURCE_TOOLS))

from ue_project_tools.project_graph import project_cpp_files  # noqa: E402
from ue_project_tools.source_declarations import _local_declaration_details  # noqa: E402
from ue_project_tools.source_operations import parse_operations  # noqa: E402
from ue_project_tools.source_parser import parse_cpp_file  # noqa: E402


_TAG_LITERAL = re.compile(r'"([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+)"')
_TAG_DEFINE = re.compile(
    r"UE_DEFINE_GAMEPLAY_TAG(?:_STATIC)?\s*\(\s*([A-Za-z_]\w*)\s*,\s*\"([^\"]+)\""
)
_TEMPLATE = re.compile(r"(?:RegisterListener|BroadcastMessage)\s*<\s*([^>]+)\s*>")


def _tag_definitions(text: str) -> dict[str, str]:
    return {match.group(1): match.group(2) for match in _TAG_DEFINE.finditer(text)}


def _channel(expression: str, known: dict[str, str]) -> dict[str, Any]:
    literal = _TAG_LITERAL.search(expression)
    if literal:
        return {"status": "static", "tag": literal.group(1), "expression": expression}
    simple = expression.strip().lstrip("&*")
    if simple in known:
        return {"status": "static", "tag": known[simple], "expression": expression}
    leaf = simple.rsplit("::", 1)[-1]
    if leaf in known:
        return {"status": "static", "tag": known[leaf], "expression": expression}
    return {"status": "unresolved", "tag": None, "expression": expression}


def _callables(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for owner in parsed.get("classes", []):
        for member in owner.get("members", []):
            if member.get("body_range"):
                results.append({"owner": owner.get("name"), **member})
    for item in parsed.get("external_definitions", []):
        results.append(
            {"owner": item.get("qualifier") or item.get("class_name"), **item}
        )
    for item in parsed.get("free_functions", []):
        results.append({"owner": None, **item})
    return results


def _parameter_types(parameters: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for parameter in parameters.split(","):
        declaration = parameter.split("=", 1)[0].strip()
        match = re.search(r"(?P<type>.+?)(?P<name>[A-Za-z_]\w*)\s*$", declaration)
        if match:
            values[match.group("name")] = match.group("type").strip()
    return values


def _clean_type(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\bconst\b", "", value)
    cleaned = re.sub(r"[&*]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def scan_cxx_gameplay_messages(project_file: Path) -> dict[str, Any]:
    project_file = project_file.resolve()
    if not project_file.is_file() or project_file.suffix.casefold() != ".uproject":
        raise ValueError(f"Project must be an existing .uproject file: {project_file}")
    root = project_file.parent
    operations: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    scanned = 0
    paths = project_cpp_files(root)
    global_tag_values: dict[str, set[str]] = {}
    for path in paths:
        try:
            for name, tag in _tag_definitions(
                path.read_text(encoding="utf-8-sig", errors="replace")
            ).items():
                global_tag_values.setdefault(name, set()).add(tag)
        except OSError:
            pass
    global_tags = {
        name: next(iter(values))
        for name, values in global_tag_values.items()
        if len(values) == 1
    }
    for path in paths:
        try:
            parsed = parse_cpp_file(path)
            scanned += 1
            known_tags = {**global_tags, **_tag_definitions(parsed["text"])}
            relative = path.relative_to(root).as_posix()
            for problem in parsed.get("problems", []):
                problems.append({**problem, "path": relative})
            callables = _callables(parsed)
            callable_by_name = {str(item.get("name", "")): item for item in callables}
            for function in callables:
                start, end = function["body_range"]
                variable_types = _parameter_types(str(function.get("parameters", "")))
                variable_types.update(
                    {
                        str(item["name"]): str(item["type_expression"])
                        for item in _local_declaration_details(
                            parsed["text"], parsed["tokens"], start, end
                        )
                    }
                )
                calls = parse_operations(
                    parsed["text"],
                    parsed["tokens"],
                    parsed["forward"],
                    parsed["reverse"],
                    start,
                    end,
                    include_control_metadata=True,
                )
                for call in calls:
                    if call.get("kind") != "invocation":
                        continue
                    callee = str(call.get("callee", ""))
                    leaf = re.split(r"::|->|\.", callee)[-1].split("<", 1)[0]
                    kind = (
                        "publish"
                        if leaf == "BroadcastMessage"
                        else "subscribe"
                        if leaf == "RegisterListener"
                        else "unsubscribe"
                        if leaf in {"UnregisterListener", "UnregisterListenerHandle"}
                        else None
                    )
                    if kind is None:
                        continue
                    arguments = [
                        str(item.get("expression", ""))
                        for item in call.get("arguments", [])
                    ]
                    channel = (
                        _channel(arguments[0], known_tags)
                        if arguments
                        else {"status": "unresolved", "tag": None, "expression": ""}
                    )
                    template = _TEMPLATE.search(str(call.get("expression", "")))
                    payload_type = template.group(1).strip() if template else None
                    if (
                        payload_type is None
                        and kind == "publish"
                        and len(arguments) > 1
                    ):
                        payload_type = variable_types.get(arguments[1].strip())
                    if (
                        payload_type is None
                        and kind == "subscribe"
                        and len(arguments) > 1
                    ):
                        callback_name = (
                            arguments[-1].strip().lstrip("&*").rsplit("::", 1)[-1]
                        )
                        callback = callable_by_name.get(callback_name)
                        if callback:
                            callback_types = list(
                                _parameter_types(
                                    str(callback.get("parameters", ""))
                                ).values()
                            )
                            if len(callback_types) > 1:
                                payload_type = callback_types[1]
                    owner = str(function.get("owner") or "")
                    name = str(function.get("name") or "")
                    qualified = f"{owner}::{name}" if owner else name
                    operations.append(
                        {
                            "operation": kind,
                            "function": qualified,
                            "signature": str(function.get("signature", "")),
                            "callee": callee,
                            "channel": channel,
                            "payload_type": _clean_type(payload_type),
                            "payload_expression": arguments[1]
                            if kind == "publish" and len(arguments) > 1
                            else None,
                            "conditions": list(call.get("conditions", [])),
                            "evidence": {
                                "root": "project",
                                "path": relative,
                                "line": int(call["location"]["line"]),
                                "end_line": int(
                                    call["location"].get(
                                        "end_line", call["location"]["line"]
                                    )
                                ),
                            },
                        }
                    )
        except (OSError, ValueError) as exc:
            problems.append(
                {
                    "severity": "warning",
                    "code": "cxx-message-scan-failed",
                    "path": path.relative_to(root).as_posix(),
                    "message": str(exc),
                }
            )
    operations.sort(
        key=lambda item: (
            str(item["evidence"]["path"]).casefold(),
            int(item["evidence"]["line"]),
            str(item["function"]).casefold(),
        )
    )
    return {
        "project": str(project_file).replace("\\", "/"),
        "source_file_count": scanned,
        "message_operation_count": len(operations),
        "operations": operations,
        "problems": problems,
    }
