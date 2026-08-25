from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_TOOLS = REPOSITORY_ROOT / "sourcetools"
if str(SOURCE_TOOLS) not in sys.path:
    sys.path.insert(0, str(SOURCE_TOOLS))

from ue_project_tools.cpp_frontend import load_cpp_unit  # noqa: E402
from ue_project_tools.project_graph import project_cpp_files  # noqa: E402


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


def _symbol_types(
    function: dict[str, Any], references: dict[str, Any]
) -> dict[str, str]:
    return {
        str(item["name"]): str(item["type_expression"])
        for item in [
            *function.get("parameter_facts", []),
            *references.get("local_variables", []),
        ]
        if item.get("name") and item.get("type_expression")
    }


def _callback_payload_type(
    expression: str,
    current_function: dict[str, Any],
    definitions_by_name: dict[str, list[dict[str, Any]]],
) -> str | None:
    callback_name = expression.strip().lstrip("&*").rsplit("::", 1)[-1]
    candidates = definitions_by_name.get(callback_name, [])
    current_owner = current_function.get("owner")
    same_owner = [item for item in candidates if item.get("owner") == current_owner]
    selected = same_owner[0] if len(same_owner) == 1 else candidates[0] if len(candidates) == 1 else None
    if selected is None:
        return None
    parameters = selected.get("parameter_facts", [])
    return str(parameters[1]["type_expression"]) if len(parameters) > 1 else None


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
    paths = project_cpp_files(root)
    if not paths:
        return {
            "project": str(project_file).replace("\\", "/"),
            "source_file_count": 0,
            "message_operation_count": 0,
            "operations": [],
            "problems": [],
        }

    relative_by_file = {
        str(path.resolve()).replace("\\", "/").casefold(): path.relative_to(
            root
        ).as_posix()
        for path in paths
    }
    text_by_file: dict[str, str] = {}
    global_tag_values: dict[str, set[str]] = {}
    for path in paths:
        key = str(path.resolve()).replace("\\", "/").casefold()
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        text_by_file[key] = text
        for name, tag in _tag_definitions(text).items():
            global_tag_values.setdefault(name, set()).add(tag)
    global_tags = {
        name: next(iter(values))
        for name, values in global_tag_values.items()
        if len(values) == 1
    }
    model = load_cpp_unit(paths[0], paths, root)
    definitions = [
        item for item in model["functions"] if item.get("role") == "definition"
    ]
    definitions_by_name: dict[str, list[dict[str, Any]]] = {}
    for function in definitions:
        definitions_by_name.setdefault(str(function["name"]), []).append(function)
    for diagnostic in model["diagnostics"]:
        problems.append(
            {
                "severity": "warning",
                "code": "tree-sitter-cpp-syntax-warning",
                "path": relative_by_file.get(
                    str(diagnostic["file"]), str(diagnostic["file"])
                ),
                "line": int(diagnostic["line"]),
                "message": str(diagnostic["message"]),
            }
        )
    for function in definitions:
        file_key = str(function["file"])
        relative = relative_by_file.get(file_key, file_key)
        known_tags = {
            **global_tags,
            **_tag_definitions(text_by_file.get(file_key, "")),
        }
        references = model["references"].get(function["usr"], {})
        variable_types = _symbol_types(function, references)
        for call in references.get("call_details", []):
            callee = str(call.get("callee", ""))
            leaf = str(call.get("target_name") or "")
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
            arguments = [str(item) for item in call.get("arguments", [])]
            channel = (
                _channel(arguments[0], known_tags)
                if arguments
                else {"status": "unresolved", "tag": None, "expression": ""}
            )
            template = _TEMPLATE.search(str(call.get("expression", "")))
            payload_type = template.group(1).strip() if template else None
            if payload_type is None and kind == "publish" and len(arguments) > 1:
                payload_type = variable_types.get(
                    arguments[1].strip().lstrip("&*")
                )
            if payload_type is None and kind == "subscribe" and len(arguments) > 1:
                payload_type = _callback_payload_type(
                    arguments[-1], function, definitions_by_name
                )
            operations.append(
                {
                    "operation": kind,
                    "function": str(function["qualified_name"]),
                    "signature": str(function.get("signature", "")),
                    "callee": callee,
                    "channel": channel,
                    "payload_type": _clean_type(payload_type),
                    "payload_expression": arguments[1]
                    if kind == "publish" and len(arguments) > 1
                    else None,
                    "conditions": [],
                    "evidence": {
                        "root": "project",
                        "path": relative,
                        "line": int(call["line"]),
                        "end_line": int(call["line"]),
                    },
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
        "source_file_count": len(paths),
        "message_operation_count": len(operations),
        "operations": operations,
        "problems": problems,
    }
