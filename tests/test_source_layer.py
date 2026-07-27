from __future__ import annotations

from tests.fixture import FixtureTestCase, write_text


class SourceLayerTests(FixtureTestCase):
    def source_result(self, script: str, *extra: str) -> dict:
        return self.cli(
            script,
            "--source",
            str(self.fixture.source_file),
            *extra,
        )

    def test_three_cxx_tools_share_context_and_source_unit(self) -> None:
        includes = self.source_result("ue_list_cxx_includes.py")
        types = self.source_result("ue_list_cxx_types.py")
        function = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Execute",
        )
        for result in (includes, types, function):
            self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(includes["path_roots"], types["path_roots"])
        self.assertEqual(types["path_roots"], function["path_roots"])
        self.assertEqual(includes["context"], types["context"])
        self.assertEqual(types["context"], function["context"])
        self.assertEqual(includes["source_unit"], types["source_unit"])
        self.assertEqual(types["source_unit"], function["source_unit"])

    def test_header_is_derived_from_private_to_public(self) -> None:
        result = self.source_result("ue_list_cxx_types.py")
        self.assertEqual(
            result["source_unit"]["header"]["path"],
            "Source/CurrentGame/Public/CurrentFeature.h",
        )

    def test_ambiguous_automatic_headers_are_reported(self) -> None:
        write_text(
            self.fixture.source_file.parent / "CurrentFeature.h",
            "#pragma once",
        )
        result = self.source_result("ue_list_cxx_types.py")
        self.assertIsNone(result["source_unit"]["header"])
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertIn(
            "source-unit-header-ambiguous",
            {problem["code"] for problem in result["validation"]["problems"]},
        )

    def test_include_facts_keep_unit_owner_and_generated_status(self) -> None:
        result = self.source_result("ue_list_cxx_includes.py")
        core = [
            item for item in result["includes"] if item["spelling"] == "CoreMinimal.h"
        ]
        self.assertEqual(
            [item["evidence"]["unit"] for item in core],
            ["cpp", "header"],
        )
        self.assertTrue(
            all(item["resolution"]["owner"]["kind"] == "engine_module" for item in core)
        )
        generated = next(
            item
            for item in result["includes"]
            if item["spelling"] == "CurrentFeature.generated.h"
        )
        self.assertEqual(
            generated["resolution"]["status"],
            "generated_header",
        )
        self.assertNotIn(
            "CurrentFeature.h",
            {item["spelling"] for item in result["includes"]},
        )

    def test_include_scan_reports_only_direct_missing_includes(self) -> None:
        core_header = (
            self.fixture.engine_root
            / "Engine"
            / "Source"
            / "Runtime"
            / "Core"
            / "Public"
            / "CoreMinimal.h"
        )
        write_text(core_header, '#pragma once\n#include "NestedMissing.h"')
        write_text(
            self.fixture.source_file,
            """
            #include "CurrentFeature.h"
            #include "DirectMissing.h"
            """,
        )
        result = self.source_result("ue_list_cxx_includes.py")
        missing = {
            problem["include"]["spelling"]
            for problem in result["validation"]["problems"]
            if "include" in problem
        }
        self.assertIn("DirectMissing.h", missing)
        self.assertNotIn("NestedMissing.h", missing)

    def test_preprocessor_condition_stays_on_its_include(self) -> None:
        editor_header = (
            self.fixture.engine_root
            / "Engine"
            / "Source"
            / "Runtime"
            / "Core"
            / "Public"
            / "EditorOnly.h"
        )
        write_text(editor_header, "#pragma once")
        write_text(
            self.fixture.source_file,
            """
            #include "CurrentFeature.h"
            #if WITH_EDITOR
            #include "EditorOnly.h"
            #endif
            """,
        )
        result = self.source_result("ue_list_cxx_includes.py")
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

    def test_type_facts_report_enum_struct_class_members_and_macros(self) -> None:
        result = self.source_result("ue_list_cxx_types.py")
        by_name = {item["name"]: item for item in result["types"]}
        self.assertIn(
            "UENUM(BlueprintType)",
            by_name["ECurrentMode"]["macros"],
        )
        feature = by_name["FCurrentFeature"]
        self.assertEqual(feature["kind"], "struct")
        self.assertIn("USTRUCT(BlueprintType)", feature["macros"])
        variable = feature["member_details"]["variables"][0]
        self.assertEqual(variable["name"], "Tag")
        self.assertIn("UPROPERTY(EditAnywhere)", variable["macros"])
        current_object = by_name["UCurrentObject"]
        self.assertEqual(current_object["base_types"], ["UObject"])
        self.assertEqual(
            current_object["member_details"]["functions"][0]["name"],
            "Execute",
        )

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
