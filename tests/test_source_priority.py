from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tests.support import ROOT, create_fixture, run_cli, write_text

sys.path.insert(0, str(ROOT / "sourcetools"))
from ue_project_tools.source_context import load_source_context
from ue_project_tools.source_priority import FunctionPriorityView


class SourcePriorityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.fixture = create_fixture(Path(self.directory.name))
        write_text(self.fixture.header, """
            struct FPayload {};
            struct FService { void Get(); void Add(); };
            DECLARE_MULTICAST_DELEGATE(FEvent);
            struct FWorker {
                TMap<FName, TArray<FPayload>> Items, Other;
                TSharedPtr<FService> Pointer;
                FService Service;
                FEvent Changed;
                void Run();
            };
        """)
        write_text(self.fixture.source, """
            void FWorker::Run() {
                Items.Find(Key);
                Items.Num();
                Items.Add(Key, First);
                Items.Add(Key, Second);
                Other.Add(Key, Third);
                Pointer.Get();
                Pointer.IsValid();
                Pointer->OnClicked();
                Service.Get();
                Service.Add();
                Changed.Broadcast();
                UE_LOG(LogTemp, Log, TEXT("trace"));
                TMap<FName, TArray<FPayload>> Local;
                int32 Count = 0;
                auto Callback = [this] { Items.Add(Key, Fourth); };
                auto Unknown = Acquire();
                Unknown.Get();
            }
        """)
        common = json.loads((ROOT / "schemas/common.schema.json").read_text(encoding="utf-8"))
        self.registry = Registry().with_resource(common["$id"], Resource.from_contents(common))

    def assert_schema(self, document):
        schema = json.loads((ROOT / "schemas" / (document["schema_version"] + ".schema.json")).read_text(encoding="utf-8"))
        Draft202012Validator(schema, registry=self.registry).validate(document)

    def inspect(self, *options):
        completed, document = run_cli("sourcetools/ue_inspect_cxx_function.py", "--source",
                                      self.fixture.source, self.fixture.header,
                                      "--function", "FWorker::Run", *options)
        self.assertEqual(completed.returncode, 0, document)
        self.assert_schema(document)
        return document

    def test_container_and_pointer_helpers_are_filtered_by_owner(self):
        full = self.inspect()
        viewed = self.inspect("--view", "behavior")
        match = viewed["matches"][0]
        groups = match["symbol_groups"]
        spellings = {g["spelling"] for g in groups}
        self.assertNotIn("TMap<FName,TArray<FPayload>>->Find()", spellings)
        self.assertNotIn("TSharedPtr<FService>->Get()", spellings)
        self.assertNotIn("TEXT()", spellings)
        self.assertIn("FService->Get()", spellings)
        self.assertIn("FService->Add()", spellings)
        self.assertIn("TSharedPtr<FService>->OnClicked()", spellings)
        self.assertIn("Unknown.Get()", spellings)
        self.assertEqual(match["delegate_operations"], full["matches"][0]["delegate_operations"])
        self.assertTrue(any(op["operation"] == "broadcast" for op in match["delegate_operations"]))
        summary = match["view_summary"]
        self.assertEqual(summary["source_count"], len(full["matches"][0]["external_symbols"]))
        self.assertEqual(sum(g["count"] for g in groups) + sum(summary["hidden_by_rule"].values()),
                         summary["source_count"])
        self.assertGreater(summary["hidden_by_rule"]["container-query"], 0)

    def test_groups_preserve_receiver_scope_and_occurrence_evidence(self):
        document = self.inspect("--view", "behavior", "--include-syntax-flow")
        match = document["matches"][0]
        updates = [g for g in match["symbol_groups"] if g.get("rule") == "container-update"]
        outer = next(g for g in updates if g["receiver"] == "Items" and "execution_scope" not in g)
        self.assertEqual(outer["count"], 2)
        self.assertEqual(outer["display"], "fold")
        self.assertEqual(len(outer["lines"]), 2)
        self.assertTrue(any(g["receiver"] == "Other" for g in updates))
        self.assertTrue(any(g.get("execution_scope", {}).get("kind") == "lambda" for g in updates))
        calls = match["syntax_flow"]["calls"]
        self.assertTrue(any(c["callee"] == "Pointer.Get" for c in calls))
        arguments = [c["arguments"] for c in calls if c["callee"] == "Items.Add"]
        self.assertEqual(arguments, [["Key", "First"], ["Key", "Second"], ["Key", "Fourth"]])

    def test_views_retain_template_structure_and_focus_recovers_hidden_items(self):
        behavior = self.inspect("--view", "behavior")["matches"][0]
        structure = self.inspect("--view", "structure")["matches"][0]
        spelling = "TMap<FName,TArray<FPayload>>"
        for match, display in ((behavior, "fold"), (structure, "expand")):
            group = next(g for g in match["symbol_groups"] if g["kind"] == "type" and g["spelling"] == spelling)
            self.assertEqual(group.get("display", "expand"), display)
        focused = self.inspect("--view", "behavior", "--focus", "TMap", "--focus", "Get")
        self.assertTrue(any(g["spelling"] == "TSharedPtr<FService>->Get()"
                            and g["rule"] == "explicit-focus" for g in focused["matches"][0]["symbol_groups"]))
        self.assertTrue(any(g["spelling"].endswith("->Find()")
                            and g["rule"] == "explicit-focus" for g in focused["matches"][0]["symbol_groups"]))
        all_focused = self.inspect("--view", "behavior", "--focus", "FWorker::Run")["matches"][0]
        self.assertEqual(all_focused["view_summary"]["hidden_by_rule"], {})

    def test_custom_types_and_unknown_accessors_are_not_name_blacklisted(self):
        write_text(self.fixture.header, """
            namespace Custom { template<typename K, typename V> struct TMap { void Find(K); }; }
            struct FWorker { Custom::TMap<int, int> Items; void Run(); };
        """)
        write_text(self.fixture.source, "void FWorker::Run() { Items.Find(1); Unknown.Get(); }")
        match = self.inspect("--view", "behavior")["matches"][0]
        self.assertEqual(match["view_summary"]["hidden_by_rule"], {})
        self.assertEqual(len(match["symbol_groups"]), 2)

    def test_full_mode_and_internal_facts_are_unchanged(self):
        implicit = self.inspect("--include-syntax-flow")
        explicit = self.inspect("--view", "full", "--include-syntax-flow")
        self.assertEqual(implicit, explicit)
        self.assertNotIn("view", implicit)
        loaded = load_source_context([self.fixture.source, self.fixture.header])
        model = loaded["cpp_model"]
        before = copy.deepcopy(model)
        function = next(f for f in model["functions"] if f["qualified_name"] == "FWorker::Run" and f["role"] == "definition")
        policy = FunctionPriorityView(model, "behavior")
        policy.project(function, model["references"][function["occurrence_id"]], "cpp")
        self.assertEqual(model, before)

    def test_definition_views_keep_all_definitions_and_show_section_priorities(self):
        documents = {}
        for view in ("full", "behavior", "structure"):
            completed, document = run_cli("sourcetools/ue_list_cxx_types.py", "--source",
                                          self.fixture.header, "--view", view)
            self.assertEqual(completed.returncode, 0, document)
            self.assert_schema(document)
            documents[view] = document
        for view in ("behavior", "structure"):
            self.assertEqual({k: v for k, v in documents[view].items() if k != "view"}, documents["full"])
        self.assertEqual(documents["behavior"]["view"]["sections"]["structs"], "fold")
        self.assertEqual(documents["structure"]["view"]["sections"]["structs"], "expand")
        completed, focused = run_cli("sourcetools/ue_list_cxx_types.py", "--source",
                                     self.fixture.header, "--view", "behavior",
                                     "--focus", " FService ", "--focus", "FWorker",
                                     "--focus", "FPayload", "--focus", "FWorker")
        self.assertEqual(completed.returncode, 0, focused)
        self.assertEqual(focused["view"]["focus"], ["FService", "FWorker", "FPayload"])
        self.assertEqual(focused["view"]["sections"]["structs"], "expand")

    def test_invalid_view_and_focus_return_request_errors(self):
        for tool, selection in (("ue_list_cxx_types", []), ("ue_inspect_cxx_function", ["--function", "FWorker::Run"])):
            for options in (("--view", "invalid"), ("--focus", "Get"), ("--view", "behavior", "--focus", " ")):
                completed, document = run_cli("sourcetools/" + tool + ".py", "--source",
                                              self.fixture.source, self.fixture.header, *selection, *options)
                self.assertEqual(completed.returncode, 2, document)
                self.assert_schema(document)


if __name__ == "__main__":
    unittest.main()
