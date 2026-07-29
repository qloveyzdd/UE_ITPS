from __future__ import annotations

from tests.cxx_support import CxxAnalysisTestCase
from tests.support import write_text


class CxxTypeTests(CxxAnalysisTestCase):
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

