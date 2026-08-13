from __future__ import annotations

from pathlib import Path
from typing import Any

from .source_context import load_source_context, source_result

def list_source_includes(
    source_file: Path,
    engine_override: Path | None = None,
    compilation_database: Path | None = None,
) -> dict[str, Any]:
    loaded = load_source_context(
        source_file,
        engine_override,
        compilation_database,
        load_includes=True,
        load_cpp_analysis=False,
    )
    return source_result(
        "ue_list_cxx_includes",
        loaded,
        {"includes": loaded["includes"]},
        responsibility="Report non-companion direct include spellings and deterministic filesystem provenance.",
        boundaries=[
            "The source unit's own companion-header include is represented by source_unit.header and omitted from includes.",
            "Ambiguous, missing, and unresolved-macro includes are moved to validation.",
            "Referenced files are located for provenance but are never recursively read.",
            "Non-generated resolved includes are cross-checked against the active Clang translation unit; their public location remains deterministic filesystem provenance.",
            "Physical ownership does not prove that a dependency is required or correctly declared.",
        ],
        additional_problems=loaded["include_problems"],
    )
