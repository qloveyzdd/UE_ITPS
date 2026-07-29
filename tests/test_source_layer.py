from __future__ import annotations

from tests.fixture import FixtureTestCase, write_text


class SourceLayerTests(FixtureTestCase):
    def source_result(self, script: str, *extra: str) -> dict:
        return self.selected_source_result(
            script,
            self.fixture.source_file,
            *extra,
        )

    def selected_source_result(
        self,
        script: str,
        source,
        *extra: str,
        expected_code: int = 0,
    ) -> dict:
        return self.cli(
            script,
            "--source",
            str(source),
            *extra,
            expected_code=expected_code,
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

    def test_header_entry_derives_source_from_public_to_private(self) -> None:
        includes = self.selected_source_result(
            "ue_list_cxx_includes.py",
            self.fixture.header_file,
        )
        types = self.selected_source_result(
            "ue_list_cxx_types.py",
            self.fixture.header_file,
        )
        function = self.selected_source_result(
            "ue_inspect_cxx_function.py",
            self.fixture.header_file,
            "--function",
            "Execute",
        )
        for result in (includes, types, function):
            self.assertEqual(result["validation"]["status"], "ok")
            self.assertEqual(
                result["source_unit"]["source"]["path"],
                "Source/CurrentGame/Private/CurrentFeature.cpp",
            )
            self.assertEqual(
                result["source_unit"]["header"]["path"],
                "Source/CurrentGame/Public/CurrentFeature.h",
            )
        self.assertEqual(function["match_count"], 1)

    def test_cc_and_hpp_are_paired_bidirectionally(self) -> None:
        cc_file = (
            self.fixture.project_root
            / "Source"
            / "CurrentGame"
            / "Private"
            / "AlternateFeature.cc"
        )
        hpp_file = (
            self.fixture.project_root
            / "Source"
            / "CurrentGame"
            / "Public"
            / "AlternateFeature.hpp"
        )
        write_text(
            hpp_file,
            """
            #pragma once
            class FAlternateFeature
            {
            public:
                void Run();
            };
            """,
        )
        write_text(
            cc_file,
            """
            #include "AlternateFeature.hpp"
            void FAlternateFeature::Run() {}
            """,
        )

        for selected in (cc_file, hpp_file):
            result = self.selected_source_result(
                "ue_inspect_cxx_function.py",
                selected,
                "--function",
                "Run",
            )
            self.assertEqual(result["validation"]["status"], "ok")
            self.assertEqual(result["match_count"], 1)
            self.assertTrue(
                result["source_unit"]["source"]["path"].endswith(
                    "AlternateFeature.cc"
                )
            )
            self.assertTrue(
                result["source_unit"]["header"]["path"].endswith(
                    "AlternateFeature.hpp"
                )
            )

    def test_standalone_header_is_scanned_without_a_source_companion(self) -> None:
        header_only = (
            self.fixture.project_root
            / "Source"
            / "CurrentGame"
            / "Public"
            / "HeaderOnly.hpp"
        )
        write_text(
            header_only,
            """
            #pragma once
            #include "CoreMinimal.h"

            class FHeaderOnly
            {
            public:
                void Run() {}
            };
            """,
        )

        includes = self.selected_source_result(
            "ue_list_cxx_includes.py",
            header_only,
        )
        types = self.selected_source_result(
            "ue_list_cxx_types.py",
            header_only,
        )
        function = self.selected_source_result(
            "ue_inspect_cxx_function.py",
            header_only,
            "--function",
            "Run",
        )
        for result in (includes, types, function):
            self.assertEqual(result["validation"]["status"], "ok")
            self.assertIsNone(result["source_unit"]["source"])
            self.assertTrue(
                result["source_unit"]["header"]["path"].endswith(
                    "HeaderOnly.hpp"
                )
            )
        self.assertEqual(
            types["classes"][0]["evidence"]["unit"],
            "header",
        )
        self.assertEqual(function["match_count"], 1)

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

    def test_ambiguous_automatic_sources_are_reported(self) -> None:
        write_text(
            self.fixture.source_file.with_suffix(".cc"),
            '#include "CurrentFeature.h"',
        )
        result = self.selected_source_result(
            "ue_list_cxx_types.py",
            self.fixture.header_file,
        )
        self.assertIsNone(result["source_unit"]["source"])
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertIn(
            "source-unit-source-ambiguous",
            {problem["code"] for problem in result["validation"]["problems"]},
        )

    def test_unsupported_cxx_suffix_is_rejected(self) -> None:
        unsupported = self.fixture.source_file.with_suffix(".cxx")
        write_text(unsupported, "void Unsupported() {}")
        result = self.selected_source_result(
            "ue_list_cxx_types.py",
            unsupported,
            expected_code=2,
        )
        self.assertEqual(result["validation"]["status"], "error")
        self.assertIn(
            ".cc, .cpp, .h, .hpp",
            result["validation"]["problems"][0]["message"],
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

    def test_cxx_anchor_contract_reports_types_and_member_anchors(self) -> None:
        result = self.source_result("ue_list_cxx_types.py")
        self.assertNotIn("types", result)
        self.assertNotIn("member_details", str(result))

        by_name = {item["name"]: item for item in result["enums"]}
        self.assertIn(
            "UENUM(BlueprintType)",
            by_name["ECurrentMode"]["macros"],
        )
        feature = next(
            item
            for item in result["structs"]
            if item["name"] == "FCurrentFeature"
        )
        self.assertIn("USTRUCT(BlueprintType)", feature["macros"])
        variable = next(
            item
            for item in feature["member_anchors"]
            if item["kind"] == "variable"
        )
        self.assertEqual(variable["name"], "Tag")
        self.assertIn("UPROPERTY(EditAnywhere)", variable["macros"])
        current_object = next(
            item
            for item in result["classes"]
            if item["name"] == "UCurrentObject"
        )
        self.assertEqual(current_object["base_types"], ["UObject"])
        self.assertEqual(
            next(
                item
                for item in current_object["member_anchors"]
                if item["kind"] == "function"
            )["name"],
            "Execute",
        )
        self.assertEqual(result["interface_candidates"], [])
        self.assertEqual(result["global_variables"], [])
        self.assertEqual(result["free_functions"], [])

    def test_cxx_anchor_contract_reports_interfaces_globals_and_free_functions(
        self,
    ) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once

            UINTERFACE()
            class UCurrentInteractable : public UInterface
            {
                GENERATED_BODY()
            };

            class ICurrentInteractable
            {
                GENERATED_BODY()

            public:
                virtual void Interact(int32 Count) = 0;
                int32 Priority;
            };

            extern int32 GCurrentCount;
            void ResetCurrent(int32 Count);

            namespace Current
            {
                extern bool bReady;
                void Refresh();
            }
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "CurrentFeature.h"

            int32 GCurrentCount = 0;
            void ResetCurrent(int32 Count)
            {
                int32 LocalCount = Count;
            }

            namespace Current
            {
                bool bReady = false;
                void Refresh() {}
            }
            """,
        )

        result = self.source_result("ue_list_cxx_types.py")

        interface_candidates = {
            item["name"]: item for item in result["interface_candidates"]
        }
        self.assertEqual(
            set(interface_candidates),
            {"UCurrentInteractable", "ICurrentInteractable"},
        )
        self.assertIn(
            "uinterface_macro",
            interface_candidates["UCurrentInteractable"]["reasons"],
        )
        self.assertIn(
            "paired_uinterface",
            interface_candidates["ICurrentInteractable"]["reasons"],
        )

        interface_class = next(
            item
            for item in result["classes"]
            if item["name"] == "ICurrentInteractable"
        )
        member_kinds = {
            (item["kind"], item["name"])
            for item in interface_class["member_anchors"]
        }
        self.assertIn(("function", "Interact"), member_kinds)
        self.assertIn(("variable", "Priority"), member_kinds)

        self.assertEqual(
            {
                item["name"]
                for item in result["global_variables"]
            },
            {"GCurrentCount", "bReady"},
        )
        free_function_roles = {
            (item["name"], item["role"])
            for item in result["free_functions"]
        }
        self.assertEqual(
            free_function_roles,
            {
                ("ResetCurrent", "declaration"),
                ("ResetCurrent", "definition"),
                ("Refresh", "declaration"),
                ("Refresh", "definition"),
            },
        )

    def test_cxx_anchor_contract_handles_lyra_declaration_shapes(
        self,
    ) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once

            template <class TClass> class TSubclassOf;
            struct FForward;
            enum EForward : int;

            namespace Tags
            {
                UE_DECLARE_GAMEPLAY_TAG_EXTERN(Status_Ready);
            }

            class FOuter
            {
            public:
                class FNested
                {
                    int32 Value;
                };

                static int32 Count;
            };

            class FFriended
            {
                friend FOuter;
            };

            int32 FindValue(int32 Input);
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "CurrentFeature.h"

            int32 FOuter::Count;

            namespace Console
            {
                static float Duration = 0.0f;
                static FAutoConsoleVariableRef CVarDuration(
                    TEXT("current.Duration"),
                    Duration);
            }

            int32 FindValue(int32 Input)
            {
                return Input;
            }
            """,
        )

        result = self.source_result("ue_list_cxx_types.py")

        classes = {
            item["qualified_name"]: item
            for item in result["classes"]
        }
        self.assertEqual(classes["TSubclassOf"]["role"], "declaration")
        self.assertIsNone(classes["TSubclassOf"]["owner"])
        self.assertEqual(classes["FOuter"]["role"], "definition")
        self.assertEqual(
            classes["FOuter::FNested"]["owner"],
            "FOuter",
        )
        self.assertEqual(
            classes["FOuter::FNested"]["member_anchors"][0]["name"],
            "Value",
        )
        self.assertEqual(
            classes["FFriended"]["member_anchors"],
            [],
        )

        forward_struct = next(
            item
            for item in result["structs"]
            if item["name"] == "FForward"
        )
        self.assertEqual(forward_struct["role"], "declaration")
        forward_enum = next(
            item
            for item in result["enums"]
            if item["name"] == "EForward"
        )
        self.assertEqual(forward_enum["role"], "declaration")
        self.assertFalse(forward_enum["scoped"])

        self.assertEqual(
            {item["name"] for item in result["global_variables"]},
            {"Duration", "CVarDuration"},
        )
        self.assertEqual(
            {
                (item["name"], item["role"])
                for item in result["free_functions"]
            },
            {
                ("FindValue", "declaration"),
                ("FindValue", "definition"),
            },
        )
        self.assertEqual(result["unresolved_declarations"], [])

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
