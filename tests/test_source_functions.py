from __future__ import annotations

from tests.fixture import write_text
from tests.source_layer_case import SourceLayerTestCase


class SourceFunctionTests(SourceLayerTestCase):
    def test_function_facts_match_declaration_and_external_references(self) -> None:
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Execute",
        )
        self.assertEqual(result["match_count"], 1)
        match = result["matches"][0]
        self.assertEqual(match["relation"]["status"], "matched")
        self.assertEqual(match["function"]["owner"], "UCurrentObject")
        self.assertEqual(
            match["external_types"],
            ["TObjectPtr<UObject>", "UObject"],
        )
        self.assertEqual(
            match["external_methods"],
            ["UObject->GetWorld()", "TObjectPtr<UObject>->GetName()"],
        )

    def test_same_name_overloads_have_stable_unique_ids(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            class UCurrentObject
            {
            public:
                void Execute(UObject* Context) const;
                void Execute(int32 Count);
            };
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "CurrentFeature.h"
            void UCurrentObject::Execute(UObject* Context) const {}
            void UCurrentObject::Execute(int32 Count) {}
            """,
        )
        first = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Execute",
        )
        second = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Execute",
        )
        first_ids = [item["function_id"] for item in first["matches"]]
        second_ids = [item["function_id"] for item in second["matches"]]
        self.assertEqual(first["match_count"], 2)
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(len(first_ids), len(set(first_ids)))

    def test_missing_function_is_a_structured_scan_error(self) -> None:
        result = self.cli(
            "ue_inspect_cxx_function.py",
            "--source",
            str(self.fixture.source_file),
            "--function",
            "DoesNotExist",
            expected_code=1,
        )
        self.assertEqual(result["match_count"], 0)
        self.assertEqual(result["validation"]["status"], "error")
        self.assertIn(
            "function-not-found",
            {problem["code"] for problem in result["validation"]["problems"]},
        )
