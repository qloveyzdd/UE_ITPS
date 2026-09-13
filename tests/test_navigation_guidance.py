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

from tests.support import ROOT, create_fixture, write_json, write_text

sys.path.insert(0, str(ROOT / "sourcetools"))
from ue_project_tools.source_scope import SourceScope
from ue_project_tools import source_context


class NavigationGuidanceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.fixture = create_fixture(Path(directory.name))
        self.profile = Path(directory.name) / "profile.json"
        self.spec = {"version": 1, "id": "sample", "name": "测试", "description": "证据导航",
                     "units": [{"id": "worker", "sources": [p.relative_to(self.fixture.project.parent).as_posix()
                                for p in (self.fixture.source, self.fixture.header)]}]}
        self.guide = {"id": "start", "intent": "开始工作时检查什么", "purpose": "behavior", "kind": "function",
                      "target": "AWorker::BeginPlay", "role": "internal_function", "reason": "通过本地 Helper 调用定位实现。",
                      "checks": [{"kind": "call", "name": "Helper"}]}

    def build(self):
        write_json(self.profile, self.spec)
        result = SourceScope(self.fixture.project, self.profile).navigation_map()
        schema = json.loads((ROOT / "schemas/source_navigation_map.schema.json").read_text(encoding="utf-8"))
        common = json.loads((ROOT / "schemas/common.schema.json").read_text(encoding="utf-8"))
        registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
        Draft202012Validator(schema, registry=registry).validate(result)
        return result

    def reviewed(self):
        baseline = self.build()
        self.spec["units"][0]["reviewed_sources"] = baseline["units"][0]["source_hashes"]
        self.spec["units"][0]["navigation"] = [copy.deepcopy(self.guide)]

    def test_guidance_has_exact_evidence_and_old_tool_query(self):
        self.reviewed()
        result = self.build()["units"][0]["navigation"][0]
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(result["evidence_status"], "matched")
        self.assertEqual(result["query"], {"tool": "ue_inspect_cxx_function", "selector": "AWorker::BeginPlay",
                                           "view": "behavior", "focus": ["Helper"]})
        observed = result["definitions"][0]["checks"][0]["matches"][0]
        self.assertEqual(observed["expression"], "Helper()")
        self.assertTrue(observed["evidence"]["path"].endswith("Worker.cpp"))
        self.assertGreater(observed["evidence"]["line"], 0)

    def test_missing_evidence_or_stale_source_cannot_be_reviewed(self):
        self.reviewed()
        self.spec["units"][0]["navigation"][0]["checks"][0]["name"] = "Invented"
        result = self.build()["units"][0]["navigation"][0]
        self.assertEqual((result["status"], result["evidence_status"]), ("candidate", "missing"))
        self.spec["units"][0]["navigation"][0] = self.guide
        write_text(self.fixture.source, "void AWorker::BeginPlay() { Helper(); NewBehavior(); }")
        unit = self.build()["units"][0]
        self.assertEqual(unit["review_status"], "stale")
        self.assertEqual(unit["navigation"][0]["status"], "candidate")
        self.assertEqual(unit["navigation"][0]["evidence_status"], "matched")

    def test_unknown_target_has_no_query_and_ambiguity_stays_candidate(self):
        self.reviewed()
        self.spec["units"][0]["navigation"][0]["target"] = "AWorker::Missing"
        result = self.build()["units"][0]["navigation"][0]
        self.assertEqual(result["status"], "unresolved")
        self.assertNotIn("query", result)
        self.spec["units"][0]["navigation"][0] = self.guide
        write_text(self.fixture.source, "void AWorker::BeginPlay() { Helper(); } void AWorker::BeginPlay() { Other(); }")
        self.spec["units"][0]["reviewed_sources"] = self.build()["units"][0]["source_hashes"]
        result = self.build()["units"][0]["navigation"][0]
        self.assertEqual(result["status"], "candidate")
        self.assertEqual(result["evidence_status"], "partial")
        self.assertEqual(len(result["definitions"]), 2)

    def test_structure_guidance_and_invalid_inputs(self):
        self.reviewed()
        guide = self.spec["units"][0]["navigation"][0]
        guide.update(kind="type", purpose="structure", target="AWorker", role="type_structure",
                     checks=[{"kind": "member", "name": "Helper"}])
        result = self.build()["units"][0]["navigation"][0]
        self.assertEqual(result["status"], "reviewed")
        self.assertEqual(result["query"], {"tool": "ue_inspect_cxx_type", "selector": "AWorker"})
        valid = copy.deepcopy(self.spec)
        for mutation in ("unknown_field", "wrong_kind", "empty_checks", "duplicate", "incomplete_hashes"):
            self.spec = copy.deepcopy(valid)
            unit = self.spec["units"][0]
            if mutation == "unknown_field": unit["navigation"][0]["confirmed"] = True
            elif mutation == "wrong_kind": unit["navigation"][0]["checks"][0]["kind"] = "call"
            elif mutation == "empty_checks": unit["navigation"][0]["checks"] = []
            elif mutation == "duplicate": unit["navigation"].append(copy.deepcopy(unit["navigation"][0]))
            else: unit["reviewed_sources"].pop(next(iter(unit["reviewed_sources"])))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.build()

    def test_enum_does_not_generate_an_unsupported_type_inspection(self):
        write_text(self.fixture.header, "enum class EState { Ready }; struct AWorker { void BeginPlay(); };")
        self.reviewed()
        self.spec["units"][0]["navigation"][0].update(
            kind="type", purpose="structure", target="EState", role="type_structure",
            checks=[{"kind": "member", "name": "Ready"}])
        result = self.build()["units"][0]["navigation"][0]
        self.assertEqual(result["status"], "unresolved")
        self.assertNotIn("query", result)

    def test_syntax_recovery_does_not_confirm_partial_analysis(self):
        write_text(self.fixture.source, "void AWorker::BeginPlay() { Helper(); } void Broken( {")
        self.reviewed()
        document = self.build()
        self.assertTrue(any(p["code"] == "tree-sitter-cpp-syntax-warning" for p in document["validation"]["problems"]))
        guide = document["units"][0]["navigation"][0]
        self.assertEqual(guide["evidence_status"], "matched")
        self.assertEqual(guide["status"], "candidate")

    def test_source_hash_and_evidence_use_the_same_parse_snapshot(self):
        self.reviewed()
        load = source_context.load_cpp_unit

        def edit_after_parse(*args, **kwargs):
            model = load(*args, **kwargs)
            write_text(self.fixture.source, "void AWorker::BeginPlay() { Changed(); }")
            return model

        with patch.object(source_context, "load_cpp_unit", side_effect=edit_after_parse):
            unit = self.build()["units"][0]
        self.assertEqual(unit["source_hashes"], self.spec["units"][0]["reviewed_sources"])
        self.assertEqual(unit["navigation"][0]["status"], "reviewed")
        # The next parse observes the new text; the saved review is not renewed.
        current = self.build()["units"][0]
        self.assertEqual(current["review_status"], "stale")
        self.assertEqual(current["navigation"][0]["status"], "candidate")


if __name__ == "__main__":
    unittest.main()
