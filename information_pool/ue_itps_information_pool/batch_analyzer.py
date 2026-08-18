from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = REPOSITORY_ROOT / "sourcetools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from ue_project_tools import source_function_index  # noqa: E402
from ue_project_tools import source_function_references  # noqa: E402
from ue_project_tools import source_include_facts  # noqa: E402
from ue_project_tools import source_type_facts  # noqa: E402
from ue_project_tools.source_context import load_source_context  # noqa: E402


ANALYZER_VERSION = "ue-itps.information-pool.batch-analyzer.v4-tree-sitter-cpp"


@dataclass
class BatchDocuments:
    types: dict[str, Any]
    includes: dict[str, Any]
    functions: dict[str, Any]
    function_references: list[dict[str, Any]]
    parse_count: int


def analyze_source_unit(
    source_file: Path,
    *,
    engine_override: Path | None = None,
) -> BatchDocuments:
    loaded = load_source_context(
        source_file,
        engine_override,
        load_includes=True,
        load_cpp_analysis=True,
    )

    original_loaders = {
        source_type_facts: source_type_facts.load_source_context,
        source_include_facts: source_include_facts.load_source_context,
        source_function_index: source_function_index.load_source_context,
        source_function_references: (
            source_function_references.load_source_context
        ),
    }
    original_callable_parts = source_function_references._callable_parts

    def shared_loader(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return loaded

    try:
        for module in original_loaders:
            module.load_source_context = shared_loader

        types_document = source_type_facts.list_source_types(
            source_file,
            engine_override,
        )
        includes_document = source_include_facts.list_source_includes(
            source_file,
            engine_override,
        )
        functions_document = source_function_index.list_source_functions(
            source_file,
            engine_override,
        )

        cached_parts = loaded["parts"]

        def shared_callable_parts(
            *_args: Any,
            **_kwargs: Any,
        ) -> list[dict[str, Any]]:
            return cached_parts

        source_function_references._callable_parts = shared_callable_parts
        function_names = sorted(
            {
                str(item["name"])
                for item in functions_document.get("functions", [])
                if item.get("definitions")
            },
            key=str.casefold,
        )
        references = [
            source_function_references.inspect_source_function(
                source_file,
                function_name,
                engine_override=engine_override,
            )
            for function_name in function_names
        ]
    finally:
        for module, original in original_loaders.items():
            module.load_source_context = original
        source_function_references._callable_parts = original_callable_parts

    return BatchDocuments(
        types=types_document,
        includes=includes_document,
        functions=functions_document,
        function_references=references,
        parse_count=1,
    )
