from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
sys.path.insert(0, str(TOOLS_ROOT))

from ue_project_tools.source_unit import (  # noqa: E402
    inspect_source_function,
    list_source_functions,
    list_source_includes,
    list_source_types,
)


class SourceUnitTests(unittest.TestCase):
    def write_fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        project_root = root / "Project"
        engine_root = root / "Engine"
        module_root = project_root / "Source" / "Fixture"
        private_root = module_root / "Private"
        public_root = module_root / "Public"
        plugin_root = engine_root / "Engine" / "Plugins" / "Demo"
        plugin_module = plugin_root / "Source" / "Demo"
        private_root.mkdir(parents=True)
        public_root.mkdir(parents=True)
        (plugin_module / "Public").mkdir(parents=True)
        (engine_root / "Engine" / "Build").mkdir(parents=True)

        project = project_root / "Fixture.uproject"
        project.write_text(
            json.dumps(
                {
                    "FileVersion": 3,
                    "EngineAssociation": "../Engine",
                    "Modules": [{"Name": "Fixture", "Type": "Runtime"}],
                    "Plugins": [],
                }
            ),
            encoding="utf-8",
        )
        (engine_root / "Engine" / "Build" / "Build.version").write_text(
            json.dumps(
                {"MajorVersion": 5, "MinorVersion": 6, "PatchVersion": 1}
            ),
            encoding="utf-8",
        )
        (module_root / "Fixture.Build.cs").write_text(
            "public class Fixture : ModuleRules {}", encoding="utf-8"
        )
        (plugin_root / "Demo.uplugin").write_text(
            json.dumps(
                {
                    "FileVersion": 3,
                    "Modules": [{"Name": "Demo", "Type": "Runtime"}],
                }
            ),
            encoding="utf-8",
        )
        (plugin_module / "Demo.Build.cs").write_text(
            "public class Demo : ModuleRules {}", encoding="utf-8"
        )
        (plugin_module / "Public" / "ExternalThing.h").write_text(
            "struct FExternalThing { // deliberately malformed and never read\n",
            encoding="utf-8",
        )

        header = public_root / "Thing.h"
        header.write_text(
            """
#pragma once
#include "ExternalThing.h"
#include "Thing.generated.h"

class UForward;

USTRUCT(BlueprintType)
struct FThing
{
    GENERATED_BODY()

    UPROPERTY()
    int32 Count = 0;

    UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category="Fixture")
    void Run(int32 Value) const;
};
""",
            encoding="utf-8",
        )
        source = private_root / "Thing.cpp"
        source.write_text(
            """
#include "Thing.h"
#include UE_INLINE_GENERATED_CPP_BY_NAME(Thing)

static int32 GCount = 1;

void FThing::Run(int32 Value) const
{
    int32 LocalValue = Value;
    if (LocalValue > 0)
    {
        ExternalCall(LocalValue);
    }
}

int32 MakeThing()
{
    FThing* Value = new FThing();
    return 1;
}
""",
            encoding="utf-8",
        )
        return project, engine_root, source, header

    def assert_common_context(self, result: dict[str, object]) -> None:
        self.assertEqual(list(result)[0], "schema_version")
        self.assertEqual(list(result)[-2:], ["validation", "limits"])
        self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(
            result["context"]["project_descriptor"], "Fixture.uproject"
        )
        self.assertEqual(
            result["context"]["project_discovery_method"],
            "nearest-source-ancestor",
        )
        self.assertEqual(
            result["source_unit"]["header"]["path"],
            "Source/Fixture/Public/Thing.h",
        )

    def test_include_tool_reports_unique_provenance_without_recursion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, _ = self.write_fixture(
                Path(temporary_directory)
            )
            result = list_source_includes(
                source, engine_override=engine_root
            )

        self.assert_common_context(result)
        self.assertEqual(
            result["schema_version"], "ue-itps.source-includes.v1"
        )
        self.assertNotIn(
            "Thing.h",
            {item["spelling"] for item in result["includes"]},
        )
        external = next(
            item
            for item in result["includes"]
            if item["spelling"] == "ExternalThing.h"
        )
        self.assertEqual(
            external["evidence"],
            {"unit": "header", "line": 3},
        )
        self.assertNotIn("origin_unit", external)
        self.assertNotIn("syntax", external)
        self.assertNotIn("status", external["resolution"])
        self.assertEqual(
            external["resolution"]["owner"],
            {
                "kind": "engine_plugin_module",
            },
        )
        generated_statuses = {
            item["spelling"]: item["resolution"].get("status")
            for item in result["includes"]
            if item["spelling"]
            in {
                "UE_INLINE_GENERATED_CPP_BY_NAME(Thing)",
                "Thing.generated.h",
            }
        }
        self.assertEqual(
            generated_statuses,
            {
                "UE_INLINE_GENERATED_CPP_BY_NAME(Thing)": "generated_source",
                "Thing.generated.h": "generated_header",
            },
        )
        self.assertNotIn("types", result)
        self.assertNotIn("functions", result)

    def test_type_tool_lists_type_shape_without_semantic_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, _ = self.write_fixture(
                Path(temporary_directory)
            )
            result = list_source_types(source, engine_override=engine_root)

        self.assert_common_context(result)
        self.assertEqual(result["schema_version"], "ue-itps.source-types.v1")
        type_fact = next(item for item in result["types"] if item["name"] == "FThing")
        self.assertEqual(type_fact["kind"], "struct")
        self.assertNotIn("member_variables", type_fact)
        self.assertNotIn("member_functions", type_fact)
        self.assertNotIn("type_macros", result)
        self.assertEqual(
            type_fact["macros"],
            ["USTRUCT(BlueprintType)", "GENERATED_BODY()"],
        )
        variables = type_fact["member_details"]["variables"]
        functions = type_fact["member_details"]["functions"]
        self.assertEqual([item["name"] for item in variables], ["Count"])
        self.assertEqual(variables[0]["macros"], ["UPROPERTY()"])
        self.assertEqual(variables[0]["evidence"]["unit"], "header")
        self.assertNotIn("root", variables[0]["evidence"])
        self.assertNotIn("path", variables[0]["evidence"])
        self.assertEqual([item["name"] for item in functions], ["Run"])
        self.assertEqual(
            functions[0]["macros"],
            [
                "UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, "
                'Category="Fixture")'
            ],
        )
        self.assertEqual(functions[0]["evidence"]["unit"], "header")
        self.assertEqual(type_fact["evidence"]["unit"], "header")
        self.assertEqual(type_fact["evidence"]["line"], 8)
        self.assertNotIn("root", type_fact["evidence"])
        self.assertNotIn("path", type_fact["evidence"])
        self.assertNotIn("summary", type_fact)

    def test_type_tool_attaches_reflection_macros_without_polluting_declarations(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, header = self.write_fixture(
                Path(temporary_directory)
            )
            header.write_text(
                """
#pragma once
UCLASS()
class UReflectedFixture
{
    GENERATED_BODY()

public:
    UReflectedFixture();

    UFUNCTION(BlueprintCallable, Category = "Fixture")
    void Run();

private:
    UPROPERTY(EditAnywhere)
    int32 Count = 0;
};
""",
                encoding="utf-8",
            )
            source.write_text('#include "Thing.h"\n', encoding="utf-8")

            result = list_source_types(
                source, engine_override=engine_root
            )

        reflected = next(
            item
            for item in result["types"]
            if item["name"] == "UReflectedFixture"
        )
        variables = reflected["member_details"]["variables"]
        functions = reflected["member_details"]["functions"]
        self.assertEqual(
            reflected["macros"], ["UCLASS()", "GENERATED_BODY()"]
        )
        self.assertEqual(
            reflected["evidence"],
            {"unit": "header", "line": 3, "end_line": 17},
        )
        self.assertEqual(
            [(item["name"], item["type_expression"]) for item in variables],
            [("Count", "int32")],
        )
        self.assertEqual(variables[0]["macros"], ["UPROPERTY(EditAnywhere)"])
        self.assertEqual(
            [(item["name"], item["signature"]) for item in functions],
            [
                ("UReflectedFixture", "UReflectedFixture()"),
                ("Run", "void Run()"),
            ],
        )
        self.assertEqual(
            functions[1]["macros"],
            ['UFUNCTION(BlueprintCallable, Category = "Fixture")'],
        )
        self.assertEqual(result["validation"]["status"], "ok")

    def test_type_tool_attaches_uenum_and_uinterface_macros(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, header = self.write_fixture(
                Path(temporary_directory)
            )
            header.write_text(
                """
#pragma once
UENUM(BlueprintType)
enum class EFixtureMode : uint8
{
    First,
    Second,
};

UINTERFACE(MinimalAPI)
class UFixtureInterface : public UInterface
{
    GENERATED_BODY()
};
""",
                encoding="utf-8",
            )
            source.write_text('#include "Thing.h"\n', encoding="utf-8")

            result = list_source_types(
                source, engine_override=engine_root
            )

        enum_type = next(
            item
            for item in result["types"]
            if item["name"] == "EFixtureMode"
        )
        interface_type = next(
            item
            for item in result["types"]
            if item["name"] == "UFixtureInterface"
        )
        self.assertEqual(enum_type["kind"], "enum")
        self.assertTrue(enum_type["scoped"])
        self.assertEqual(enum_type["macros"], ["UENUM(BlueprintType)"])
        self.assertEqual(
            enum_type["evidence"],
            {"unit": "header", "line": 3, "end_line": 8},
        )
        self.assertEqual(interface_type["kind"], "class")
        self.assertEqual(interface_type["base_types"], ["UInterface"])
        self.assertEqual(
            interface_type["macros"],
            ["UINTERFACE(MinimalAPI)", "GENERATED_BODY()"],
        )
        self.assertEqual(
            interface_type["evidence"],
            {"unit": "header", "line": 10, "end_line": 14},
        )
        self.assertEqual(result["validation"]["status"], "ok")

    def test_type_tool_attaches_multiline_macros_inside_if_blocks(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, header = self.write_fixture(
                Path(temporary_directory)
            )
            header.write_text(
                """
#pragma once
#if WITH_EDITOR
UCLASS(
    BlueprintType,
    meta=(DisplayName="Conditional Fixture")
)
class UConditionalFixture
{
    GENERATED_BODY()

#if WITH_EDITORONLY_DATA
    UPROPERTY(
        EditAnywhere,
        Category = "Fixture"
    )
    int32 Count = 0;
#endif

#if WITH_EDITOR
    UFUNCTION(
        BlueprintCallable,
        Category = "Fixture"
    )
    void Run();
#endif
};
#endif
""",
                encoding="utf-8",
            )
            source.write_text('#include "Thing.h"\n', encoding="utf-8")

            result = list_source_types(
                source, engine_override=engine_root
            )

        conditional = next(
            item
            for item in result["types"]
            if item["name"] == "UConditionalFixture"
        )
        variables = conditional["member_details"]["variables"]
        functions = conditional["member_details"]["functions"]
        self.assertEqual(
            conditional["macros"],
            [
                'UCLASS( BlueprintType, meta=(DisplayName="Conditional '
                'Fixture") )',
                "GENERATED_BODY()",
            ],
        )
        self.assertEqual(conditional["evidence"]["line"], 4)
        self.assertEqual([item["name"] for item in variables], ["Count"])
        self.assertEqual(
            variables[0]["macros"],
            ['UPROPERTY( EditAnywhere, Category = "Fixture" )'],
        )
        self.assertEqual([item["name"] for item in functions], ["Run"])
        self.assertEqual(
            functions[0]["macros"],
            ['UFUNCTION( BlueprintCallable, Category = "Fixture" )'],
        )
        self.assertEqual(result["validation"]["status"], "ok")

    def test_function_index_and_selected_function_detail_stay_separate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, _ = self.write_fixture(
                Path(temporary_directory)
            )
            index = list_source_functions(
                source, engine_override=engine_root
            )
            detail = inspect_source_function(
                source,
                "Run",
                engine_override=engine_root,
            )

        self.assert_common_context(index)
        self.assertEqual(
            index["schema_version"], "ue-itps.source-functions.v1"
        )
        run = next(
            item
            for item in index["functions"]
            if item["owner"] == "FThing" and item["name"] == "Run"
        )
        self.assertEqual(run["relation"], "matched")
        self.assertNotIn("operations", index)

        self.assertEqual(
            detail["schema_version"], "ue-itps.source-function.v1"
        )
        self.assertEqual(detail["selection"], {"name": "Run"})
        self.assertEqual(detail["match_count"], 1)
        match = detail["matches"][0]
        self.assertEqual(match["function"]["name"], "Run")
        self.assertNotIn("function_id", match["function"])
        self.assertNotIn("parameter_signature", match["function"])
        self.assertNotIn("evidence", match["function"])
        self.assertEqual(
            list(match["relation"]),
            ["status", "declarations", "definitions"],
        )
        self.assertNotIn("operations", match)
        self.assertNotIn("body", match)
        self.assertEqual(match["external_types"], [])
        self.assertEqual(match["external_methods"], [])

    def test_callable_template_member_is_a_variable_not_a_void_function(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, header = self.write_fixture(
                Path(temporary_directory)
            )
            header.write_text(
                """
#pragma once

struct FCallableFixture
{
    TFunction<void(const FCallableFixture&, int32&)> JobFunc;
    void (*Callback)(int32);
    void (FCallableFixture::*MemberCallback)(int32) const;
    void Run();
};
""",
                encoding="utf-8",
            )

            types = list_source_types(source, engine_override=engine_root)
            functions = list_source_functions(
                source, engine_override=engine_root
            )

        type_fact = next(
            item
            for item in types["types"]
            if item["name"] == "FCallableFixture"
        )
        self.assertEqual(
            [
                item["name"]
                for item in type_fact["member_details"]["variables"]
            ],
            ["JobFunc", "Callback", "MemberCallback"],
        )
        self.assertEqual(
            [
                item["name"]
                for item in type_fact["member_details"]["functions"]
            ],
            ["Run"],
        )
        variable_details = {
            item["name"]: item
            for item in type_fact["member_details"]["variables"]
        }
        function_details = {
            item["name"]: item
            for item in type_fact["member_details"]["functions"]
        }
        self.assertEqual(
            variable_details["JobFunc"]["evidence"]["line"], 6
        )
        self.assertEqual(
            function_details["Run"]["evidence"]["line"], 9
        )
        self.assertNotIn(
            "void", {item["name"] for item in functions["functions"]}
        )
        self.assertEqual(types["validation"]["status"], "ok")
        self.assertEqual(functions["validation"]["status"], "ok")

    def test_unresolved_declaration_is_reported_by_remaining_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, header = self.write_fixture(
                Path(temporary_directory)
            )
            header.write_text(
                """
#pragma once
struct FAmbiguous
{
    int32 First, Second;
};
""",
                encoding="utf-8",
            )

            types = list_source_types(source, engine_override=engine_root)
            functions = list_source_functions(
                source, engine_override=engine_root
            )

        self.assertEqual(types["validation"]["status"], "warning")
        self.assertEqual(
            types["unresolved_declarations"][0]["reason"],
            "multiple_declarators",
        )
        self.assertEqual(functions["validation"]["status"], "warning")
        self.assertEqual(
            functions["unresolved_declarations"][0]["reason"],
            "multiple_declarators",
        )

    def test_function_ids_and_precise_relations_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, header = self.write_fixture(
                Path(temporary_directory)
            )
            header.write_text(
                """
#pragma once
struct FRelations
{
    void Matched() const;
    void Inline() const {}
    void DeclarationOnly();
    void Overloaded() { NonConstCall(); }
    void Overloaded() const { ConstCall(); }
};
struct FOtherRelations
{
    void Overloaded();
};
""",
                encoding="utf-8",
            )
            source.write_text(
                """
#include "Thing.h"
void FRelations::Matched() const {}
void FOtherRelations::Overloaded() { OtherCall(); }
void SourceOnly() {}
""",
                encoding="utf-8",
            )

            first = list_source_functions(
                source, engine_override=engine_root
            )
            second = list_source_functions(
                source, engine_override=engine_root
            )
            inline = next(
                item
                for item in first["functions"]
                if item["name"] == "Inline"
            )
            detail = inspect_source_function(
                source,
                "Inline",
                engine_override=engine_root,
            )
            overloaded_detail = inspect_source_function(
                source,
                "Overloaded",
                engine_override=engine_root,
            )

        self.assertEqual(first, second)
        relations = {
            item["name"]: item["relation"] for item in first["functions"]
        }
        self.assertEqual(relations["Matched"], "matched")
        self.assertEqual(relations["Inline"], "inline_definition")
        self.assertEqual(relations["DeclarationOnly"], "declaration_only")
        self.assertEqual(relations["SourceOnly"], "source_only")
        overloads = [
            item
            for item in first["functions"]
            if item["name"] == "Overloaded"
        ]
        self.assertEqual(len(overloads), 3)
        self.assertEqual(
            len({item["function_id"] for item in overloads}), 3
        )
        self.assertEqual(detail["match_count"], 1)
        self.assertEqual(
            detail["matches"][0]["function_id"], inline["function_id"]
        )
        self.assertEqual(overloaded_detail["validation"]["status"], "ok")
        self.assertEqual(overloaded_detail["match_count"], 3)
        self.assertEqual(
            [
                (
                    item["function"]["owner"],
                    item["function"]["qualifiers"],
                )
                for item in overloaded_detail["matches"]
            ],
            [
                ("FOtherRelations", []),
                ("FRelations", []),
                ("FRelations", ["const"]),
            ],
        )
        other_match = overloaded_detail["matches"][0]
        self.assertEqual(other_match["external_types"], [])
        self.assertEqual(other_match["external_methods"], [])
        self.assertTrue(
            all("body" not in item for item in overloaded_detail["matches"])
        )

    def test_qualified_calls_are_not_definitions_and_destructor_keeps_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, header = self.write_fixture(
                Path(temporary_directory)
            )
            header.write_text(
                """
#pragma once
namespace Demo
{
struct FScoped
{
    int32 Value;
    FScoped();
    ~FScoped();
    void Run();
};
}
""",
                encoding="utf-8",
            )
            source.write_text(
                """
#include "Thing.h"
namespace Demo
{
FScoped::FScoped() : Value{0} {}
FScoped::~FScoped() {}
void FScoped::Run()
{
    if (FParse::Value(FCommandLine::Get(), TEXT("x"), Value))
    {
        Super::Run();
    }
}
}
""",
                encoding="utf-8",
            )

            functions = list_source_functions(
                source, engine_override=engine_root
            )
            fake_detail = inspect_source_function(
                source,
                "Get",
                engine_override=engine_root,
            )

        identities = {
            (item["owner"], item["name"]): item
            for item in functions["functions"]
        }
        self.assertEqual(
            set(identities),
            {
                ("FScoped", "FScoped"),
                ("FScoped", "~FScoped"),
                ("FScoped", "Run"),
            },
        )
        self.assertEqual(identities[("FScoped", "FScoped")]["relation"], "matched")
        self.assertEqual(identities[("FScoped", "~FScoped")]["relation"], "matched")
        self.assertEqual(identities[("FScoped", "Run")]["relation"], "matched")
        self.assertEqual(
            identities[("FScoped", "~FScoped")]["function_id"],
            "method|FScoped|~FScoped|()|",
        )
        self.assertEqual(fake_detail["validation"]["status"], "error")
        self.assertEqual(
            fake_detail["validation"]["problems"][0]["code"],
            "function-not-found",
        )

    def test_elaborated_parameter_does_not_create_type_or_keyword_callable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, header = self.write_fixture(
                Path(temporary_directory)
            )
            header.write_text(
                """
#pragma once
class FArchive;
struct FPacket
{
    bool NetSerialize(FArchive& Ar, class UPackageMap* Map, bool& bOutSuccess);
};
enum class EMode
{
    First
};
template<class T>
struct TBox
{
    T Value;
};
template<class T>
struct TTraits
{
};
template<>
struct TTraits<FPacket>
{
};
""",
                encoding="utf-8",
            )
            source.write_text(
                """
#include "Thing.h"
bool FPacket::NetSerialize(FArchive& Ar, class UPackageMap* Map, bool& bOutSuccess)
{
    bool bHasTimeStamp = true;
    if (bHasTimeStamp)
    {
        return true;
    }
    return false;
}
""",
                encoding="utf-8",
            )

            types = list_source_types(source, engine_override=engine_root)
            functions = list_source_functions(
                source, engine_override=engine_root
            )
            fake_detail = inspect_source_function(
                source,
                "if",
                engine_override=engine_root,
            )

        type_items = types["types"]
        self.assertNotIn(
            "bOutSuccess", {item["name"] for item in type_items}
        )
        self.assertEqual(
            sum(item["name"] == "EMode" for item in type_items), 1
        )
        self.assertEqual(
            next(item for item in type_items if item["name"] == "EMode")[
                "kind"
            ],
            "enum",
        )
        self.assertEqual(
            sum(item["name"] == "TBox" for item in type_items), 1
        )
        self.assertEqual(
            sum(item["name"] == "FPacket" for item in type_items), 1
        )
        self.assertEqual(
            sum(item["name"] == "TTraits" for item in type_items), 2
        )
        self.assertEqual(
            {item["name"] for item in functions["functions"]},
            {"NetSerialize"},
        )
        self.assertEqual(fake_detail["validation"]["status"], "error")
        self.assertEqual(
            fake_detail["validation"]["problems"][0]["code"],
            "function-not-found",
        )

    def test_members_after_inline_bodies_remain_variable_details(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, header = self.write_fixture(
                Path(temporary_directory)
            )
            header.write_text(
                """
#pragma once
struct FInlineMembers
{
    void Inline() {}
    int32 First = 1;

    template<typename T>
    bool Change(T& Value)
    {
        return true;
    }

    bool Last = false;
};
""",
                encoding="utf-8",
            )
            source.write_text('#include "Thing.h"\n', encoding="utf-8")

            types = list_source_types(
                source, engine_override=engine_root
            )

        projected = next(
            item for item in types["types"] if item["name"] == "FInlineMembers"
        )
        self.assertEqual(types["validation"]["status"], "ok")
        self.assertEqual(
            [
                item["name"]
                for item in projected["member_details"]["variables"]
            ],
            ["First", "Last"],
        )

    def test_reflected_class_closing_brace_is_not_an_unresolved_declaration(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, header = self.write_fixture(
                Path(temporary_directory)
            )
            header.write_text(
                """
#pragma once
USTRUCT()
struct FPreviewSettings
{
    GENERATED_BODY()

    int32 Count = 0;
};

UCLASS()
class FIXTURE_API UFixtureNotify
{
    GENERATED_BODY()

public:
    UE_API UFixtureNotify();

private:
#if WITH_EDITORONLY_DATA
    UPROPERTY()
    FPreviewSettings PreviewSettings;
#endif
};
""",
                encoding="utf-8",
            )
            source.write_text('#include "Thing.h"\n', encoding="utf-8")

            functions = list_source_functions(
                source, engine_override=engine_root
            )

        self.assertEqual(functions["validation"]["status"], "ok")
        self.assertFalse(functions["unresolved_declarations"])

    def test_function_external_types_and_methods_use_local_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, header = self.write_fixture(
                Path(temporary_directory)
            )
            external_header = header.parent / "ExternalApi.h"
            external_header.write_text(
                "struct FExternalApi { // deliberately malformed and never read\n",
                encoding="utf-8",
            )
            header.write_text(
                """
#pragma once
struct FExternalApi;
struct FLocalType;
struct FMemberType;
struct FSecondLocalType;
template <typename T> class TWrapper;
struct FUnusedType;
struct FOperations
{
    TWrapper<FExternalApi> UsedApi;
    FUnusedType UnusedValue;
    FMemberType Shadowed;
    FMemberType LocalShadowed;
    void Run(FLocalType Shadowed);
};
""",
                encoding="utf-8",
            )
            source.write_text(
                """
#include "Thing.h"
#include "ExternalApi.h"
void FOperations::Run(FLocalType Shadowed)
{
    FSecondLocalType LocalShadowed;
    Shadowed->Call();
    LocalShadowed->Ping();
    UsedApi->Call<FExternalApi>();
    Unknown->Missing();
}
""",
                encoding="utf-8",
            )

            result = inspect_source_function(
                source,
                "Run",
                engine_override=engine_root,
            )

        self.assertEqual(result["match_count"], 1)
        match = result["matches"][0]
        self.assertNotIn("operations", match)
        self.assertNotIn("body", match)
        self.assertEqual(
            match["external_types"],
            [
                "FLocalType",
                "FSecondLocalType",
                "TWrapper<FExternalApi>",
            ],
        )
        self.assertEqual(
            match["external_methods"],
            [
                "FLocalType->Call()",
                "FSecondLocalType->Ping()",
                "TWrapper<FExternalApi>->Call<FExternalApi>()",
                "Unknown->Missing()",
            ],
        )

    def test_include_evidence_identifies_cpp_or_header(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, _ = self.write_fixture(
                Path(temporary_directory)
            )
            result = list_source_includes(
                source, engine_override=engine_root
            )

        evidence_units = {
            item["spelling"]: item["evidence"]["unit"]
            for item in result["includes"]
        }
        self.assertNotIn("Thing.h", evidence_units)
        self.assertEqual(
            evidence_units["UE_INLINE_GENERATED_CPP_BY_NAME(Thing)"],
            "cpp",
        )
        self.assertEqual(evidence_units["ExternalThing.h"], "header")

    def test_missing_function_is_a_structured_cli_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, _ = self.write_fixture(
                Path(temporary_directory)
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS_ROOT / "ue_inspect_source_function.py"),
                    "--source",
                    str(source),
                    "--function",
                    "Missing",
                    "--engine-root",
                    str(engine_root),
                ],
                text=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertFalse(completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(
            result["schema_version"], "ue-itps.source-function.v1"
        )
        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "function-not-found",
        )

    def test_all_source_clis_return_json_for_input_failures(self) -> None:
        commands = {
            "ue_list_source_includes.py": [],
            "ue_list_source_types.py": [],
            "ue_inspect_source_function.py": [
                "--function",
                "Missing",
            ],
        }
        for script, extra_arguments in commands.items():
            with self.subTest(script=script):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(TOOLS_ROOT / script),
                        "--source",
                        str(REPOSITORY_ROOT / "Missing.cpp"),
                        *extra_arguments,
                    ],
                    text=True,
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertFalse(completed.stderr)
                result = json.loads(completed.stdout)
                self.assertEqual(result["validation"]["status"], "error")
                self.assertEqual(
                    result["validation"]["problems"][0]["code"],
                    "source-input-failure",
                )

    def test_header_is_derived_without_include_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project, engine_root, source, header = self.write_fixture(root)
            source.write_text(
                "void Local() {}\n",
                encoding="utf-8",
            )

            result = list_source_types(source, engine_override=engine_root)

        header_fact = result["source_unit"]["header"]
        self.assertEqual(
            header_fact["path"],
            "Source/Fixture/Public/Thing.h",
        )
        self.assertEqual(result["validation"]["status"], "ok")
        self.assertIn("FThing", {item["name"] for item in result["types"]})

    def test_multiple_automatic_headers_are_reported_in_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, header = self.write_fixture(
                Path(temporary_directory)
            )
            header.with_suffix(".hpp").write_text(
                "struct FAlternateThing {};",
                encoding="utf-8",
            )

            result = list_source_types(source, engine_override=engine_root)

        self.assertIsNone(result["source_unit"]["header"])
        problem = next(
            problem
            for problem in result["validation"]["problems"]
            if problem["code"] == "source-unit-header-ambiguous"
        )
        self.assertEqual(len(problem["candidates"]), 2)
        self.assertEqual(result["validation"]["status"], "warning")

    def test_unresolved_includes_move_to_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project, engine_root, source, _ = self.write_fixture(
                Path(temporary_directory)
            )
            project_duplicate = (
                project.parent
                / "Source"
                / "Fixture"
                / "Public"
                / "Duplicate.h"
            )
            engine_duplicate = (
                engine_root
                / "Engine"
                / "Plugins"
                / "Demo"
                / "Source"
                / "Demo"
                / "Public"
                / "Duplicate.h"
            )
            project_duplicate.write_text("", encoding="utf-8")
            engine_duplicate.write_text("", encoding="utf-8")
            source.write_text(
                """
#include "Thing.h"
#include "Duplicate.h"
#include "Missing.h"
#include UNKNOWN_HEADER_MACRO(Thing)
#include <vector>
""",
                encoding="utf-8",
            )

            result = list_source_includes(
                source, engine_override=engine_root
            )

        spellings = {item["spelling"] for item in result["includes"]}
        self.assertNotIn("Duplicate.h", spellings)
        self.assertNotIn("Missing.h", spellings)
        self.assertNotIn("UNKNOWN_HEADER_MACRO(Thing)", spellings)
        system_include = next(
            item for item in result["includes"] if item["spelling"] == "vector"
        )
        self.assertEqual(
            system_include["resolution"]["status"],
            "system_or_sdk_unresolved",
        )
        problems = {
            problem["code"]: problem
            for problem in result["validation"]["problems"]
        }
        self.assertIn("source-include-ambiguous", problems)
        self.assertIn("source-include-not-found", problems)
        self.assertIn("source-include-macro-unresolved", problems)
        ambiguous_candidates = problems[
            "source-include-ambiguous"
        ]["include"]["resolution"]["candidates"]
        self.assertTrue(
            all(
                set(candidate["owner"]) == {"kind"}
                for candidate in ambiguous_candidates
            )
        )

    def test_project_discovery_rejects_nearest_ancestor_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project, engine_root, source, _ = self.write_fixture(
                Path(temporary_directory)
            )
            (project.parent / "Second.uproject").write_text(
                '{"FileVersion": 3}', encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "Multiple .uproject"):
                list_source_includes(source, engine_override=engine_root)

    def test_cli_rejects_source_without_an_ancestor_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            _, engine_root, _, _ = self.write_fixture(root)
            outside = root / "Outside.cpp"
            outside.write_text("void Outside() {}", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS_ROOT / "ue_list_source_includes.py"),
                    "--source",
                    str(outside),
                    "--engine-root",
                    str(engine_root),
                ],
                text=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

        self.assertEqual(completed.returncode, 2)
        self.assertFalse(completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(
            result["schema_version"], "ue-itps.source-includes.v1"
        )
        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "source-input-failure",
        )
        self.assertIn(
            "No .uproject file found",
            result["validation"]["problems"][0]["message"],
        )


if __name__ == "__main__":
    unittest.main()
