from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tests.support import ROOT, create_fixture, run_cli, write_json, write_text

sys.path.insert(0, str(ROOT / "sourcetools"))
from ue_project_tools.source_scope import SourceScope
from ue_project_tools.source_context import load_source_context


class SourceScopeTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.fixture = create_fixture(Path(directory.name))
        write_text(self.fixture.header, """
            struct FService { void Get(); };
            DECLARE_MULTICAST_DELEGATE(FChanged);
            struct FWorker {
                TMap<int, FService> Items, Other;
                TSharedPtr<FService> Pointer;
                FService Service;
                FChanged Changed;
                void Run();
            };
        """)
        write_text(self.fixture.source, """
            #include "Worker.h"
            void FWorker::Run() {
                Items.Find(Key);
                Items.Add(Key, First); Items.Add(Key, Second);
                Other.Add(Key, Third);
                Pointer.Get(); Service.Get(); Unknown.Get();
                Changed.Broadcast();
                auto Callback = [this] { Items.Add(Key, Fourth); };
                UE_LOG(LogTemp, Log, TEXT("trace"));
            }
        """)
        root = self.fixture.project.parent
        self.profile_data = {
            "version": 1, "id": "sample", "name": "测试系统", "description": "验证源码导航",
            "units": [{"id": "worker", "sources": [p.relative_to(root).as_posix()
                       for p in (self.fixture.source, self.fixture.header)],
                       "roles": {"FWorker": ["入口"]}, "entry_points": ["FWorker::Run"]}],
        }
        self.profile = write_json(Path(directory.name) / "scope.json", self.profile_data)
        self.scope = SourceScope(self.fixture.project, self.profile)
        schemas = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "schemas").glob("*.schema.json")]
        registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)
        schema = next(s for s in schemas if s["$id"] == "urn:ue-itps:schema:ue_inspect_cxx_scope")
        self.validator = Draft202012Validator(schema, registry=registry)

    def query(self, **kwargs):
        result = self.scope.query(**kwargs)
        self.validator.validate(result)
        return result

    def entry(self):
        return next(i for i in self.query()["items"] if i["kind"] == "function")

    def test_four_levels_and_exact_evidence(self):
        overview = self.query()
        worker = next(i for i in overview["items"] if i["kind"] == "type" and i["name"] == "FWorker")
        details = self.query(level="type", select=worker["id"])
        self.assertTrue(details["type_details"]["member_anchors"])
        entry = self.entry()
        function = self.query(level="function", select=entry["id"], limit=100)
        updates = [i for i in function["items"] if i.get("rule") == "container-update"]
        self.assertEqual(sorted(i["count"] for i in updates), [1, 1, 2])
        repeated = next(i for i in updates if i["count"] == 2)
        evidence = self.query(level="evidence", select=repeated["id"])
        self.assertEqual([i["call"]["arguments"] for i in evidence["items"]],
                         [["Key", "First"], ["Key", "Second"]])
        self.assertTrue(all(i["evidence"]["path"].endswith("Worker.cpp") for i in evidence["items"]))
        self.assertNotIn("Items.Add", json.dumps(overview["items"], ensure_ascii=False))

    def test_full_evidence_focus_and_unknowns(self):
        entry = self.entry()
        normal = self.query(level="function", select=entry["id"], limit=100)
        targets = {i["target"] for i in normal["items"]}
        self.assertIn("FService->Get()", targets)
        self.assertIn("Unknown.Get()", targets)
        self.assertNotIn("TSharedPtr<FService>->Get()", targets)
        focus = self.query(level="function", select=entry["id"], focus=["Get"], limit=100)
        self.assertIn("TSharedPtr<FService>->Get()", {i["target"] for i in focus["items"]})
        full = self.query(level="evidence", select=entry["id"], limit=100)
        self.assertTrue(any(i.get("call", {}).get("callee") == "Pointer.Get" for i in full["items"]))
        self.assertTrue(any(i["kind"] == "delegate" for i in full["items"]))
        _, old = run_cli("sourcetools/ue_inspect_cxx_function.py", "--source", self.fixture.source,
                         self.fixture.header, "--function", "FWorker::Run")
        self.assertEqual([i["fact"] for i in full["items"] if i["kind"] == "delegate"],
                         old["matches"][0]["delegate_operations"])
        symbols = [i for i in full["items"] if i["kind"] == "symbol"]
        # The legacy external-symbol list merges same-name occurrences on one line.
        self.assertEqual(len(symbols), len(old["matches"][0]["external_symbols"]) + 1)
        adds = [i for i in symbols if i.get("call", {}).get("callee") == "Items.Add"]
        self.assertEqual([i["call"]["arguments"] for i in adds],
                         [["Key", "First"], ["Key", "Second"], ["Key", "Fourth"]])

    def test_pages_cover_every_item_once_without_mutating_facts(self):
        before = copy.deepcopy(self.scope.units["worker"]["cpp_model"])
        complete = self.query(view="full", limit=100)
        collected = []
        offset = 0
        while offset is not None:
            page = self.query(view="full", offset=offset, limit=3)
            collected.extend(page["items"])
            offset = page["page"]["next_offset"]
        self.assertEqual(collected, complete["items"])
        self.query(view="structure")
        self.assertEqual(before, self.scope.units["worker"]["cpp_model"])

    def test_each_unit_parsed_once_and_snapshot_rejects_old_ids(self):
        with patch("ue_project_tools.source_scope.load_source_context", wraps=load_source_context) as loader:
            scope = SourceScope(self.fixture.project, self.profile)
            scope.query()
            scope.query(view="structure")
            self.assertEqual(loader.call_count, 1)
        old = self.entry()["id"]
        write_text(self.fixture.source, "void FWorker::Run() { Service.Get(); }")
        changed = SourceScope(self.fixture.project, self.profile)
        with self.assertRaisesRegex(ValueError, "selection|Selection"):
            changed.query(level="function", select=old)

    def test_profile_rejects_missing_symbols_duplicate_files_and_escape(self):
        for change in ("symbol", "duplicate", "escape", "unknown_field"):
            profile = copy.deepcopy(self.profile_data)
            unit = profile["units"][0]
            if change == "symbol":
                unit["entry_points"] = ["Invented::Call"]
            elif change == "duplicate":
                profile["units"].append({**unit, "id": "duplicate"})
            elif change == "escape":
                unit["sources"] = ["../Outside.h"]
            else:
                unit["entrypoints"] = unit.pop("entry_points")
            write_json(self.profile, profile)
            with self.subTest(change=change), self.assertRaises(ValueError):
                SourceScope(self.fixture.project, self.profile)

    def test_cli_errors_are_schema_shaped(self):
        for options in (("--level", "function"), ("--limit", "0"), ("--focus", " ")):
            completed, result = run_cli("sourcetools/ue_inspect_cxx_scope.py", "--project", self.fixture.project,
                                        "--profile", self.profile, *options)
            self.assertEqual(completed.returncode, 2, result)
            self.validator.validate(result)

    def test_same_line_type_definitions_keep_their_own_methods(self):
        write_text(self.fixture.header, "struct FWorker { void Run() { First(); } }; struct FWorker { void Run() { Second(); } };")
        write_text(self.fixture.source, "// Definitions are in the selected header")
        scope = SourceScope(self.fixture.project, self.profile)
        overview = scope.query(limit=100)
        types = [i for i in overview["items"] if i["kind"] == "type"]
        self.assertEqual(len(types), 2)
        self.assertNotEqual(types[0]["evidence"]["byte_offset"], types[1]["evidence"]["byte_offset"])
        targets = []
        ids = []
        for item in types:
            result = scope.query(level="type", select=item["id"], limit=100)
            methods = [i for i in result["items"] if i["kind"] == "function"]
            self.assertEqual(len(methods), 1)
            ids.append(methods[0]["id"])
            targets.extend(i["target"] for i in result["items"] if i["kind"] == "relation")
        self.assertEqual(len(set(ids)), 2)
        self.assertCountEqual(targets, ["First()", "Second()"])

    def test_same_names_in_different_units_are_not_bound_together(self):
        root = self.fixture.project.parent
        source = write_text(root / "Source/Sample/Private/Other.cpp", "void FWorker::Run() { Different(); }")
        header = write_text(root / "Source/Sample/Public/Other.h", "struct FWorker { void Run(); };")
        profile = copy.deepcopy(self.profile_data)
        profile["units"].append({"id": "other", "sources": [p.relative_to(root).as_posix() for p in (source, header)]})
        write_json(self.profile, profile)
        scope = SourceScope(self.fixture.project, self.profile)
        types = [i for i in scope.query(view="structure", limit=100)["items"] if i["kind"] == "type" and i["name"] == "FWorker"]
        self.assertEqual(len(types), 2)
        functions = [next(i for i in scope.query(level="type", select=t["id"])["items"] if i["kind"] == "function") for t in types]
        self.assertNotEqual(functions[0]["id"], functions[1]["id"])
        self.assertNotEqual(functions[0]["evidence"]["path"], functions[1]["evidence"]["path"])


if __name__ == "__main__":
    unittest.main()
