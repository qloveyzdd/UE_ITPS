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
    list_source_variables,
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
        self.assertEqual(result["source_unit"]["header"]["status"], "selected")

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
        external = next(
            item
            for item in result["includes"]
            if item["spelling"] == "ExternalThing.h"
        )
        self.assertEqual(external["resolution"]["status"], "resolved")
        self.assertEqual(
            external["resolution"]["owner"],
            {
                "kind": "engine_plugin_module",
                "module": "Demo",
                "plugin": "Demo",
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
        self.assertIn("Count", type_fact["member_variables"])
        self.assertIn("Run", type_fact["member_functions"])
        self.assertIn(
            "USTRUCT", [item["name"] for item in result["type_macros"]]
        )
        self.assertNotIn("summary", type_fact)

    def test_variable_tool_separates_scopes_and_preserves_initializers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, _ = self.write_fixture(
                Path(temporary_directory)
            )
            result = list_source_variables(
                source, engine_override=engine_root
            )

        self.assert_common_context(result)
        self.assertEqual(
            result["schema_version"], "ue-itps.source-variables.v1"
        )
        indexed = {
            (item["scope"], item["name"]): item
            for item in result["variables"]
        }
        self.assertEqual(indexed[("file", "GCount")]["initializer"], "1")
        self.assertEqual(indexed[("member", "Count")]["initializer"], "0")
        self.assertEqual(
            indexed[("parameter", "Value")]["callable"]["owner"], "FThing"
        )
        self.assertIn(("local", "LocalValue"), indexed)
        self.assertEqual(
            indexed[("local", "LocalValue")]["initializer"], "Value"
        )
        self.assertIn(
            "UPROPERTY", [item["name"] for item in result["variable_macros"]]
        )
        self.assertNotIn(("file", "UForward"), indexed)

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
                owner="FThing",
                parameters="int32 Value",
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
        self.assertEqual(detail["function"]["name"], "Run")
        invocation = next(
            item
            for item in detail["operations"]
            if item.get("callee") == "ExternalCall"
        )
        self.assertEqual(invocation["callable"]["owner"], "FThing")
        self.assertNotIn(
            "construction", [item["kind"] for item in detail["operations"]]
        )

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
            variables = list_source_variables(
                source, engine_override=engine_root
            )
            functions = list_source_functions(
                source, engine_override=engine_root
            )

        type_fact = next(
            item
            for item in types["types"]
            if item["name"] == "FCallableFixture"
        )
        self.assertEqual(
            type_fact["member_variables"],
            ["JobFunc", "Callback", "MemberCallback"],
        )
        self.assertEqual(type_fact["member_functions"], ["Run"])
        details = {
            (item["kind"], item["name"]): item
            for item in type_fact["member_details"]
        }
        self.assertEqual(
            details[("variable", "JobFunc")]["evidence"]["line"], 6
        )
        self.assertEqual(
            details[("function", "Run")]["evidence"]["line"], 9
        )
        self.assertEqual(
            {
                item["name"]
                for item in variables["variables"]
                if item["scope"] == "member"
                and item["owner"] == "FCallableFixture"
            },
            {"Callback", "JobFunc", "MemberCallback"},
        )
        self.assertNotIn(
            "void", {item["name"] for item in functions["functions"]}
        )
        self.assertEqual(types["validation"]["status"], "ok")
        self.assertEqual(variables["validation"]["status"], "ok")
        self.assertEqual(functions["validation"]["status"], "ok")

    def test_unresolved_declaration_is_reported_instead_of_silently_guessed(self) -> None:
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

            result = list_source_variables(
                source, engine_override=engine_root
            )
            types = list_source_types(source, engine_override=engine_root)
            functions = list_source_functions(
                source, engine_override=engine_root
            )

        self.assertEqual(result["validation"]["status"], "warning")
        self.assertFalse(
            [
                item
                for item in result["variables"]
                if item.get("owner") == "FAmbiguous"
            ]
        )
        unresolved = result["unresolved_declarations"]
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]["reason"], "multiple_declarators")
        self.assertEqual(unresolved[0]["scope"], "member")
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
    void Overloaded() {}
    void Overloaded() const {}
};
""",
                encoding="utf-8",
            )
            source.write_text(
                """
