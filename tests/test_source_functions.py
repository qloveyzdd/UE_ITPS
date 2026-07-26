from __future__ import annotations

from pathlib import Path
import tempfile

from tools.ue_project_tools.source_unit import inspect_source_function

from tests.support import EnvelopeAssertions, create_fixture, write_text


class SourceFunctionTests(EnvelopeAssertions):
    def test_function_matches_declaration_and_reports_external_references(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            result = inspect_source_function(fixture.source_file, "Execute")

        self.assert_envelope(result)
        self.assertEqual(result["match_count"], 1)
        match = result["matches"][0]
        self.assertEqual(match["relation"]["status"], "matched")
        self.assertEqual(match["function"]["owner"], "UFixtureObject")
        self.assertEqual(
            match["external_types"],
            ["TObjectPtr<UObject>", "UObject"],
        )
        self.assertEqual(
            match["external_methods"],
            ["UObject->GetWorld()", "TObjectPtr<UObject>->GetName()"],
        )

    def test_same_name_overloads_remain_separate_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            write_text(
                fixture.header_file,
                """
                #pragma once
                class UFixtureObject
                {
                public:
                    void Execute(UObject* Context) const;
                    void Execute(int32 Count);
                };
                """,
            )
            write_text(
                fixture.source_file,
                """
                #include "Feature.h"
                void UFixtureObject::Execute(UObject* Context) const {}
                void UFixtureObject::Execute(int32 Count) {}
                """,
            )
            first = inspect_source_function(fixture.source_file, "Execute")
            second = inspect_source_function(fixture.source_file, "Execute")

        self.assertEqual(first["match_count"], 2)
        first_ids = [match["function_id"] for match in first["matches"]]
        second_ids = [match["function_id"] for match in second["matches"]]
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(len(first_ids), len(set(first_ids)))

    def test_missing_function_is_a_structured_scan_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            result = inspect_source_function(fixture.source_file, "NotPresent")

        self.assertEqual(result["match_count"], 0)
        self.assertEqual(result["validation"]["status"], "error")
        self.assertTrue(
            any(
                problem["code"] == "function-not-found"
                for problem in result["validation"]["problems"]
            )
        )
