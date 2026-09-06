from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tests.support import ROOT, create_fixture, run_cli, write_text


class SourceTypeSemanticsTests(unittest.TestCase):
    def assert_contract(self, result) -> None:
        schema = json.loads((ROOT / "schemas" / (result["schema_version"] + ".schema.json")).read_text(encoding="utf-8"))
        common = json.loads((ROOT / "schemas/common.schema.json").read_text(encoding="utf-8"))
        registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
        Draft202012Validator(schema, registry=registry).validate(result)

    def test_basic_inventory_excludes_details_and_lists_local_macro_definitions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            write_text(fixture.header.parent / "Other.h", "class NotSelected {};\n#define NOT_SELECTED 1")
            header = write_text(fixture.header, """
                #include "Other.h"
                #define VALUE 42
                #define EMPTY()
                #define APPLY(Value, ...) Value
                #if WITH_EDITOR
                #define EDITOR_VALUE 1
                #else
                #define EDITOR_VALUE 2
                #endif
                class Forward;
                extern int External;
                void Prototype();
                namespace Game {
                    UCLASS()
                    class Worker : public Base { int Count; void Run() {} };
                    struct Data {};
                    enum class Mode { First, Second };
                    int Global = 0;
                    void Free() {}
                }
            """)
            completed, result = run_cli("sourcetools/ue_list_cxx_types.py", "--source", header)
            self.assertEqual(completed.returncode, 0)
            self.assert_contract(result)
            self.assertEqual(set(result), {"schema_version", "classes", "structs", "enums",
                                         "global_variables", "free_functions", "macros", "validation", "limits"})
            self.assertEqual([item["qualified_name"] for item in result["classes"]], ["Game::Worker"])
            worker = result["classes"][0]
            self.assertEqual(worker["macros"], ["UCLASS()"])
            self.assertNotIn("member_anchors", worker)
            self.assertNotIn("base_types", worker)
            self.assertNotIn("enumerators", result["enums"][0])
            self.assertEqual([item["name"] for item in result["free_functions"]], ["Free"])
            self.assertEqual([item["name"] for item in result["global_variables"]], ["Global"])
            self.assertEqual([(item["name"], item["parameters"]) for item in result["macros"]],
                             [("VALUE", None), ("EMPTY", []), ("APPLY", ["Value", "..."]),
                              ("EDITOR_VALUE", None), ("EDITOR_VALUE", None)])
            self.assertTrue(all(set(item) == {"name", "parameters", "evidence"} for item in result["macros"]))
            self.assertEqual(result["macros"][0]["evidence"]["line"], 2)

    def test_type_selector_is_exact_and_limits_members_to_selected_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(fixture.header, """
                namespace Game {
                    struct Worker : Base { int Count; void Run(); struct Nested { void Inner() {} }; };
                }
                namespace Other { struct Worker { void Run() {} }; }
            """)
            source = write_text(fixture.source, "void Game::Worker::Run() {}")
            completed, result = run_cli("sourcetools/ue_inspect_cxx_type.py", "--source", source, header,
                                        "--type", "Game::Worker")
            self.assertEqual(completed.returncode, 0)
            self.assert_contract(result)
            self.assertEqual(len(result["matches"]), 1)
            match = result["matches"][0]
            self.assertEqual(match["base_types"], ["Base"])
            self.assertEqual([item["name"] for item in match["member_anchors"]], ["Count", "Run"])
            self.assertEqual([item["qualified_name"] for item in match["member_functions"]], ["Game::Worker::Run"])
            self.assertEqual(match["member_functions"][0]["evidence"]["unit"], "cpp")
            _, header_only = run_cli("sourcetools/ue_inspect_cxx_type.py", "--source", header, "--type", "Game::Worker")
            self.assertEqual(header_only["matches"][0]["member_functions"], [])
            for selector in ("Worker", "Missing"):
                completed, missing = run_cli("sourcetools/ue_inspect_cxx_type.py", "--source", header, "--type", selector)
                self.assertEqual(completed.returncode, 1)
                self.assertEqual(missing["matches"], [])
                self.assert_contract(missing)
            completed, invalid = run_cli("sourcetools/ue_inspect_cxx_type.py", "--source", header, "--type", "")
            self.assertEqual(completed.returncode, 2)
            self.assert_contract(invalid)

    def test_interface_inference_moves_to_type_details(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(fixture.header, """
                UINTERFACE(BlueprintType)
                class UFeature : public UInterface {};
                class IFeature {};
                namespace Other { class IFeature {}; }
            """)
            _, result = run_cli("sourcetools/ue_inspect_cxx_type.py", "--source", header, "--type", "UFeature")
            self.assert_contract(result)
            self.assertEqual(result["matches"][0]["interface_candidate_reasons"],
                             ["UINTERFACE macro", "derives from UInterface"])
            _, result = run_cli("sourcetools/ue_inspect_cxx_type.py", "--source", header, "--type", "IFeature")
            self.assertEqual(result["matches"][0]["interface_candidate_reasons"], ["paired I/U interface naming"])
            _, result = run_cli("sourcetools/ue_inspect_cxx_type.py", "--source", header, "--type", "Other::IFeature")
            self.assertEqual(result["matches"][0]["interface_candidate_reasons"], [])

    def test_static_member_definitions_keep_identity_and_reference_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(fixture.header, """
                namespace Game {
                    struct A { static int Count; int Read(); };
                    struct B { static int Count; int Read(); };
                }
            """)
            source = write_text(fixture.source, """
                int Count = 0;
                namespace Game {
                    int A::Count = 1;
                    int Game::B::Count = 2;
                    int A::Read() { return Count + B::Count + ::Count; }
                    int B::Read() { return Count; }
                }
            """)
            completed, result = run_cli(
                "sourcetools/ue_list_cxx_types.py", "--source", source, header,
            )
            self.assertEqual(completed.returncode, 0)
            variables = result["global_variables"]
            self.assertEqual(
                [(item["qualified_name"], item["namespace"]) for item in variables],
                [("Count", None), ("Game::A::Count", "Game"), ("Game::B::Count", "Game")],
            )
            for selector, expected in [
                ("Game::A::Read", {"Game::A::Count", "Game::B::Count", "Count"}),
                ("Game::B::Read", {"Game::B::Count"}),
            ]:
                with self.subTest(selector=selector):
                    completed, result = run_cli(
                        "sourcetools/ue_inspect_cxx_function.py", "--source", source, header,
                        "--function", selector,
                    )
                    self.assertEqual(completed.returncode, 0)
                    self.assertEqual(
                        {item["spelling"] for item in result["matches"][0]["external_symbols"]
                         if item["kind"] == "global_variable"}, expected,
                    )

    def test_member_anchors_cover_inline_template_and_conditional_members(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(fixture.header, """
                class AWorker {
                    AWorker();
                    ~AWorker() {}
                    UFUNCTION() int GetCount() const { return 1; }
                    template<class T> void Bind(T Value);
                    template<class T> void Send(T Value) {}
                #if WITH_EDITOR
                    void Edit() {}
                #endif
                    struct FNested { void Inner() {} };
                };
            """)
            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_type.py", "--source", header, "--type", "AWorker",
            )
            self.assertEqual(completed.returncode, 0)
            worker = result["matches"][0]
            anchors = worker["member_anchors"]
            self.assertEqual([item["name"] for item in anchors],
                             ["AWorker", "~AWorker", "GetCount", "Bind", "Send", "Edit"])
            self.assertEqual(next(item for item in anchors if item["name"] == "GetCount")["macros"],
                             ["UFUNCTION()"])
            definitions = worker["member_functions"]
            self.assertEqual(len(definitions), 4)
            self.assertNotIn("Bind", {item["name"] for item in definitions})
            completed, nested = run_cli(
                "sourcetools/ue_inspect_cxx_type.py", "--source", header,
                "--type", "AWorker::FNested",
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual([item["name"] for item in nested["matches"][0]["member_anchors"]], ["Inner"])


if __name__ == "__main__":
    unittest.main()
