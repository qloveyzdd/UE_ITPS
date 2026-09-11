"""Real Lyra navigation checks; source content is read only by SourceTools."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from tests.support import ROOT, write_json

sys.path.insert(0, str(ROOT / "sourcetools"))
from ue_project_tools.source_scope import SourceScope
from ue_project_tools.source_function_references import _inspect_function_from_context, _list_functions_from_context
from ue_project_tools.source_type_facts import _list_types_from_context


PROJECT = ROOT / "LyraStarterGame/LyraStarterGame.uproject"


@unittest.skipUnless(PROJECT.is_file(), "Lyra reference project is not available")
class LyraScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scope = SourceScope(PROJECT, ROOT / "sourcetools/profiles/lyra_equipment.json")

    def test_equipment_inventory_entries_and_unclassified_definition(self):
        result = self.scope.query()
        self.assertEqual({k: result["summary"][k] for k in ("units", "files", "types", "functions")},
                         {"units": 6, "files": 12, "types": 13, "functions": 60})
        self.assertEqual(result["summary"]["unclassified_types"], 1)
        entries = {i["name"] for i in result["items"] if i.get("entry_point")}
        self.assertIn("ULyraEquipmentManagerComponent::EquipItem", entries)
        self.assertIn("ULyraEquipmentManagerComponent::UnequipItem", entries)
        unclassified = self.scope.query(focus=["TStructOpsTypeTraits<FLyraEquipmentList>"])["items"][0]
        self.assertEqual(unclassified["name"], "TStructOpsTypeTraits<FLyraEquipmentList>")
        self.assertEqual(unclassified["roles"], [])

    def test_equip_item_route_reaches_exact_add_entry_evidence(self):
        manager = next(t["anchor"] for t in self.scope.types.values() if t["anchor"]["name"] == "ULyraEquipmentManagerComponent")
        details = self.scope.query(level="type", select=manager["id"], limit=100)
        function = next(i for i in details["items"] if i.get("name") == "ULyraEquipmentManagerComponent::EquipItem")
        relations = self.scope.query(level="function", select=function["id"])["items"]
        relation = next(i for i in relations if i["target"] == "FLyraEquipmentList->AddEntry()")
        self.assertEqual(relation["status"], "syntax_candidate")
        evidence = self.scope.query(level="evidence", select=relation["id"])["items"]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["call"]["arguments"], ["EquipmentClass"])
        self.assertEqual(evidence[0]["call"]["expression"], "EquipmentList.AddEntry(EquipmentClass)")
        self.assertTrue(evidence[0]["evidence"]["path"].endswith("LyraEquipmentManagerComponent.cpp"))

    def test_overview_and_four_step_payload_against_full_scope(self):
        def size(value):
            return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

        baseline = 0
        for loaded in self.scope.units.values():
            functions = _list_functions_from_context(loaded)
            baseline += size(_list_types_from_context(loaded)) + size(functions)
            for selector in sorted({f["qualified_name"] for f in functions["functions"]}):
                baseline += size(_inspect_function_from_context(loaded, selector))
        overview = self.scope.query()
        self.assertLess(size(overview), baseline / 2)
        manager = next(t["anchor"] for t in self.scope.types.values() if t["anchor"]["name"] == "ULyraEquipmentManagerComponent")
        details = self.scope.query(level="type", select=manager["id"])
        entry = next(i for i in details["items"] if i.get("name") == "ULyraEquipmentManagerComponent::EquipItem")
        function = self.scope.query(level="function", select=entry["id"])
        relation = next(i for i in function["items"] if i["target"] == "FLyraEquipmentList->AddEntry()")
        evidence = self.scope.query(level="evidence", select=relation["id"])
        self.assertLess(sum(map(size, (overview, details, function, evidence))), baseline)

    def test_real_lyra_delegates_are_preserved_in_supplementary_scope(self):
        # The equipment sample has no delegate operations; exercise them in AsyncMixin.
        with tempfile.TemporaryDirectory() as directory:
            profile = write_json(Path(directory) / "async.json", {
                "version": 1, "id": "async", "name": "异步加载", "description": "委托证据回归",
                "units": [{"id": "async", "sources": [
                    "Plugins/AsyncMixin/Source/Private/AsyncMixin.cpp",
                    "Plugins/AsyncMixin/Source/Public/AsyncMixin.h"]}],
            })
            scope = SourceScope(PROJECT, profile)
            expected = []
            for function in scope.functions.values():
                raw = function["raw"]
                expected.extend(scope.units["async"]["cpp_model"]["references"][raw["occurrence_id"]]["delegate_operations"])
            self.assertTrue(expected)
            actual = []
            for function_id in scope.functions:
                offset = 0
                while offset is not None:
                    result = scope.query(level="evidence", select=function_id, offset=offset, limit=100)
                    actual.extend(i["fact"] for i in result["items"] if i["kind"] == "delegate")
                    offset = result["page"]["next_offset"]
            self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
