from __future__ import annotations

from pathlib import Path
import tempfile

from tools.ue_project_tools.source_unit import list_source_types

from tests.support import EnvelopeAssertions, create_fixture, write_text


class SourceTypeTests(EnvelopeAssertions):
    def test_types_report_shape_members_and_reflection_macros(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            result = list_source_types(fixture.source_file)

        self.assert_envelope(result)
        by_name = {item["name"]: item for item in result["types"]}
        feature = by_name["FFixtureFeature"]
        self.assertEqual(feature["kind"], "struct")
        self.assertIn("USTRUCT(BlueprintType)", feature["macros"])
        self.assertEqual(
            feature["member_details"]["variables"][0]["name"],
            "Tag",
        )
        self.assertIn(
            "UPROPERTY(EditAnywhere)",
            feature["member_details"]["variables"][0]["macros"],
        )

        fixture_object = by_name["UFixtureObject"]
        self.assertEqual(fixture_object["base_types"], ["UObject"])
        self.assertEqual(
            fixture_object["member_details"]["functions"][0]["name"],
            "Execute",
        )

    def test_enum_and_interface_macros_attach_to_lexical_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            write_text(
                fixture.header_file,
                """
                #pragma once
                #include "Feature.generated.h"

                UENUM(BlueprintType)
                enum class EFixtureMode : uint8
                {
                    One,
                    Two
                };

                UINTERFACE(MinimalAPI)
                class UFixtureInterface : public UInterface
                {
                    GENERATED_BODY()
                };

                class IFixtureInterface
                {
                    GENERATED_BODY()
                };
                """,
            )
            result = list_source_types(fixture.source_file)

        by_name = {item["name"]: item for item in result["types"]}
        self.assertIn("UENUM(BlueprintType)", by_name["EFixtureMode"]["macros"])
        self.assertIn(
            "UINTERFACE(MinimalAPI)",
            by_name["UFixtureInterface"]["macros"],
        )
        self.assertNotIn(
            "UINTERFACE(MinimalAPI)",
            by_name["IFixtureInterface"]["macros"],
        )

    def test_elaborated_parameter_does_not_create_a_type_definition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            write_text(
                fixture.header_file,
                """
                #pragma once
                class UFixtureObject
                {
                public:
                    void Use(class UForwardDeclared* Value);
                };
                """,
            )
            result = list_source_types(fixture.source_file)

        names = {item["name"] for item in result["types"]}
        self.assertEqual(names, {"UFixtureObject"})
        self.assertNotIn("UForwardDeclared", names)
