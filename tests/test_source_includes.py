from __future__ import annotations

from pathlib import Path
import tempfile
from unittest.mock import patch

from tools.ue_project_tools.source_includes import module_records, resolve_include
from tools.ue_project_tools.source_unit import list_source_includes

from tests.support import EnvelopeAssertions, create_fixture, write_text


class SourceIncludeTests(EnvelopeAssertions):
    def test_includes_keep_unit_evidence_and_unique_filesystem_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            result = list_source_includes(fixture.source_file)

        self.assert_envelope(result)
        core_includes = [
            item for item in result["includes"] if item["spelling"] == "CoreMinimal.h"
        ]
        self.assertEqual(
            [item["evidence"]["unit"] for item in core_includes],
            ["cpp", "header"],
        )
        self.assertTrue(
            all(
                item["resolution"]["owner"]["kind"] == "engine_module"
                for item in core_includes
            )
        )
        generated = next(
            item
            for item in result["includes"]
            if item["spelling"] == "Feature.generated.h"
        )
        self.assertEqual(generated["resolution"]["status"], "generated_header")

    def test_companion_header_is_not_repeated_as_an_include(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            result = list_source_includes(fixture.source_file)

        self.assertFalse(
            any(item["spelling"] == "Feature.h" for item in result["includes"])
        )
        self.assertEqual(
            result["source_unit"]["header"]["path"],
            "Source/FixtureGame/Public/Feature.h",
        )

    def test_missing_include_moves_to_validation_without_recursive_reading(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            nested_dependency = (
                fixture.engine_root
                / "Engine"
                / "Source"
                / "Runtime"
                / "Core"
                / "Public"
                / "CoreMinimal.h"
            )
            write_text(
                nested_dependency,
                '#pragma once\n#include "NestedMissing.h"',
            )
            write_text(
                fixture.source_file,
                """
                #include "Feature.h"
                #include "DirectMissing.h"
                """,
            )
            result = list_source_includes(fixture.source_file)

        problem_spellings = {
            problem["include"]["spelling"]
            for problem in result["validation"]["problems"]
            if "include" in problem
        }
        self.assertIn("DirectMissing.h", problem_spellings)
        self.assertNotIn("NestedMissing.h", problem_spellings)
        self.assertFalse(
            any(
                item["spelling"] in {"DirectMissing.h", "NestedMissing.h"}
                for item in result["includes"]
            )
        )

    def test_preprocessor_condition_is_preserved_on_direct_include(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            write_text(
                fixture.engine_root
                / "Engine"
                / "Source"
                / "Runtime"
                / "Core"
                / "Public"
                / "EditorOnly.h",
                "#pragma once",
            )
            write_text(
                fixture.source_file,
                """
                #include "Feature.h"
                #if WITH_EDITOR
                #include "EditorOnly.h"
                #endif
                """,
            )
            result = list_source_includes(fixture.source_file)

        editor_only = next(
            item for item in result["includes"] if item["spelling"] == "EditorOnly.h"
        )
        self.assertEqual(
            editor_only["conditions"],
            [
                {
                    "kind": "preprocessor",
                    "expression": "WITH_EDITOR",
                    "branch": "then",
                    "start_line": 2,
                }
            ],
        )

    def test_resolved_module_candidate_reuses_its_known_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            records = module_records(
                fixture.project_root,
                fixture.engine_root,
            )
            include = {
                "spelling": "CoreMinimal.h",
                "syntax": "quote",
            }
            with patch(
                "tools.ue_project_tools.source_includes.owner_for_path",
                side_effect=AssertionError("known module owner was rescanned"),
            ):
                resolution = resolve_include(
                    include,
                    fixture.source_file,
                    records,
                    fixture.project_root,
                    fixture.engine_root,
                )

        self.assertEqual(resolution["status"], "resolved")
        self.assertEqual(resolution["owner"], {"kind": "engine_module"})

    def test_include_scan_skips_declaration_only_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            with patch(
                "tools.ue_project_tools.source_unit._callable_parts",
                side_effect=AssertionError("include scan loaded callable analysis"),
            ):
                result = list_source_includes(fixture.source_file)

        self.assertEqual(result["schema_version"], "ue-itps.cxx-includes.v1")
