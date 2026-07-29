from __future__ import annotations

from tests.fixture import write_text
from tests.source_layer_case import SourceLayerTestCase


class SourceTypeTests(SourceLayerTestCase):
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
