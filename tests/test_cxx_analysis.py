from __future__ import annotations

from tests.support import CliTestCase, write_text


class CxxAnalysisTests(CliTestCase):
    def test_cxx_output_omits_diagnostic_metadata(self) -> None:
        result = self.cli(
            "ue_list_cxx_types.py",
            "--source",
            str(self.fixture.source_cpp),
        )
        self.assertNotIn("path_roots", result)
        self.assertNotIn("context", result)
        self.assertNotIn("analysis", result)
        self.assertNotIn("source_unit", result)
        self.assertTrue(
            any(
                item["qualified_name"] == "Gameplay::Utility"
                for item in result["free_functions"]
            )
        )
        self.assertFalse(
            (self.fixture.project_root / "compile_commands.json").exists()
        )

    def _write_delegate_fixture(self):
        header = write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Public"
            / "DelegateSample.h",
            """
            #pragma once

            class FDelegateOwner
            {
            public:
                DECLARE_EVENT_OneParam(FDelegateOwner, FChangedEvent, int32 Value)
                FChangedEvent OnChanged;

                void Publish();
            };

            class SDelegateSubscriber
            {
            public:
                void Subscribe(FDelegateOwner* Owner);
                void HandleChanged(int32 Value);
            };
            """,
        )
        source = write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Private"
            / "DelegateSample.cpp",
            """
            #include "DelegateSample.h"

            void FDelegateOwner::Publish()
            {
                OnChanged.Broadcast(1);
            }

            void SDelegateSubscriber::Subscribe(FDelegateOwner* Owner)
            {
                Owner->OnChanged.AddSP(
                    this,
                    &SDelegateSubscriber::HandleChanged
                );
            }

            void SDelegateSubscriber::HandleChanged(int32 Value)
            {
            }
            """,
        )
        return header, source

    def test_delegate_operations_preserve_event_and_callback_identity(self) -> None:
        header, source = self._write_delegate_fixture()

        types = self.cli(
            "ue_list_cxx_types.py",
            "--source",
            str(header),
        )
        owner = next(
            item for item in types["classes"]
            if item["qualified_name"] == "FDelegateOwner"
        )
        variables = {
            item["name"] for item in owner["member_anchors"]
            if item["kind"] == "variable"
        }
        functions = {
            item["name"] for item in owner["member_anchors"]
            if item["kind"] == "function"
        }
        self.assertIn("OnChanged", variables)
        self.assertNotIn("DECLARE_EVENT_OneParam", functions)
        self.assertFalse(
            any(
                problem["code"] == "source-type-member-projection-mismatch"
                for problem in types["validation"]["problems"]
            )
        )

        publish = self.cli(
            "ue_inspect_cxx_function.py",
            "--source",
            str(source),
            "--function",
            "Publish",
        )["matches"][0]
        self.assertEqual(
            publish["delegate_operations"],
            [
                {
                    "operation": "publish",
                    "api": "Broadcast",
                    "event": {
                        "owner_type": "FDelegateOwner",
                        "name": "OnChanged",
                        "qualified_name": "FDelegateOwner::OnChanged",
                    },
                    "callback": None,
                    "evidence": {"unit": "cpp", "line": 5},
                }
            ],
        )

        subscribe = self.cli(
            "ue_inspect_cxx_function.py",
            "--source",
            str(source),
            "--function",
            "Subscribe",
        )["matches"][0]
        self.assertEqual(
            subscribe["delegate_operations"],
            [
                {
                    "operation": "subscribe",
                    "api": "AddSP",
                    "event": {
                        "owner_type": "FDelegateOwner",
                        "name": "OnChanged",
                        "qualified_name": "FDelegateOwner::OnChanged",
                    },
                    "callback": {
                        "owner_type": "SDelegateSubscriber",
                        "name": "HandleChanged",
                        "qualified_name": (
                            "SDelegateSubscriber::HandleChanged"
                        ),
                    },
                    "evidence": {"unit": "cpp", "line": 10},
                }
            ],
        )

    def test_single_cpp_does_not_scan_matching_header(self) -> None:
        result = self.cli(
            "ue_list_cxx_includes.py",
            "--source",
            str(self.fixture.source_cpp),
        )
        self.assertNotIn("source_unit", result)
        self.assertEqual(
            {item["spelling"] for item in result["includes"]},
            {"SampleActor.h", "GameplayTagContainer.h"},
        )

    def test_explicit_same_name_source_and_header_are_both_scanned(self) -> None:
        result = self.cli(
            "ue_list_cxx_types.py",
            "--source",
            str(self.fixture.source_header),
            str(self.fixture.source_cpp),
        )
        self.assertNotIn("source_unit", result)
        self.assertEqual(result["classes"][0]["name"], "ASampleActor")
        self.assertEqual(
            {item["role"] for item in result["global_variables"]},
            {"declaration", "definition"},
        )

    def test_include_facts_report_engine_provenance_and_generated_header(self) -> None:
        result = self.cli(
            "ue_list_cxx_includes.py",
            "--source",
            str(self.fixture.source_cpp),
            str(self.fixture.source_header),
        )
        by_spelling = {item["spelling"]: item for item in result["includes"]}
        self.assertIn("SampleActor.h", by_spelling)
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
            str(self.fixture.source_header),
        )
        spellings = {item["spelling"] for item in result["includes"]}
        self.assertIn("Nested.h", spellings)
        self.assertNotIn("Deep.h", spellings)

    def test_type_facts_report_reflection_members_and_namespace(self) -> None:
        result = self.cli(
            "ue_list_cxx_types.py",
            "--source",
            str(self.fixture.source_cpp),
            str(self.fixture.source_header),
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
            str(self.fixture.source_header),
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

    def test_type_facts_only_report_standalone_forward_declarations(self) -> None:
        header = write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Public"
            / "ForwardDeclarations.h",
            """
            #pragma once

            class UExisting;
            class SAMPLEGAME_API UExported;
            enum class EMode : uint8;

            class FOwner
            {
                class FNested;
                friend class UExisting;
                TSubclassOf<class UExisting> Type;
                class UExisting* Raw;
                const class UExisting* Current;
                virtual class UExisting* Resolve() const override;
            };
            """,
        )

        result = self.cli(
            "ue_list_cxx_types.py",
            "--source",
            str(header),
        )

        self.assertEqual(
            {item["qualified_name"] for item in result["classes"]},
            {
                "UExisting",
                "UExported",
                "FOwner",
                "FOwner::FNested",
            },
        )
        self.assertEqual(
            {item["qualified_name"] for item in result["enums"]},
            {"EMode"},
        )

    def test_template_fields_and_initializers_emit_only_declared_names(self) -> None:
        header = write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Public"
            / "Container.h",
            """
            #pragma once
            class FContainer
            {
                TArray<TObjectPtr<UObject>> Items;
                double Time = 0.0;
            };
            """,
        )

        result = self.cli(
            "ue_list_cxx_types.py",
            "--source",
            str(header),
        )
        fields = {
            item["name"]: item["type_expression"]
            for item in result["classes"][0]["member_anchors"]
        }
        self.assertEqual(
            fields,
            {
                "Items": "TArray<TObjectPtr<UObject>>",
                "Time": "double",
            },
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
            str(self.fixture.source_header),
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

    def test_function_facts_resolve_control_initializer_receiver_type(self) -> None:
        self.fixture.source_header.write_text(
            self.fixture.source_header.read_text(encoding="utf-8").replace(
                "extern int32 GSampleCount;",
                """
        class UAbilityBase
        {
        public:
            void GetActivationGroup();
        };

extern int32 GSampleCount;""",
            ),
            encoding="utf-8",
        )
        self.fixture.source_cpp.write_text(
            self.fixture.source_cpp.read_text(encoding="utf-8").replace(
                """void ASampleActor::Helper()
{
    Count = 1;
}""",
                """void ASampleActor::Helper()
{
    if (UAbilityBase* Ability = Cast<UAbilityBase>(nullptr))
    {
        Ability->GetActivationGroup();
    }
}""",
            ),
            encoding="utf-8",
        )

        result = self.cli(
            "ue_inspect_cxx_function.py",
            "--source",
            str(self.fixture.source_cpp),
            "--function",
            "Helper",
        )
        symbols = {
            (item["kind"], item["spelling"], item.get("owner_type"))
            for item in result["matches"][0]["external_symbols"]
        }
        self.assertIn(
            (
                "member_call",
                "UAbilityBase->GetActivationGroup()",
                "UAbilityBase",
            ),
            symbols,
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
            str(header),
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
        self.assertNotIn("source_unit", result)
        self.assertEqual(result["structs"][0]["name"], "FStandalone")

    def test_single_cpp_ignores_all_matching_header_candidates(self) -> None:
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
        self.assertNotIn("source_unit", result)
        self.assertEqual(result["validation"]["status"], "ok")

    def test_two_explicit_files_must_be_opposite_kind_and_same_name(self) -> None:
        other_header = write_text(
            self.fixture.source_header.with_name("Other.h"),
            "#pragma once",
        )
        invalid_inputs = (
            (self.fixture.source_header, other_header),
            (self.fixture.source_cpp, other_header),
            (
                self.fixture.source_cpp,
                self.fixture.source_header,
                other_header,
            ),
        )
        for sources in invalid_inputs:
            with self.subTest(sources=sources):
                arguments = [
                    "ue_list_cxx_includes.py",
                    "--source",
                    *(str(path) for path in sources),
                ]
                result = self.cli(*arguments, expected_code=2)
                self.assert_request_failure(result, kind="input")

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
