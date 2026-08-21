from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .source_context import load_source_context, source_result

def list_source_includes(
    source_files: Path | Sequence[Path],
    engine_override: Path | None = None,
) -> dict[str, Any]:
    loaded = load_source_context(
        source_files,
        engine_override,
        load_includes=True,
        load_cpp_analysis=False,
    )
    return source_result(
        "ue_list_cxx_includes",
        loaded,
        {"includes": loaded["includes"]},
        responsibility="Report direct include spellings and deterministic filesystem provenance.",
        boundaries=[
            "Ambiguous, missing, and unresolved-macro includes are moved to validation.",
            "Referenced files are located for provenance but are never recursively read.",
            "Non-generated includes use deterministic filesystem provenance and do not model compiler search-path order.",
            "Physical ownership does not prove that a dependency is required or correctly declared.",
        ],
        additional_problems=loaded["include_problems"],
    )
