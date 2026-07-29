from __future__ import annotations

from tests.support import CliTestCase, write_text


class CxxAnalysisTests(CliTestCase):
    def test_cpp_derives_public_header_as_one_source_unit(self) -> None:
        result = self.cli(
            "ue_list_cxx_includes.py",
            "--source",
            str(self.fixture.source_cpp),
        )
        self.assertEqual(
            result["source_unit"]["source"]["path"],
            "Source/SampleGame/Private/SampleActor.cpp",
        )
        self.assertEqual(
            result["source_unit"]["header"]["path"],
            "Source/SampleGame/Public/SampleActor.h",
        )

    def test_public_header_derives_private_cpp_bidirectionally(self) -> None:
        result = self.cli(
            "ue_list_cxx_types.py",
            "--source",
            str(self.fixture.source_header),
        )
        self.assertEqual(
            result["source_unit"]["source"]["path"],
            "Source/SampleGame/Private/SampleActor.cpp",
        )
        self.assertEqual(
            result["source_unit"]["header"]["path"],
            "Source/SampleGame/Public/SampleActor.h",
        )

    def test_include_facts_report_engine_provenance_and_generated_header(self) -> None:
        result = self.cli(
            "ue_list_cxx_includes.py",
            "--source",
            str(self.fixture.source_cpp),
        )
        by_spelling = {item["spelling"]: item for item in result["includes"]}
        self.assertNotIn("SampleActor.h", by_spelling)
        self.assertEqual(
            by_spelling["GameplayTagContainer.h"]["resolution"]["owner"]["kind"],
            "engine_module",
        )
        self.assertEqual(
            by_spelling["CoreMinimal.h"]["resolution"]["location"]["root"],
            "engine",
        )
        self.assertEqual(
            by_spelling["SampleActor.generated.h"]["resolution"]["status"],
            "generated_header",
        )

    def test_include_scan_does_not_follow_nested_includes(self) -> None:
        nested = write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Public"
            / "Nested.h",
            """
            #pragma once
            #include "Deep.h"
            """,
        )
        write_text(
            nested.with_name("Deep.h"),
            "#pragma once",
        )
        original = self.fixture.source_header.read_text(encoding="utf-8")
        self.fixture.source_header.write_text(
            original.replace(
                '#include "CoreMinimal.h"',
                '#include "CoreMinimal.h"\n#include "Nested.h"',
            ),
            encoding="utf-8",
        )
        result = self.cli(
            "ue_list_cxx_includes.py",
            "--source",
            str(self.fixture.source_cpp),
        )
        spellings = {item["spelling"] for item in result["includes"]}
        self.assertIn("Nested.h", spellings)
        self.assertNotIn("Deep.h", spellings)

    def test_type_facts_report_reflection_members_and_namespace(self) -> None:
        result = self.cli(
            "ue_list_cxx_types.py",
            "--source",
            str(self.fixture.source_cpp),
        )
        actor = result["classes"][0]
        self.assertEqual(actor["qualified_name"], "Gameplay::ASampleActor")
        self.assertEqual(actor["base_types"], ["AActor"])
        self.assertIn("UCLASS()", actor["macros"])
        members = {item["name"]: item for item in actor["member_anchors"]}
        self.assertIn("UFUNCTION()", members["BeginPlay"]["macros"])
        self.assertIn("UPROPERTY()", members["Count"]["macros"])

    def test_type_facts_keep_roles_linkage_and_enum_shape(self) -> None:
        result = self.cli(
            "ue_list_cxx_types.py",
            "--source",
            str(self.fixture.source_cpp),
        )
        self.assertEqual(result["enums"][0]["qualified_name"], "Gameplay::ESampleState")
        self.assertTrue(result["enums"][0]["scoped"])
        globals_by_role = {
            item["role"]: item
            for item in result["global_variables"]
        }
        self.assertEqual(globals_by_role["definition"]["linkage"], "external")
        functions_by_role = {
            item["role"]: item
            for item in result["free_functions"]
        }
        self.assertEqual(
            functions_by_role["definition"]["qualified_name"],
            "Gameplay::Utility",
        )

    def test_type_facts_identify_local_interface_candidates(self) -> None:
        header = write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Public"
            / "SampleInterface.h",
            """
            #pragma once

            UINTERFACE()
            class USampleInterface : public UInterface
            {
                GENERATED_BODY()
            };

            class ISampleInterface
            {
                GENERATED_BODY()
            public:
                virtual void Execute() = 0;
            };
            """,
        )
        result = self.cli(
            "ue_list_cxx_types.py",
            "--source",
            str(header),
        )
        names = {item["name"] for item in result["interface_candidates"]}
        self.assertEqual(names, {"USampleInterface", "ISampleInterface"})
        self.assertTrue(
            all(item["reasons"] for item in result["interface_candidates"])
        )

    def test_function_facts_match_declaration_and_external_symbols(self) -> None:
        result = self.cli(
            "ue_inspect_cxx_function.py",
            "--source",
            str(self.fixture.source_cpp),
            "--function",
            "BeginPlay",
        )
        self.assertEqual(result["match_count"], 1)
        match = result["matches"][0]
        self.assertEqual(
            match["function"]["qualified_name"],
            "Gameplay::ASampleActor::BeginPlay",
        )
        self.assertEqual(match["relation"]["status"], "matched")
        symbols = {
            (item["kind"], item["spelling"])
            for item in match["external_symbols"]
        }
        self.assertIn(("type", "FGameplayTag"), symbols)
        self.assertIn(("member_call", "ASampleActor->Helper()"), symbols)
        self.assertIn(("free_function", "Gameplay::Utility"), symbols)
        self.assertTrue(
            all("line" in item["evidence"] for item in match["external_symbols"])
        )

    def test_same_name_overloads_receive_unique_function_ids(self) -> None:
        header = write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Public"
            / "Overloaded.h",
            """
            #pragma once
            class FOverloaded
            {
            public:
                void Run();
                void Run(int32 Value);
            };
            """,
        )
        source = write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Private"
            / "Overloaded.cpp",
            """
            #include "Overloaded.h"
            void FOverloaded::Run() {}
            void FOverloaded::Run(int32 Value) {}
            """,
        )
        self.assertTrue(header.is_file())
        result = self.cli(
            "ue_inspect_cxx_function.py",
            "--source",
            str(source),
            "--function",
            "Run",
        )
        self.assertEqual(result["match_count"], 2)
        self.assertEqual(
            len({match["function_id"] for match in result["matches"]}),
            2,
        )

    def test_missing_function_is_structured_domain_error(self) -> None:
        result = self.cli(
            "ue_inspect_cxx_function.py",
            "--source",
            str(self.fixture.source_cpp),
            "--function",
            "DoesNotExist",
            expected_code=1,
        )
        self.assertEqual(result["match_count"], 0)
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "function-not-found",
        )

    def test_standalone_header_scans_without_source_companion(self) -> None:
        header = write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Public"
            / "Standalone.h",
            """
            #pragma once
            struct FStandalone {};
            """,
        )
        result = self.cli(
            "ue_list_cxx_types.py",
            "--source",
            str(header),
        )
        self.assertIsNone(result["source_unit"]["source"])
        self.assertEqual(
            result["source_unit"]["header"]["path"],
            "Source/SampleGame/Public/Standalone.h",
        )
        self.assertEqual(result["structs"][0]["name"], "FStandalone")

    def test_ambiguous_companion_headers_produce_warning_without_guessing(self) -> None:
        source = write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Private"
            / "Dual.cpp",
            "void Touch() {}",
        )
        for directory in ("Public", "Classes"):
            write_text(
                self.fixture.project_root
                / "Source"
                / "SampleGame"
                / directory
                / "Dual.h",
                "#pragma once",
            )
        result = self.cli(
            "ue_list_cxx_includes.py",
            "--source",
            str(source),
        )
        self.assertIsNone(result["source_unit"]["header"])
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertTrue(
            any(
                problem["code"] == "source-unit-header-ambiguous"
                for problem in result["validation"]["problems"]
            )
        )

    def test_all_cxx_tools_reject_unsupported_suffixes(self) -> None:
        wrong = write_text(
            self.fixture.project_root / "Source" / "SampleGame" / "Wrong.txt",
            "not C++",
        )
        calls = {
            "ue_list_cxx_includes.py": (),
            "ue_list_cxx_types.py": (),
            "ue_inspect_cxx_function.py": ("--function", "Run"),
        }
        for script, extra in calls.items():
            with self.subTest(script=script):
                result = self.cli(
                    script,
                    "--source",
                    str(wrong),
                    *extra,
                    expected_code=2,
                )
                self.assert_request_failure(result, kind="input")