#include "Thing.h"
void FRelations::Matched() const {}
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
                function_id=inline["function_id"],
                engine_override=engine_root,
            )
            ambiguous = inspect_source_function(
                source,
                "Overloaded",
                owner="FRelations",
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
        self.assertEqual(len(overloads), 2)
        self.assertEqual(
            len({item["function_id"] for item in overloads}), 2
        )
        self.assertEqual(detail["function_id"], inline["function_id"])
        self.assertEqual(
            detail["function"]["function_id"], inline["function_id"]
        )
        self.assertEqual(ambiguous["validation"]["status"], "error")
        self.assertEqual(len(ambiguous["candidates"]), 2)

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
                function_id="method|FCommandLine|Get|()|",
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

    def test_lambda_call_statements_do_not_produce_variable_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, header = self.write_fixture(
                Path(temporary_directory)
            )
            header.write_text(
                """
#pragma once
struct FVariableExpressions
{
    void Run();
};
""",
                encoding="utf-8",
            )
            source.write_text(
                """
#include "Thing.h"
void FVariableExpressions::Run()
{
    Algo::SortBy(Items, [](const auto& Data) { return Data.Value; }, TGreater<>());
    Entries.Sort([](const auto& A, const auto& B) { return A.Value < B.Value; });
}
""",
                encoding="utf-8",
            )

            variables = list_source_variables(
                source, engine_override=engine_root
            )

        self.assertEqual(variables["validation"]["status"], "ok")
        self.assertFalse(variables["unresolved_declarations"])

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
                function_id="method|bOutSuccess|if|(bHasTimeStamp)|",
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
        self.assertEqual(projected["member_variables"], ["First", "Last"])

    def test_array_declaration_is_not_a_structured_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, _ = self.write_fixture(
                Path(temporary_directory)
            )
            source.write_text(
                """
#include "Thing.h"
void FThing::Run(int32 Value) const
{
    const FText Names[] = { FText(), FText() };
    auto [First, Second] = Pair;
}
""",
                encoding="utf-8",
            )

            variables = list_source_variables(
                source, engine_override=engine_root
            )

        names = {
            item["name"]
            for item in variables["variables"]
            if item["scope"] == "local"
        }
        self.assertIn("Names", names)
        self.assertEqual(
            [
                item["reason"]
                for item in variables["unresolved_declarations"]
            ],
            ["structured_binding"],
        )

    def test_function_operations_report_hierarchy_roles_and_literals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, header = self.write_fixture(
                Path(temporary_directory)
            )
            header.write_text(
                """
#pragma once
struct FOperations
{
    void Run();
};
""",
                encoding="utf-8",
            )
            source.write_text(
                """
#include "Thing.h"
void FOperations::Run()
{
    if (Check(false))
    {
        Outer(Inner(0.0f), nullptr);
        UE_LOG(LogTemp, Display, TEXT("done"));
        FOperations();
    }
}
""",
                encoding="utf-8",
            )

            result = inspect_source_function(
                source,
                "Run",
                owner="FOperations",
                engine_override=engine_root,
            )

        operations = result["operations"]
        check = next(item for item in operations if item.get("callee") == "Check")
        outer = next(item for item in operations if item.get("callee") == "Outer")
        inner = next(item for item in operations if item.get("callee") == "Inner")
        log = next(item for item in operations if item.get("callee") == "UE_LOG")
        construction = next(
            item
            for item in operations
            if item.get("callee") == "FOperations"
        )
        self.assertEqual(check["expression_role"], "condition")
        self.assertIsNone(outer["parent_operation_id"])
        self.assertEqual(inner["parent_operation_id"], outer["operation_id"])
        self.assertEqual(inner["depth"], outer["depth"] + 1)
        self.assertEqual(
            inner["arguments"][0]["evaluation"]["literal_values"], [0.0]
        )
        self.assertEqual(
            check["arguments"][0]["evaluation"]["literal_values"], [False]
        )
        self.assertEqual(
            outer["arguments"][1]["evaluation"]["literal_values"], [None]
        )
        self.assertEqual(log["call_kind"], "known_macro")
        self.assertEqual(construction["call_kind"], "construction_candidate")

    def test_include_origin_unit_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            _, engine_root, source, _ = self.write_fixture(
                Path(temporary_directory)
            )
            result = list_source_includes(
                source, engine_override=engine_root
            )

        origins = {
            item["spelling"]: item["origin_unit"]
            for item in result["includes"]
        }
        self.assertEqual(origins["Thing.h"], "source")
        self.assertEqual(origins["ExternalThing.h"], "companion_header")

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
            "ue_list_source_variables.py": [],
            "ue_list_source_functions.py": [],
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

    def test_header_selection_returns_ambiguity_without_reading_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project, engine_root, source, header = self.write_fixture(root)
            module_root = project.parent / "Source" / "Fixture"
            first = module_root / "Public" / "A" / "Thing.h"
            second = module_root / "Public" / "B" / "Thing.h"
            first.parent.mkdir(parents=True)
            second.parent.mkdir(parents=True)
            first.write_text("struct FFirst {", encoding="utf-8")
            second.write_text("struct FSecond {", encoding="utf-8")
            header.unlink()
            source.write_text(
                '#include "A/Thing.h"\n#include "B/Thing.h"\nvoid Local() {}\n',
                encoding="utf-8",
            )

            result = list_source_types(source, engine_override=engine_root)

        self.assertEqual(result["source_unit"]["header"]["status"], "ambiguous")
        self.assertEqual(len(result["source_unit"]["header"]["candidates"]), 2)
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertFalse(result["types"])

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
