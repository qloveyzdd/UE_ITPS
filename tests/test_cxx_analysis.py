from __future__ import annotations

from tests.support import WorkspaceTestCase, write_json, write_text


class CxxAnalysisTests(WorkspaceTestCase):
    def source_result(
        self,
        script: str,
        *arguments: str,
        source=None,
        expected_code: int = 0,
    ) -> dict:
        return self.cli(
            script,
            "--source",
            str(source or self.fixture.source_file),
            *arguments,
            expected_code=expected_code,
        )

    def test_cxx_tools_share_context_and_source_unit(self) -> None:
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

    def test_private_cpp_derives_public_header(self) -> None:
        result = self.source_result("ue_list_cxx_types.py")
        self.assertEqual(
            result["source_unit"]["header"]["path"],
            "Source/SampleGame/Public/SampleFeature.h",
        )

    def test_public_header_derives_private_cpp(self) -> None:
        for script, extra in (
            ("ue_list_cxx_includes.py", ()),
            ("ue_list_cxx_types.py", ()),
            ("ue_inspect_cxx_function.py", ("--function", "Execute")),
        ):
            with self.subTest(script=script):
                result = self.source_result(
                    script,
                    *extra,
                    source=self.fixture.header_file,
                )
                self.assertEqual(
                    result["source_unit"]["source"]["path"],
                    "Source/SampleGame/Private/SampleFeature.cpp",
                )
                self.assertEqual(
                    result["source_unit"]["header"]["path"],
                    "Source/SampleGame/Public/SampleFeature.h",
                )

    def test_cc_and_hpp_pair_bidirectionally(self) -> None:
        cc_file = (
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Private"
            / "AlternateFeature.cc"
        )
        hpp_file = (
            self.fixture.project_root
            / "Source"
            / "SampleGame"
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
            with self.subTest(selected=selected.suffix):
                result = self.source_result(
                    "ue_inspect_cxx_function.py",
                    "--function",
                    "Run",
                    source=selected,
                )
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

    def test_standalone_header_scans_without_source_companion(self) -> None:
        header = (
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Public"
            / "HeaderOnly.hpp"
        )
        write_text(
            header,
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
        includes = self.source_result("ue_list_cxx_includes.py", source=header)
        types = self.source_result("ue_list_cxx_types.py", source=header)
        function = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Run",
            source=header,
        )
        for result in (includes, types, function):
            self.assertIsNone(result["source_unit"]["source"])
            self.assertTrue(
                result["source_unit"]["header"]["path"].endswith("HeaderOnly.hpp")
            )
        self.assertEqual(types["classes"][0]["evidence"]["unit"], "header")
        self.assertEqual(function["match_count"], 1)

    def test_ambiguous_automatic_headers_are_warning(self) -> None:
        write_text(
            self.fixture.source_file.parent / "SampleFeature.h",
            "#pragma once",
        )
        result = self.source_result("ue_list_cxx_types.py")
        self.assertIsNone(result["source_unit"]["header"])
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertIn(
            "source-unit-header-ambiguous",
            {problem["code"] for problem in result["validation"]["problems"]},
        )

    def test_ambiguous_automatic_sources_are_warning(self) -> None:
        write_text(
            self.fixture.source_file.with_suffix(".cc"),
            '#include "SampleFeature.h"',
        )
        result = self.source_result(
            "ue_list_cxx_types.py",
            source=self.fixture.header_file,
        )
        self.assertIsNone(result["source_unit"]["source"])
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertIn(
            "source-unit-source-ambiguous",
            {problem["code"] for problem in result["validation"]["problems"]},
        )

    def test_unsupported_cxx_suffix_is_input_failure(self) -> None:
        unsupported = self.fixture.source_file.with_suffix(".cxx")
        write_text(unsupported, "void Unsupported() {}")
        result = self.source_result(
            "ue_list_cxx_types.py",
            source=unsupported,
            expected_code=2,
        )
        self.assert_request_failure(result, kind="input")
        self.assertIn(
            ".cc, .cpp, .h, .hpp",
            result["validation"]["problems"][0]["message"],
        )

    def test_source_context_refuses_nearest_project_ambiguity(self) -> None:
        root = self.fixture.workspace / "Ambiguous"
        source = root / "Source" / "Feature.cpp"
        write_text(source, "void Run() {}")
        write_json(root / "A.uproject", {"FileVersion": 3})
        write_json(root / "B.uproject", {"FileVersion": 3})
        result = self.source_result(
            "ue_list_cxx_types.py",
            source=source,
            expected_code=2,
        )
        self.assert_request_failure(result, kind="input")
        self.assertIn(
            "Multiple .uproject",
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
            if item["spelling"] == "SampleFeature.generated.h"
        )
        self.assertEqual(generated["resolution"]["status"], "generated_header")
        self.assertNotIn(
            "SampleFeature.h",
            {item["spelling"] for item in result["includes"]},
        )

    def test_include_scan_does_not_follow_nested_includes(self) -> None:
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
            #include "SampleFeature.h"
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

    def test_preprocessor_condition_stays_on_include(self) -> None:
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
            #include "SampleFeature.h"
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

    def test_type_facts_report_reflection_macros_and_members(self) -> None:
        result = self.source_result("ue_list_cxx_types.py")
        self.assertNotIn("types", result)
        enum = next(item for item in result["enums"] if item["name"] == "ESampleMode")
        self.assertIn("UENUM(BlueprintType)", enum["macros"])
        feature = next(
            item for item in result["structs"] if item["name"] == "FSampleFeature"
        )
        self.assertIn("USTRUCT(BlueprintType)", feature["macros"])
        tag = next(
            item
            for item in feature["member_anchors"]
            if item["kind"] == "variable"
        )
        self.assertEqual(tag["name"], "Tag")
        self.assertIn("UPROPERTY(EditAnywhere)", tag["macros"])
        sample_object = next(
            item for item in result["classes"] if item["name"] == "USampleObject"
        )
        self.assertEqual(sample_object["base_types"], ["UObject"])
        self.assertIn(
            ("function", "Execute"),
            {
                (item["kind"], item["name"])
                for item in sample_object["member_anchors"]
            },
        )

    def test_type_facts_report_interfaces_globals_and_free_functions(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            UINTERFACE()
            class USampleInteractable : public UInterface
            {
                GENERATED_BODY()
            };
            class ISampleInteractable
            {
                GENERATED_BODY()
            public:
                virtual void Interact(int32 Count) = 0;
                int32 Priority;
            };
            extern int32 GSampleCount;
            void ResetSample(int32 Count);
            namespace Sample
            {
                extern bool bReady;
                void Refresh();
            }
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            int32 GSampleCount = 0;
            void ResetSample(int32 Count) { int32 LocalCount = Count; }
            namespace Sample
            {
                bool bReady = false;
                void Refresh() {}
            }
            """,
        )
        result = self.source_result("ue_list_cxx_types.py")
        candidates = {
            item["name"]: item for item in result["interface_candidates"]
        }
        self.assertEqual(
            set(candidates),
            {"USampleInteractable", "ISampleInteractable"},
        )
        self.assertIn("uinterface_macro", candidates["USampleInteractable"]["reasons"])
        self.assertIn("paired_uinterface", candidates["ISampleInteractable"]["reasons"])
        self.assertEqual(
            {item["name"] for item in result["global_variables"]},
            {"GSampleCount", "bReady"},
        )
        self.assertEqual(
            {(item["name"], item["role"]) for item in result["free_functions"]},
            {
                ("ResetSample", "declaration"),
                ("ResetSample", "definition"),
                ("Refresh", "declaration"),
                ("Refresh", "definition"),
            },
        )

    def test_type_facts_report_namespaces_roles_and_linkage(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            namespace Outer::Inner
            {
                class FForward;
                struct FData {};
                enum class EMode : uint8;
                extern int32 GExternal;
                static int32 GHeaderInternal;
                const int32 GConstInternal = 1;
                inline const int32 GInlineExternal = 2;
                void Declared();
                static void Hidden();
            }
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            namespace Outer
            {
                namespace Inner
                {
                    int32 GExternal = 0;
                    static int32 GSourceInternal = 0;
                    void Declared() {}
                    static void Hidden() {}
                }
            }
            namespace
            {
                struct FAnonymous {};
                int32 GAnonymous = 0;
                void LocalOnly() {}
            }
            """,
        )
        result = self.source_result("ue_list_cxx_types.py")

        forward = next(
            item
            for item in result["classes"]
            if item["name"] == "FForward"
        )
        self.assertEqual(forward["namespace"], "Outer::Inner")
        self.assertEqual(
            forward["qualified_name"],
            "Outer::Inner::FForward",
        )
        anonymous_type = next(
            item
            for item in result["structs"]
            if item["name"] == "FAnonymous"
        )
        self.assertEqual(anonymous_type["namespace"], "(anonymous)")
        self.assertEqual(
            anonymous_type["qualified_name"],
            "(anonymous)::FAnonymous",
        )
        mode = next(
            item
            for item in result["enums"]
            if item["name"] == "EMode"
        )
        self.assertEqual(mode["namespace"], "Outer::Inner")
        self.assertEqual(
            mode["qualified_name"],
            "Outer::Inner::EMode",
        )

        globals_by_key = {
            (item["qualified_name"], item["role"]): item
            for item in result["global_variables"]
        }
        self.assertEqual(
            globals_by_key[
                ("Outer::Inner::GExternal", "declaration")
            ]["linkage"],
            "external",
        )
        self.assertEqual(
            globals_by_key[
                ("Outer::Inner::GExternal", "definition")
            ]["linkage"],
            "external",
        )
        for name in (
            "Outer::Inner::GHeaderInternal",
            "Outer::Inner::GConstInternal",
            "Outer::Inner::GSourceInternal",
            "(anonymous)::GAnonymous",
        ):
            self.assertEqual(
                globals_by_key[(name, "definition")]["linkage"],
                "internal",
            )
        self.assertEqual(
            globals_by_key[
                ("Outer::Inner::GInlineExternal", "definition")
            ]["linkage"],
            "external",
        )

        functions_by_key = {
            (
                item["qualified_name"],
                item["role"],
                item["evidence"]["unit"],
            ): item
            for item in result["free_functions"]
        }
        self.assertEqual(
            functions_by_key[
                ("Outer::Inner::Declared", "declaration", "header")
            ]["linkage"],
            "external",
        )
        self.assertEqual(
            functions_by_key[
                ("Outer::Inner::Declared", "definition", "cpp")
            ]["linkage"],
            "external",
        )
        self.assertEqual(
            functions_by_key[
                ("Outer::Inner::Hidden", "declaration", "header")
            ]["linkage"],
            "internal",
        )
        self.assertEqual(
            functions_by_key[
                ("Outer::Inner::Hidden", "definition", "cpp")
            ]["linkage"],
            "internal",
        )
        self.assertEqual(
            functions_by_key[
                ("(anonymous)::LocalOnly", "definition", "cpp")
            ]["linkage"],
            "internal",
        )

    def test_type_facts_classify_namespace_qualified_definitions(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            namespace Gameplay
            {
                extern int32 GCount;
                void Initialize();
            }
            namespace Outer::Inner
            {
                extern int32 GNestedCount;
                extern int32 GRelativeCount;
                void InitializeNested();
                void InitializeRelative();
            }
            class FSystem
            {
                static int32 GCount;
                static void Initialize();
            };
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            int32 Gameplay::GCount = 0;
            int32 Outer::Inner::GNestedCount = 0;
            int32 FSystem::GCount = 0;
            void Gameplay::Initialize() {}
            void Outer::Inner::InitializeNested() {}
            void FSystem::Initialize() {}
            namespace Outer
            {
                int32 Inner::GRelativeCount = 0;
                void Inner::InitializeRelative() {}
            }
            """,
        )
        result = self.source_result("ue_list_cxx_types.py")

        global_definitions = {
            item["qualified_name"]: item
            for item in result["global_variables"]
            if item["role"] == "definition"
        }
        self.assertEqual(
            set(global_definitions),
            {
                "Gameplay::GCount",
                "Outer::Inner::GNestedCount",
                "Outer::Inner::GRelativeCount",
            },
        )
        self.assertTrue(
            all(
                item["type_expression"] == "int32"
                and item["linkage"] == "external"
                for item in global_definitions.values()
            )
        )
        function_definitions = {
            item["qualified_name"]
            for item in result["free_functions"]
            if item["role"] == "definition"
        }
        self.assertEqual(
            function_definitions,
            {
                "Gameplay::Initialize",
                "Outer::Inner::InitializeNested",
                "Outer::Inner::InitializeRelative",
            },
        )
        function_result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Initialize",
        )
        matches_by_owner = {
            item["function"]["owner"]: item
            for item in function_result["matches"]
        }
        self.assertEqual(set(matches_by_owner), {None, "FSystem"})
        self.assertEqual(
            matches_by_owner[None]["relation"]["status"],
            "matched",
        )

    def test_type_facts_handle_forward_nested_and_namespace_shapes(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            template <class TClass> class TSubclassOf;
            struct FForward;
            enum EForward : int;
            class FOuter
            {
            public:
                class FNested { int32 Value; };
                static int32 Count;
            };
            class FFriended { friend FOuter; };
            int32 FindValue(int32 Input);
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            int32 FOuter::Count;
            namespace Console
            {
                static float Duration = 0.0f;
                static FAutoConsoleVariableRef CVarDuration(
                    TEXT("sample.Duration"), Duration);
            }
            int32 FindValue(int32 Input) { return Input; }
            """,
        )
        result = self.source_result("ue_list_cxx_types.py")
        classes = {item["qualified_name"]: item for item in result["classes"]}
        self.assertEqual(classes["TSubclassOf"]["role"], "declaration")
        self.assertEqual(classes["FOuter::FNested"]["owner"], "FOuter")
        self.assertEqual(
            classes["FOuter::FNested"]["member_anchors"][0]["name"],
            "Value",
        )
        self.assertEqual(classes["FFriended"]["member_anchors"], [])
        self.assertEqual(
            next(item for item in result["structs"] if item["name"] == "FForward")[
                "role"
            ],
            "declaration",
        )
        self.assertEqual(
            {item["name"] for item in result["global_variables"]},
            {"Duration", "CVarDuration"},
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
        self.assertEqual(match["function"]["owner"], "USampleObject")
        self.assertEqual(
            match["external_symbols"],
            [
                {
                    "kind": "type",
                    "spelling": "UObject",
                    "evidence": {"unit": "cpp", "line": 4},
                },
                {
                    "kind": "member_call",
                    "spelling": "UObject->GetWorld()",
                    "owner_type": "UObject",
                    "evidence": {"unit": "cpp", "line": 8},
                },
                {
                    "kind": "type",
                    "spelling": "TObjectPtr<UObject>",
                    "evidence": {"unit": "cpp", "line": 9},
                },
                {
                    "kind": "member_call",
                    "spelling": "TObjectPtr<UObject>->GetName()",
                    "owner_type": "TObjectPtr<UObject>",
                    "evidence": {"unit": "cpp", "line": 9},
                },
            ],
        )
        self.assertNotIn("external_types", match)
        self.assertNotIn("external_methods", match)

    def test_function_facts_keep_namespace_in_local_identity(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            namespace A
            {
                void Tick();
            }
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            namespace A
            {
                void Tick() {}
            }
            namespace B
            {
                void Tick() {}
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Tick",
        )

        self.assertEqual(result["match_count"], 2)
        matches = {
            item["function"]["qualified_name"]: item
            for item in result["matches"]
        }
        self.assertEqual(set(matches), {"A::Tick", "B::Tick"})
        self.assertEqual(
            matches["A::Tick"]["function"]["namespace"],
            "A",
        )
        self.assertEqual(
            matches["B::Tick"]["function"]["namespace"],
            "B",
        )
        self.assertEqual(
            matches["A::Tick"]["function_id"],
            "free_function|A||Tick|()|",
        )
        self.assertEqual(
            matches["B::Tick"]["function_id"],
            "free_function|B||Tick|()|",
        )
        self.assertEqual(
            matches["A::Tick"]["relation"]["status"],
            "matched",
        )
        self.assertEqual(
            matches["B::Tick"]["relation"]["status"],
            "source_only",
        )

    def test_function_facts_namespace_same_named_class_methods(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            namespace A
            {
                class FWorker
                {
                    void Run();
                };
            }
            namespace B
            {
                class FWorker
                {
                    void Run();
                };
            }
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            void A::FWorker::Run() {}
            void B::FWorker::Run() {}
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Run",
        )

        matches = {
            item["function"]["qualified_name"]: item
            for item in result["matches"]
        }
        self.assertEqual(
            set(matches),
            {"A::FWorker::Run", "B::FWorker::Run"},
        )
        self.assertEqual(
            matches["A::FWorker::Run"]["function_id"],
            "method|A|FWorker|Run|()|",
        )
        self.assertEqual(
            matches["B::FWorker::Run"]["function_id"],
            "method|B|FWorker|Run|()|",
        )
        self.assertTrue(
            all(
                item["relation"]["status"] == "matched"
                for item in matches.values()
            )
        )

    def test_function_facts_keep_nested_class_owner_chain(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            namespace A
            {
                class FOuterOne
                {
                    class FInner
                    {
                        void Run();
                    };
                };
                class FOuterTwo
                {
                    class FInner
                    {
                        void Run();
                    };
                };
            }
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            void A::FOuterOne::FInner::Run() {}
            void A::FOuterTwo::FInner::Run() {}
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Run",
        )

        matches = {
            item["function"]["qualified_name"]: item
            for item in result["matches"]
        }
        self.assertEqual(
            set(matches),
            {
                "A::FOuterOne::FInner::Run",
                "A::FOuterTwo::FInner::Run",
            },
        )
        self.assertEqual(
            matches[
                "A::FOuterOne::FInner::Run"
            ]["function"]["owner"],
            "FOuterOne::FInner",
        )
        self.assertEqual(
            matches[
                "A::FOuterTwo::FInner::Run"
            ]["function"]["owner"],
            "FOuterTwo::FInner",
        )
        self.assertEqual(
            matches[
                "A::FOuterOne::FInner::Run"
            ]["function_id"],
            "method|A|FOuterOne::FInner|Run|()|",
        )
        self.assertEqual(
            matches[
                "A::FOuterTwo::FInner::Run"
            ]["function_id"],
            "method|A|FOuterTwo::FInner|Run|()|",
        )
        self.assertTrue(
            all(
                item["relation"]["status"] == "matched"
                for item in matches.values()
            )
        )

    def test_function_reports_external_symbol_categories_with_evidence(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            struct FMyConfig {};
            class UMySystem
            {
            public:
                void Initialize();
            };
            extern UMySystem* GDefaultSystem;
            UMySystem* CreateDefaultSystem(const FMyConfig& Config);
            void HandleReady();
            class UConsumer
            {
            public:
                void Execute(const FMyConfig& Config);
                void HandleMember();
            private:
                FSimpleDelegate ReadyDelegate;
            };
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            void UConsumer::Execute(const FMyConfig& Config)
            {
                UMySystem* System = GDefaultSystem;
                if (!System)
                {
                    System = CreateDefaultSystem(Config);
                }
                System->Initialize();
                auto Factory = &CreateDefaultSystem;
                FCoreDelegates::OnPostEngineInit.AddStatic(&HandleReady);
                ReadyDelegate.BindUObject(this, &UConsumer::HandleMember);
                ExternalRegistry.Service();
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Execute",
        )
        symbols = result["matches"][0]["external_symbols"]
        self.assertEqual(
            symbols,
            [
                {
                    "kind": "type",
                    "spelling": "FMyConfig",
                    "evidence": {"unit": "cpp", "line": 2},
                },
                {
                    "kind": "type",
                    "spelling": "UMySystem",
                    "evidence": {"unit": "cpp", "line": 4},
                },
                {
                    "kind": "global_variable",
                    "spelling": "GDefaultSystem",
                    "evidence": {"unit": "cpp", "line": 4},
                },
                {
                    "kind": "free_function",
                    "spelling": "CreateDefaultSystem",
                    "evidence": {"unit": "cpp", "line": 7},
                },
                {
                    "kind": "member_call",
                    "spelling": "UMySystem->Initialize()",
                    "owner_type": "UMySystem",
                    "evidence": {"unit": "cpp", "line": 9},
                },
                {
                    "kind": "function_address",
                    "spelling": "CreateDefaultSystem",
                    "evidence": {"unit": "cpp", "line": 10},
                },
                {
                    "kind": "unknown",
                    "spelling": (
                        "FCoreDelegates::OnPostEngineInit."
                        "AddStatic(&HandleReady)"
                    ),
                    "evidence": {"unit": "cpp", "line": 11},
                },
                {
                    "kind": "callback_target",
                    "spelling": "HandleReady",
                    "evidence": {"unit": "cpp", "line": 11},
                },
                {
                    "kind": "type",
                    "spelling": "FSimpleDelegate",
                    "evidence": {"unit": "cpp", "line": 12},
                },
                {
                    "kind": "member_call",
                    "spelling": (
                        "FSimpleDelegate.BindUObject("
                        "this, &UConsumer::HandleMember)"
                    ),
                    "owner_type": "FSimpleDelegate",
                    "evidence": {"unit": "cpp", "line": 12},
                },
                {
                    "kind": "callback_target",
                    "spelling": "UConsumer::HandleMember",
                    "owner_type": "UConsumer",
                    "evidence": {"unit": "cpp", "line": 12},
                },
                {
                    "kind": "unknown",
                    "spelling": "ExternalRegistry.Service()",
                    "evidence": {"unit": "cpp", "line": 13},
                },
            ],
        )

    def test_function_calls_require_confirmed_symbol_categories(self) -> None:
        write_text(self.fixture.header_file, "#pragma once")
        write_text(
            self.fixture.source_file,
            """
            class UConsumer
            {
                TFunction<void()> MemberCallback;
                void Execute(TFunction<void()> Callback);
            };
            class FConfirmedType
            {
            public:
                static void Sort();
            };
            void UConsumer::Execute(TFunction<void()> Callback)
            {
                TFunction<void()> LocalCallback = Callback;
                Callback();
                LocalCallback();
                MemberCallback();
                Algo::Sort(Values);
                FConfirmedType::Sort();
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Execute",
        )
        self.assertEqual(
            result["matches"][0]["external_symbols"],
            [
                {
                    "kind": "type",
                    "spelling": "TFunction<void()>",
                    "evidence": {"unit": "cpp", "line": 11},
                },
                {
                    "kind": "unknown",
                    "spelling": "Algo::Sort(Values)",
                    "evidence": {"unit": "cpp", "line": 17},
                },
                {
                    "kind": "type",
                    "spelling": "FConfirmedType",
                    "evidence": {"unit": "cpp", "line": 18},
                },
                {
                    "kind": "member_call",
                    "spelling": "FConfirmedType::Sort()",
                    "owner_type": "FConfirmedType",
                    "evidence": {"unit": "cpp", "line": 18},
                },
            ],
        )

    def test_function_bare_calls_require_local_callable_facts(self) -> None:
        write_text(self.fixture.header_file, "#pragma once")
        write_text(
            self.fixture.source_file,
            """
            void DeclaredFree();
            class UChild
            {
            public:
                void Run();
                void LocalMethod();
            };
            void UChild::Run()
            {
                DeclaredFree();
                LocalMethod();
                Refresh();
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Run",
        )
        self.assertEqual(
            result["matches"][0]["external_symbols"],
            [
                {
                    "kind": "free_function",
                    "spelling": "DeclaredFree",
                    "evidence": {"unit": "cpp", "line": 10},
                },
                {
                    "kind": "member_call",
                    "spelling": "UChild->LocalMethod()",
                    "owner_type": "UChild",
                    "evidence": {"unit": "cpp", "line": 11},
                },
                {
                    "kind": "unknown",
                    "spelling": "Refresh()",
                    "evidence": {"unit": "cpp", "line": 12},
                },
            ],
        )

    def test_function_preserves_qualified_global_variable_spelling(self) -> None:
        write_text(self.fixture.header_file, "#pragma once")
        write_text(
            self.fixture.source_file,
            """
            namespace Gameplay
            {
                extern bool GEnabled;
            }
            class FObject
            {
            public:
                static bool GEnabled;
            };
            void CheckGlobals(FObject* Object)
            {
                FObject ObjectValue;
                if (Gameplay::GEnabled) {}
                if (ObjectValue.GEnabled) {}
                if (Object->GEnabled) {}
                if (FObject::GEnabled) {}
                if (GPlainEnabled) {}
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "CheckGlobals",
        )
        symbols = result["matches"][0]["external_symbols"]
        self.assertEqual(
            [
                item
                for item in symbols
                if item["kind"] == "global_variable"
            ],
            [
                {
                    "kind": "global_variable",
                    "spelling": "Gameplay::GEnabled",
                    "evidence": {"unit": "cpp", "line": 13},
                },
                {
                    "kind": "global_variable",
                    "spelling": "GPlainEnabled",
                    "evidence": {"unit": "cpp", "line": 17},
                },
            ],
        )
        self.assertEqual(
            {
                item["spelling"]
                for item in symbols
                if item["kind"] == "unknown"
            },
            {
                "ObjectValue.GEnabled",
                "Object->GEnabled",
                "FObject::GEnabled",
            },
        )

    def test_function_requires_qualified_namespace_global_evidence(self) -> None:
        write_text(self.fixture.header_file, "#pragma once")
        write_text(
            self.fixture.source_file,
            """
            namespace A
            {
                extern int Value;
            }

            namespace B
            {
                void Run()
                {
                    B::Value;
                    A::Value;
                    B::GHeuristic;
                }
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Run",
        )
        self.assertEqual(
            result["matches"][0]["external_symbols"],
            [
                {
                    "kind": "unknown",
                    "spelling": "B::Value",
                    "evidence": {"unit": "cpp", "line": 10},
                },
                {
                    "kind": "global_variable",
                    "spelling": "A::Value",
                    "evidence": {"unit": "cpp", "line": 11},
                },
                {
                    "kind": "global_variable",
                    "spelling": "B::GHeuristic",
                    "evidence": {"unit": "cpp", "line": 12},
                },
            ],
        )

    def test_function_uses_namespace_facts_for_calls_and_addresses(self) -> None:
        write_text(self.fixture.header_file, "#pragma once")
        write_text(
            self.fixture.source_file,
            """
            namespace Gameplay
            {
                void Create();
                void Handle();
            }
            class FHandler
            {
            public:
                static void Handle();
            };
            void TestNamespaceReferences()
            {
                Gameplay::Create();
                Unknown::Create();
                auto Callback = &Gameplay::Handle;
                auto Member = &FHandler::Handle;
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "TestNamespaceReferences",
        )
        self.assertEqual(
            result["matches"][0]["external_symbols"],
            [
                {
                    "kind": "free_function",
                    "spelling": "Gameplay::Create",
                    "evidence": {"unit": "cpp", "line": 13},
                },
                {
                    "kind": "unknown",
                    "spelling": "Unknown::Create()",
                    "evidence": {"unit": "cpp", "line": 14},
                },
                {
                    "kind": "function_address",
                    "spelling": "Gameplay::Handle",
                    "evidence": {"unit": "cpp", "line": 15},
                },
                {
                    "kind": "function_address",
                    "spelling": "FHandler::Handle",
                    "owner_type": "FHandler",
                    "evidence": {"unit": "cpp", "line": 16},
                },
                {
                    "kind": "type",
                    "spelling": "FHandler",
                    "evidence": {"unit": "cpp", "line": 16},
                },
            ],
        )

    def test_function_resolves_member_address_in_current_namespace(self) -> None:
        write_text(self.fixture.header_file, "#pragma once")
        write_text(
            self.fixture.source_file,
            """
            namespace A
            {
                class FHandler
                {
                public:
                    static void Handle();
                };
                void Test()
                {
                    auto P = &FHandler::Handle;
                }
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Test",
        )
        self.assertEqual(
            result["matches"][0]["external_symbols"],
            [
                {
                    "kind": "function_address",
                    "spelling": "FHandler::Handle",
                    "owner_type": "FHandler",
                    "evidence": {"unit": "cpp", "line": 10},
                },
                {
                    "kind": "type",
                    "spelling": "FHandler",
                    "evidence": {"unit": "cpp", "line": 10},
                },
            ],
        )

    def test_same_name_overloads_have_stable_unique_ids(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            class USampleObject
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
            #include "SampleFeature.h"
            void USampleObject::Execute(UObject* Context) const {}
            void USampleObject::Execute(int32 Count) {}
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

    def test_missing_function_is_structured_scan_error(self) -> None:
        result = self.source_result(
            "ue_inspect_cxx_function.py",
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


if __name__ == "__main__":
    import unittest

    unittest.main()
