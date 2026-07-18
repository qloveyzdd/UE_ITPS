from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import result_document
from .source_parser import parse_rule_file


def _inspect_rules(path: Path, base_type: str, schema: str) -> dict[str, Any]:
    facts = parse_rule_file(path, base_type)
    problems: list[dict[str, Any]] = []
    if not facts["rules_classes"]:
        problems.append(
            {
                "severity": "error",
                "code": "rules-class-not-found",
                "path": facts["path"],
                "required_base_type": base_type,
                "message": f"No class derived from {base_type} was found in the selected file",
            }
        )
    kind = "Target.cs" if base_type == "TargetRules" else "Build.cs"
    return result_document(
        schema,
        facts,
        problems,
        responsibility=f"Report deterministic static source facts from one {kind} file.",
        boundaries=[
            "Static declarations are not effective UBT build results.",
            "Conditions and expressions are preserved but are not executed against a Target profile.",
            "Only direct same-file method relationships are resolved.",
            "Unsupported expressions remain unresolved source facts instead of inferred values.",
        ],
    )


def inspect_target_rules(path: Path) -> dict[str, Any]:
    return _inspect_rules(path, "TargetRules", "ue-itps.target-rules-source.v1")


def inspect_module_rules(path: Path) -> dict[str, Any]:
    return _inspect_rules(path, "ModuleRules", "ue-itps.module-rules-source.v1")
