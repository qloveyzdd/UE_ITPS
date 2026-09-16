"""Scope coverage and declaration candidates, including deliberately unsafe matches."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tests.support import ROOT, create_fixture, write_json, write_text, run_cli

sys.path.insert(0, str(ROOT / "sourcetools"))
from ue_project_tools.source_scope import SourceScope
from ue_project_tools import source_context


class ScopeAnalysisTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.fixture = create_fixture(Path(directory.name))
        self.root = self.fixture.project.parent
        self.profile = self.root / "scope.json"
        self.spec = {"version": 1, "id": "scope", "name": "Scope", "description": "Candidate regression",
                     "inventory_rules": [self.fixture.module_rules.relative_to(self.root).as_posix()],
                     "units": [{"id": "worker", "sources": [p.relative_to(self.root).as_posix()
                                for p in (self.fixture.source, self.fixture.header)]}]}
        schemas = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "schemas").glob("*.schema.json")]
        registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)
        self.validator = Draft202012Validator(next(s for s in schemas if s["$id"].endswith(":ue_inspect_cxx_scope")), registry=registry)

    def build(self):
        write_json(self.profile, self.spec)
        scope = SourceScope(self.fixture.project, self.profile)
        self.validator.validate(scope.query(include_audit=True))
        return scope

    def add_unit(self, name, header, source):
        paths = [write_text(self.root / f"Source/Sample/Public/{name}.h", header),
                 write_text(self.root / f"Source/Sample/Private/{name}.cpp", source)]
        self.spec["units"].append({"id": name, "sources": [p.relative_to(self.root).as_posix() for p in paths]})

    def calls(self, scope, name="AWorker::BeginPlay"):
        selected = next(k for k, item in scope.functions.items() if item["anchor"]["name"] == name)
        result = scope.query(level="evidence", select=selected, limit=100)
        self.validator.validate(result)
        return {item["call"]["callee"]: item for item in result["items"] if "call" in item}

    def test_coverage_is_explicit_and_does_not_parse_unselected_files(self):
        extra = write_text(self.root / "Source/Sample/Public/Unread.h", "This is deliberately not C++")
        scope = self.build()
        result = scope.query(include_audit=True)
        files = {f["path"]: f for f in result["audit"]["files"]}
        self.assertEqual(result["audit"]["coverage"]["selected"], 2)
        self.assertEqual(result["audit"]["coverage"]["inventoried"], 4)
        self.assertEqual(files[extra.relative_to(self.root).as_posix()]["status"], "not_selected")
        self.assertNotIn("audit", scope.query())
        self.spec.pop("inventory_rules")
        self.assertIsNone(self.build().query(include_audit=True)["audit"]["coverage"]["inventoried"])

    def test_diagnostics_and_missing_inputs_are_not_silent_success(self):
        write_text(self.fixture.source, "void AWorker::BeginPlay() { if ( }")
        result = self.build().query(include_audit=True)
        self.assertIn("parsed_with_diagnostics", result["audit"]["coverage"]["by_status"])
        self.fixture.source.unlink()
        with self.assertRaises(ValueError):
            self.build()

    def test_provenance_changes_for_source_profile_and_engine(self):
        initial = self.build()
        self.assertEqual(initial.snapshot, self.build().snapshot)
        write_text(self.fixture.source, "void AWorker::BeginPlay() { Other(); }")
        changed = self.build()
        self.assertNotEqual(initial.provenance["sources_sha256"], changed.provenance["sources_sha256"])
        self.spec["description"] = "Changed"
        self.assertNotEqual(changed.provenance["profile_sha256"], self.build().provenance["profile_sha256"])
        write_json(self.profile, self.spec)
        engine_a = SourceScope(self.fixture.project, self.profile, self.fixture.root)
        version = json.loads(self.fixture.build_version.read_text(encoding="utf-8"))
        version["PatchVersion"] += 1
        write_json(self.fixture.build_version, version)
        engine_b = SourceScope(self.fixture.project, self.profile, self.fixture.root)
        self.assertNotEqual(engine_a.snapshot, engine_b.snapshot)
        self.assertEqual(engine_a.provenance["sources_sha256"], engine_b.provenance["sources_sha256"])

    def test_unknown_reason_totals_and_actionable_locations(self):
        write_text(self.fixture.source, "void AWorker::BeginPlay() { Missing(); NewObject<AWorker>(); (&Missing)(); &Outside; }")
        scope = self.build()
        summary = scope.query()["summary"]
        self.assertEqual(sum(summary["unresolved_by_reason"].values()), summary["unresolved_symbols"])
        calls = self.calls(scope)
        self.assertEqual(calls["Missing"]["resolution"]["reason"], "declaration_not_in_scope")
        self.assertEqual(calls["NewObject<AWorker>"]["resolution"]["reason"], "requires_semantics")
        for record in scope.records:
            if record["public"]["kind"] == "symbol" and record["public"]["fact"]["kind"] == "unknown":
                self.assertTrue(record["public"]["resolution"]["next_step"])
                self.assertGreater(record["public"]["evidence"]["line"], 0)

    def test_cross_unit_candidate_and_definition_navigation(self):
        self.add_unit("Service", "struct FService { void Work(); };", "void FService::Work() {}")
        write_text(self.fixture.source, "void AWorker::BeginPlay() { FService* Service; Service->Work(); }")
        scope = self.build()
        result = self.calls(scope)["Service.Work"]["resolution"]
        self.assertEqual(result["status"], "candidate")
        self.assertEqual({c["role"] for c in result["candidates"]}, {"declaration", "definition"})
        target = next(c for c in result["candidates"] if "function_id" in c)
        self.assertEqual(scope.query(level="function", select=target["function_id"])["selection"]["name"], "FService::Work")

    def test_overloads_and_conditional_definitions_are_preserved(self):
        self.add_unit("Service", "void Work(int); void Work(float);", "void Work(int A) {} void Work(float B) {}")
        write_text(self.fixture.source, "void AWorker::BeginPlay() { Work(1); }")
        result = self.calls(self.build())["Work"]["resolution"]
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(len(result["candidates"]), 4)
        write_text(self.root / "Source/Sample/Private/Service.cpp", "#if FIRST\nvoid Work(int A) {}\n#else\nvoid Work(int A) {}\n#endif")
        write_text(self.root / "Source/Sample/Public/Service.h", "void Work(int);")
        result = self.calls(self.build())["Work"]["resolution"]
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(len([c for c in result["candidates"] if c["role"] == "definition"]), 2)

    def test_shadowing_and_unrelated_static_functions_do_not_create_edges(self):
        self.add_unit("Service", "void Work();", "void Work() {} static void Hidden() {}")
        write_text(self.fixture.source, "void AWorker::BeginPlay() { auto Work = []{}; Work(); Hidden(); }")
        calls = self.calls(self.build())
        self.assertFalse(calls["Work"]["resolution"]["candidates"])
        self.assertFalse(calls["Hidden"]["resolution"]["candidates"])

    def test_same_simple_name_in_other_namespace_is_not_a_candidate(self):
        self.add_unit("Service", "namespace Other { void Work(); }", "void Other::Work() {}")
        write_text(self.fixture.source, "void AWorker::BeginPlay() { Work(); }")
        self.assertFalse(self.calls(self.build())["Work"]["resolution"]["candidates"])

    def test_anonymous_namespace_functions_stay_in_their_source_unit(self):
        self.add_unit("Service", "// Private implementation", "namespace { void Hidden() {} }")
        write_text(self.fixture.source, "void AWorker::BeginPlay() { Hidden(); }")
        self.assertFalse(self.calls(self.build())["Hidden"]["resolution"]["candidates"])

    def test_file_local_return_types_and_globals_do_not_leak(self):
        self.add_unit("Service", "struct FService { void Work(); };",
                      "void FService::Work() {} static FService* Get(); static FService* Global;")
        write_text(self.fixture.source, "void AWorker::BeginPlay() { Get()->Work(); Global->Work(); }")
        calls = self.calls(self.build())
        self.assertTrue(all(not item["resolution"]["candidates"] for item in calls.values()))

    def test_inheritance_and_tobjectptr_arrow_keep_matching_basis(self):
        self.add_unit("Service", "struct FBase { void Work(); }; struct FService : FBase {};", "void FBase::Work() {}")
        write_text(self.fixture.source, "void AWorker::BeginPlay() { TObjectPtr<const FService> Service; Service->Work(); Service.Work(); }")
        # Both expressions normalize to Service.Work; inspect occurrences separately.
        scope = self.build()
        matches = [r["public"] for r in scope.records if r["call"] and r["call"]["target_name"] == "Work"]
        arrow = next(r for r in matches if "->" in r["call"]["expression"])
        dot = next(r for r in matches if "->" not in r["call"]["expression"])
        self.assertEqual(arrow["resolution"]["basis"], ["base_type_and_member_name"])
        self.assertFalse(dot["resolution"]["candidates"])

    def test_nested_calls_sharing_start_offset_are_counted_separately(self):
        write_text(self.fixture.header, "struct AWorker { AWorker* Get(); void Work(); void BeginPlay(); };")
        write_text(self.fixture.source, "void AWorker::BeginPlay() { Get()->Work(); }")
        scope = self.build()
        calls = self.calls(scope)
        self.assertEqual(set(calls), {"Get", "Get().Work"})
        self.assertEqual(scope.query()["summary"]["call_occurrences"], 2)
        self.assertTrue(all(c["resolution"]["candidates"] for c in calls.values()))

    def test_inner_arrow_does_not_unwrap_outer_dot_receiver(self):
        self.add_unit("Service", "struct FService { void Work(); }; struct FHolder { TObjectPtr<FService> Pointer; };",
                      "void FService::Work() {}")
        write_text(self.fixture.source, "void AWorker::BeginPlay() { FHolder* Holder; Holder->Pointer.Work(); }")
        self.assertFalse(self.calls(self.build())["Holder.Pointer.Work"]["resolution"]["candidates"])

    def test_cli_audit_and_inventory_escape(self):
        self.build()
        completed, result = run_cli("sourcetools/ue_inspect_cxx_scope.py", "--project", self.fixture.project,
                                    "--profile", self.profile, "--include-audit")
        self.assertEqual(completed.returncode, 0)
        self.validator.validate(result)
        self.assertIn("files", result["audit"])
        self.spec["inventory_rules"] = ["../Outside.Build.cs"]
        with self.assertRaises(ValueError):
            self.build()

    def test_module_inventory_reuse_matches_uncached_and_refreshes_next_scan(self):
        self.add_unit("Service", "struct FService { void Work(); };", "void FService::Work() {}")
        with patch.object(source_context, "module_records", wraps=source_context.module_records) as discovery:
            cached = self.build()
            self.assertEqual(discovery.call_count, 1)
            self.build()
            self.assertEqual(discovery.call_count, 2)

        def uncached(*args, **kwargs):
            kwargs.pop("module_records_cache", None)
            return source_context.load_source_context(*args, **kwargs)

        with patch("ue_project_tools.source_scope.load_source_context", side_effect=uncached):
            fresh = self.build()
        self.assertEqual(cached.query(include_audit=True), fresh.query(include_audit=True))
        self.assertEqual(cached.records, fresh.records)
        for function_id in cached.functions:
            self.assertEqual(cached.query(level="evidence", select=function_id, limit=100),
                             fresh.query(level="evidence", select=function_id, limit=100))


if __name__ == "__main__":
    unittest.main()
