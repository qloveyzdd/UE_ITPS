"""Reviewed Lyra sampling regressions; source contents are read by SourceTools only."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tests.support import ROOT, run_cli, write_json

sys.path.insert(0, str(ROOT / "sourcetools"))
from ue_project_tools.project_cxx_sources import list_module_cxx_sources
from ue_project_tools.source_function_references import _inspect_function_from_context
from ue_project_tools.source_scope import SourceScope
from ue_project_tools.source_type_details import _compound

PROJECT = ROOT / "LyraStarterGame/LyraStarterGame.uproject"


@unittest.skipUnless(PROJECT.is_file(), "Lyra reference project is not available")
class LyraRetrievalSamplingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((ROOT / "tests/fixtures/lyra_retrieval_sampling.json").read_text(encoding="utf-8"))["cases"]
        cls.scope = SourceScope(PROJECT, ROOT / "sourcetools/profiles/lyra_sampling_reviewed.json")
        cls.document = cls.scope.navigation_map()
        cls.guides = {g["id"]: g for u in cls.document["units"] for g in u["navigation"]}
        schemas = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "schemas").glob("*.schema.json")]
        registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)
        cls.validators = {s["$id"].rsplit(":", 1)[-1]: Draft202012Validator(s, registry=registry) for s in schemas}
        cls.views = {}
        for case in cls.cases:
            if case["kind"] == "function":
                cls.views[case["id"]] = {view: _inspect_function_from_context(
                    cls.scope.units[case["unit"]], case["target"], view=view, include_syntax_flow=True)
                    for view in ("full", "behavior", "structure")}

    def assert_schema(self, document):
        self.validators[document["schema_version"]].validate(document)

    def assert_expected(self, case, result):
        self.assert_schema(result)
        self.assertEqual(len(result["matches"]), case["definition_count"])
        if case["kind"] == "function":
            calls = [c for m in result["matches"] for c in m["syntax_flow"]["calls"]]
            self.assertTrue(set(case["expected"]) <= {c["callee"] for c in calls})
            for call in calls:
                self.assertGreater(call["location"]["line"], 0)
                self.assertGreater(call["location"]["column"], 0)
            if "expected_statements" in case:
                self.assertEqual([s["expression"] for s in result["matches"][0]["syntax_flow"]["statements"]], case["expected_statements"])
        else:
            self.assertTrue(set(case["expected"]) <= {m["name"] for m in result["matches"][0]["member_anchors"]})

    def test_navigation_counts_and_overload_candidate_are_honest(self):
        self.assert_schema(self.document)
        self.assertEqual(self.document["summary"], {"units": 12, "files": 23, "types": 23, "functions": 141})
        self.assertEqual(set(self.guides), {c["id"] for c in self.cases})
        self.assertEqual(sum(g["status"] == "reviewed" for g in self.guides.values()), 29)
        for case in self.cases:
            with self.subTest(case=case["id"]):
                guide = self.guides[case["id"]]
                self.assertEqual(guide["status"], case["navigation_status"])
                self.assertEqual(len(guide["definitions"]), case["definition_count"])
        self.assertEqual(self.guides["case-23"]["evidence_status"], "partial")
        self.assertEqual(self.guides["case-21"]["role"], "internal_function")
        self.assertTrue(self.guides["case-01"]["query"]["include_syntax_flow"])

    def test_views_preserve_manual_evidence_and_delegate_facts(self):
        for case in self.cases:
            if case["kind"] != "function":
                continue
            full = self.views[case["id"]]["full"]
            for view in ("behavior", "structure"):
                with self.subTest(case=case["id"], view=view):
                    result = self.views[case["id"]][view]
                    self.assert_expected(case, result)
                    for before, after in zip(full["matches"], result["matches"]):
                        self.assertEqual(before["delegate_operations"], after["delegate_operations"])
                        self.assertEqual([(c["callee"], c["location"]["line"]) for c in before["syntax_flow"]["calls"]],
                                         [(c["callee"], c["location"]["line"]) for c in after["syntax_flow"]["calls"]])
                        self.assertEqual(before["syntax_flow"]["controls"], after["syntax_flow"]["controls"])
                        summary = after["view_summary"]
                        self.assertEqual(sum(g["count"] for g in after["symbol_groups"])
                                         + sum(g["count"] for log in after.get("log_groups", []) for g in log["symbol_groups"])
                                         + sum(summary["hidden_by_rule"].values()), summary["source_count"])

    def test_state_writes_expand_and_log_helpers_remain_grouped(self):
        for view in ("behavior", "structure"):
            ability = self.views["case-25"][view]["matches"][0]
            added = next(g for g in ability["symbol_groups"] if "->AddUnique()" in g["spelling"])
            self.assertEqual((added["receiver"], added["count"], added.get("display", "expand")), ("AbilitiesToActivate", 2, "expand"))
            tracker = self.views["case-30"][view]["matches"][0]
            written = next(g for g in tracker["symbol_groups"] if g.get("receiver") == "DirtySettings")
            self.assertEqual(written["spelling"], "TMap<FObjectKey,TWeakObjectPtr<UGameSetting>>->Add()")
            self.assertEqual(written.get("display", "expand"), "expand")
            cancel = self.views["case-26"][view]["matches"][0]
            self.assertEqual(len(cancel["log_groups"]), 2)
            self.assertTrue(all(log["callee"] == "UE_LOG" and log["display"] == "fold" for log in cancel["log_groups"]))
            self.assertTrue(all("GetName()" in g["spelling"] for log in cancel["log_groups"] for g in log["symbol_groups"]))
            self.assertFalse(any("GetName()" in g["spelling"] for g in cancel["symbol_groups"]))
            self.assertTrue(any("CancelAbility()" in g["spelling"] and g.get("display", "expand") == "expand" for g in cancel["symbol_groups"]))
        case = next(c for c in self.cases if c["id"] == "case-26")
        focused = _inspect_function_from_context(self.scope.units[case["unit"]], case["target"], view="behavior", focus=["AbilitySpec.Ability.GetName"])
        self.assert_schema(focused)
        self.assertTrue(any(g["spelling"] == "AbilitySpec.Ability.GetName()" for g in focused["matches"][0]["symbol_groups"]))

    def test_non_call_defaults_overloads_lambda_and_type_members(self):
        constructor = self.views["case-01"]["behavior"]["matches"][0]
        self.assertEqual(constructor["syntax_flow"]["calls"], [])
        self.assertEqual(constructor["statement_summary"], {"initialization": 7})
        overloads = self.views["case-23"]["behavior"]["matches"]
        implemented = next(m for m in overloads if any(c["callee"] == "Entries.AddDefaulted_GetRef" for c in m["syntax_flow"]["calls"]))
        stub = next(m for m in overloads if m is not implemented)
        self.assertEqual([c["callee"] for c in stub["syntax_flow"]["calls"]], ["unimplemented"])
        callback = self.views["case-16"]["behavior"]["matches"][0]
        indirect = next(g for g in callback["symbol_groups"] if g["spelling"] == "(StrongObject->*Function)()")
        self.assertEqual((indirect["kind"], indirect["execution_scope"]["kind"]), ("unknown", "lambda"))
        weak = next(g for g in callback["symbol_groups"] if g["spelling"] == "TWeakObjectPtr<TOwner>->Get()")
        self.assertEqual((weak.get("display", "expand"), weak["execution_scope"]["kind"]), ("expand", "lambda"))
        self.assertEqual(callback["delegate_operations"], [])
        for case in self.cases:
            if case["kind"] == "type":
                target = next(t for t in self.scope.types.values() if t["unit"] == case["unit"] and t["anchor"]["name"] == case["target"])
                members = _compound(target["raw"])["member_anchors"]
                self.assertTrue(set(case["expected"]) <= {m["name"] for m in members})
                if case["id"] == "case-03":
                    for name in ("GetPreviousTargetCache", "GetCurrentTargetCache"):
                        self.assertEqual(len([m for m in members if m["name"] == name]), 2)

    def test_real_cross_directory_pair_is_used_by_navigation(self):
        inventory = list_module_cxx_sources(PROJECT.parent / "Plugins/GameSettings/Source/GameSettings.Build.cs")
        self.assert_schema(inventory)
        pair = next(p for p in inventory["pairs"] if p["header"].endswith("/GameSettingRegistryChangeTracker.h"))
        self.assertEqual(pair["method"], "unique-module-basename")
        case = next(c for c in self.cases if c["id"] == "case-30")
        self.assertEqual(set(case["sources"]), {pair["header"], pair["cpp"]})

    def test_all_saved_queries_in_independent_old_clis(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                query = self.guides[case["id"]]["query"]
                args = ["--source", *[PROJECT.parent / p for p in case["sources"]],
                        "--function" if case["kind"] == "function" else "--type", query["selector"]]
                if case["kind"] == "function":
                    args += ["--view", query["view"], "--include-syntax-flow"]
                    for name in query["focus"]:
                        args += ["--focus", name]
                completed, result = run_cli("sourcetools/" + query["tool"] + ".py", *args)
                self.assertEqual(completed.returncode, 0, result)
                self.assertEqual(completed.stderr, "")
                self.assert_expected(case, result)


@unittest.skipUnless(PROJECT.is_file(), "Lyra reference project is not available")
class LyraRetrievalHoldoutV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((ROOT / "tests/fixtures/lyra_retrieval_holdout_v3.json").read_text(encoding="utf-8"))["cases"]
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        profile = write_json(Path(directory.name) / "holdout.json", {
            "version": 1, "id": "holdout-v3", "name": "新增保留问题", "description": "无导航提示或 focus 的通用规则检查",
            "units": [{"id": c["unit"], "sources": c["sources"]} for c in cls.cases]})
        cls.scope = SourceScope(PROJECT, profile)
        schemas = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "schemas").glob("*.schema.json")]
        registry = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in schemas)
        cls.validators = {s["$id"].rsplit(":", 1)[-1]: Draft202012Validator(s, registry=registry) for s in schemas}

    def check_result(self, case, result):
        self.validators[result["schema_version"]].validate(result)
        self.assertEqual(result["match_count"], 1)
        match = result["matches"][0]
        self.assertTrue(set(case["calls"]) <= {c["callee"] for c in match["syntax_flow"]["calls"]})
        self.assertTrue(set(case["statements"]) <= {s["expression"] for s in match["syntax_flow"]["statements"]})
        for required in case["expanded"]:
            self.assertTrue(any(all(g.get(k) == v for k, v in required.items())
                                and g.get("display", "expand") == "expand" for g in match["symbol_groups"]), (case["id"], required))

    def test_holdout_sources_do_not_enter_authored_navigation(self):
        sources = {p for c in self.cases for p in c["sources"]}
        for name in ("lyra_equipment", "lyra_reviewed_navigation", "lyra_sampling_reviewed"):
            profile = json.loads((ROOT / "sourcetools/profiles" / (name + ".json")).read_text(encoding="utf-8"))
            self.assertFalse(sources & {p for u in profile["units"] for p in u["sources"]})
        document = self.scope.navigation_map()
        self.assertTrue(all(u["review_status"] == "unreviewed" and not u.get("navigation") for u in document["units"]))

    def test_unfocused_views_keep_state_changes_and_non_call_evidence(self):
        for case in self.cases:
            loaded = self.scope.units[case["unit"]]
            full = _inspect_function_from_context(loaded, case["target"])
            for view in ("behavior", "structure"):
                with self.subTest(case=case["id"], view=view):
                    result = _inspect_function_from_context(loaded, case["target"], view=view, include_syntax_flow=True)
                    self.check_result(case, result)
                    self.assertEqual(full["matches"][0]["delegate_operations"], result["matches"][0]["delegate_operations"])

    def test_independent_old_clis_need_no_focus(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                completed, result = run_cli("sourcetools/ue_inspect_cxx_function.py", "--source",
                                            *[PROJECT.parent / p for p in case["sources"]], "--function", case["target"],
                                            "--view", "behavior", "--include-syntax-flow")
                self.assertEqual(completed.returncode, 0, result)
                self.check_result(case, result)


if __name__ == "__main__":
    unittest.main()
