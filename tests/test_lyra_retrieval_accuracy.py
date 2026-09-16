"""Manually selected Lyra evidence; only SourceTools reads source content.

The six holdout questions were frozen before checking their source evidence and
are never added to the authored navigation profile. This is a regression corpus,
not an estimate of natural-language routing accuracy.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tests.support import LYRA_PROJECT as PROJECT
from tests.support import ROOT, run_cli

sys.path.insert(0, str(ROOT / "sourcetools"))
from ue_project_tools.source_function_references import _inspect_function_from_context
from ue_project_tools.source_scope import SourceScope
from ue_project_tools.source_type_details import _compound


@unittest.skipUnless(PROJECT.is_file(), "Lyra reference project is not available")
class LyraRetrievalAccuracyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((ROOT / "tests/fixtures/lyra_retrieval_accuracy.json").read_text(encoding="utf-8"))["cases"]
        cls.scope = SourceScope(PROJECT, ROOT / "sourcetools/profiles/lyra_reviewed_navigation.json")
        cls.document = cls.scope.navigation_map()
        cls.units = {tuple(sorted(u["sources"])): u for u in cls.document["units"]}
        cls.guides = {g["id"]: g for u in cls.document["units"] for g in u.get("navigation", [])}
        common = json.loads((ROOT / "schemas/common.schema.json").read_text(encoding="utf-8"))
        cls.registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
        analysis = json.loads((ROOT / "schemas/source_scope_analysis.schema.json").read_text(encoding="utf-8"))
        cls.registry = cls.registry.with_resource(analysis["$id"], Resource.from_contents(analysis))

    def assert_schema(self, document):
        schema = json.loads((ROOT / "schemas" / (document["schema_version"] + ".schema.json")).read_text(encoding="utf-8"))
        Draft202012Validator(schema, registry=self.registry).validate(document)

    def unit(self, case):
        return self.units[tuple(sorted(case["sources"]))]

    def assert_calls(self, case, match):
        calls = match["syntax_flow"]["calls"]
        for expected in case["expected_calls"]:
            found = [call for call in calls if all(call[k] == v for k, v in expected.items())]
            self.assertTrue(found, (case["id"], expected))
            self.assertTrue(all(c["location"]["line"] > 0 and c["location"]["column"] > 0 for c in found))

    def test_reviewed_guidance_and_holdout_separation(self):
        self.assert_schema(self.document)
        development = [c for c in self.cases if c["split"] == "development"]
        holdout = [c for c in self.cases if c["split"] == "holdout"]
        self.assertEqual((len(development), len(holdout)), (21, 6))
        self.assertEqual(set(self.guides), {c["id"] for c in development})
        for case in development:
            with self.subTest(case=case["id"]):
                guide = self.guides[case["id"]]
                self.assertEqual(guide["target"], case["target"])
                self.assertEqual(guide["status"], "reviewed")
                self.assertEqual(guide["evidence_status"], "matched")
                self.assertEqual(self.unit(case)["review_status"], "current")
                self.assertEqual(len(guide["definitions"]), 1)
                for check in guide["definitions"][0]["checks"]:
                    self.assertTrue(check["matches"])
        for case in holdout:
            self.assertFalse(any(g["target"] == case["target"] for g in self.guides.values()))
        self.assertEqual(self.guides["user"]["role"], "system_entry")
        self.assertEqual(self.guides["experience"]["role"], "internal_function")
        self.assertEqual(self.guides["pawn-data"]["role"], "type_structure")

    def test_generic_views_keep_key_occurrences_and_delegates(self):
        for case in self.cases:
            if case["kind"] != "function":
                continue
            unit = self.unit(case)
            loaded = self.scope.units[unit["id"]]
            target = next(f for f in self.scope.functions.values()
                          if f["unit"] == unit["id"] and f["anchor"]["name"] == case["target"])
            references = loaded["cpp_model"]["references"][target["raw"]["occurrence_id"]]
            full = _inspect_function_from_context(loaded, case["target"], include_syntax_flow=True)["matches"][0]
            for view in ("behavior", "structure"):
                with self.subTest(case=case["id"], view=view):
                    result = _inspect_function_from_context(loaded, case["target"], view=view, include_syntax_flow=True)
                    self.assert_schema(result)
                    self.assertEqual(result["match_count"], 1)
                    match = result["matches"][0]
                    self.assert_calls(case, match)
                    self.assertEqual(match["delegate_operations"], full["delegate_operations"])
                    self.assertEqual([(c["callee"], c["location"]["line"]) for c in match["syntax_flow"]["calls"]],
                                     [(c["callee"], c["location"]["line"]) for c in full["syntax_flow"]["calls"]])
                    summary = match["view_summary"]
                    self.assertEqual(sum(g["count"] for g in match["symbol_groups"])
                                     + sum(g["count"] for log in match.get("log_groups", []) for g in log["symbol_groups"])
                                     + sum(summary["hidden_by_rule"].values()),
                                     summary["source_count"])
                    # These manually chosen occurrences must be expanded without profile focus.
                    for name in case["expanded_calls"]:
                        call = next(c for c in references["call_details"] if c["callee"] == name)
                        symbol = next(s for s in references["symbol_occurrences"] if s.get("start_offset") == call["start_offset"])
                        groups = [g for g in match["symbol_groups"]
                                  if all(g.get(k) == v for k, v in symbol.items() if k not in {"line", "start_offset"})
                                  and symbol["line"] in g["lines"]]
                        self.assertTrue(groups, (case["id"], name))
                        self.assertTrue(all(g.get("display", "expand") == "expand" for g in groups))

    def test_structure_members_match_reviewed_source_evidence(self):
        for case in self.cases:
            if case["kind"] != "type":
                continue
            with self.subTest(case=case["id"]):
                matches = [_compound(t["raw"]) for t in self.scope.types.values()
                           if t["unit"] == self.unit(case)["id"] and t["anchor"]["name"] == case["target"]]
                self.assertEqual(len(matches), 1)
                members = {m["name"]: m for m in matches[0]["member_anchors"]}
                self.assertTrue(set(case["expected_members"]) <= members.keys())
                self.assertTrue(all(members[name]["evidence"]["line"] > 0 for name in case["expected_members"]))

    def test_holdout_lambda_and_broadcast_scope(self):
        case = next(c for c in self.cases if c["id"] == "heldout-experience-ready")
        loaded = self.scope.units[self.unit(case)["id"]]
        match = _inspect_function_from_context(loaded, case["target"], view="behavior", include_syntax_flow=True)["matches"][0]
        calls = match["syntax_flow"]["calls"]
        activation = next(c for c in calls if c["callee"] == "Action.OnGameFeatureActivating")
        self.assertEqual(activation["execution_scope"]["kind"], "lambda")
        broadcasts = [c for c in calls if c["callee"] in {
            "OnExperienceLoaded_HighPriority.Broadcast", "OnExperienceLoaded.Broadcast", "OnExperienceLoaded_LowPriority.Broadcast"}]
        self.assertEqual(len(broadcasts), 3)
        self.assertTrue(all(c["execution_scope"]["kind"] == "function" for c in broadcasts))
        self.assertEqual([c["callee"] for c in broadcasts], [
            "OnExperienceLoaded_HighPriority.Broadcast", "OnExperienceLoaded.Broadcast", "OnExperienceLoaded_LowPriority.Broadcast"])

    def test_saved_guidance_and_holdout_queries_in_independent_old_clis(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                unit = self.unit(case)
                query = self.guides[case["id"]]["query"] if case["split"] == "development" else {
                    "tool": "ue_inspect_cxx_function" if case["kind"] == "function" else "ue_inspect_cxx_type",
                    "selector": case["target"], "view": "behavior", "focus": []}
                args = ["--source", *[PROJECT.parent / path for path in unit["sources"]]]
                args += ["--function" if case["kind"] == "function" else "--type", query["selector"]]
                if case["kind"] == "function":
                    args += ["--view", query["view"], "--include-syntax-flow"]
                    for focus in query["focus"]:
                        args += ["--focus", focus]
                completed, result = run_cli("sourcetools/" + query["tool"] + ".py", *args)
                self.assertEqual(completed.returncode, 0, result)
                self.assertEqual(completed.stderr, "")
                self.assert_schema(result)
                self.assertEqual(len(result["matches"]), 1)
                match = result["matches"][0]
                if case["kind"] == "function":
                    self.assert_calls(case, match)
                    if case["split"] == "development":
                        for check in self.guides[case["id"]]["definitions"][0]["checks"]:
                            for proof in check["matches"]:
                                self.assertTrue(any(c["callee"] == check["name"] and c["expression"] == proof["expression"]
                                                    and c["arguments"] == proof["arguments"] and c["location"]["line"] == proof["evidence"]["line"]
                                                    and c["location"]["column"] == proof["evidence"]["column"]
                                                    and c["execution_scope"] == proof["execution_scope"]
                                                    for c in match["syntax_flow"]["calls"]))
                else:
                    self.assertTrue(set(case["expected_members"]) <= {m["name"] for m in match["member_anchors"]})


if __name__ == "__main__":
    unittest.main()
