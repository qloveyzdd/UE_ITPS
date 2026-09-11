"""A saved navigation map locates fresh, ordinary SourceTools queries."""
from __future__ import annotations

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
from ue_project_tools.source_unit import inspect_source_function, list_source_functions


class NavigationMapTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.fixture = create_fixture(Path(directory.name))
        self.profile = write_json(Path(directory.name) / "scope.json", {
            "version": 1, "id": "sample", "name": "测试系统", "description": "入口导航",
            "units": [{"id": "worker", "sources": [
                p.relative_to(self.fixture.project.parent).as_posix()
                for p in (self.fixture.source, self.fixture.header)],
                "roles": {"AWorker": ["工作入口"]},
                "entry_points": ["AWorker::BeginPlay"]}],
        })

    def saved_map(self):
        document = SourceScope(self.fixture.project, self.profile).navigation_map()
        path = write_json(self.profile.parent / "map.json", document)
        # This is an artifact read, not a source read; no live Scope object survives.
        return json.loads(path.read_text(encoding="utf-8"))

    def sources(self, document):
        return [Path(document["project"]).parent / p for p in document["units"][0]["sources"]]

    def validate(self, document):
        schema = json.loads((ROOT / "schemas/source_navigation_map.schema.json").read_text(encoding="utf-8"))
        common = json.loads((ROOT / "schemas/common.schema.json").read_text(encoding="utf-8"))
        registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
        Draft202012Validator(schema, registry=registry).validate(document)

    def test_saved_map_uses_old_queries_without_rebuilding_scope(self):
        document = self.saved_map()
        self.validate(document)
        unit = document["units"][0]
        self.assertEqual(unit["types"], [{"name": "AWorker", "kind": "class",
                                         "roles": ["工作入口"], "definition_count": 1}])
        self.assertEqual(unit["entry_points"], [{"name": "AWorker::BeginPlay", "definition_count": 1}])
        self.assertNotIn("AWorker::Helper", json.dumps(document))
        with patch("ue_project_tools.source_scope.load_source_context", side_effect=AssertionError("Scope was rebuilt")):
            result = inspect_source_function(self.sources(document), unit["entry_points"][0]["name"])
            inventory = list_source_functions(self.sources(document))
        self.assertEqual(result["match_count"], 1)
        self.assertIn("AWorker::Helper", {f["qualified_name"] for f in inventory["functions"]})

    def test_implementation_changes_are_read_fresh(self):
        document = self.saved_map()
        write_text(self.fixture.source, "void AWorker::BeginPlay() { NewlyAdded(); }")
        result = inspect_source_function(self.sources(document), document["units"][0]["entry_points"][0]["name"])
        self.assertEqual(result["match_count"], 1)
        self.assertIn("NewlyAdded()", {s["spelling"] for s in result["matches"][0]["external_symbols"]})
        self.assertNotIn("NewlyAdded", json.dumps(document))

    def test_renamed_entry_or_missing_file_requires_navigation_refresh(self):
        document = self.saved_map()
        write_text(self.fixture.source, "void AWorker::Renamed() { NewCall(); }")
        result = inspect_source_function(self.sources(document), document["units"][0]["entry_points"][0]["name"])
        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(result["match_count"], 0)
        inventory = list_source_functions(self.sources(document))
        self.assertEqual([f["qualified_name"] for f in inventory["functions"]], ["AWorker::Renamed"])
        self.fixture.source.unlink()
        with self.assertRaisesRegex(ValueError, "not a file"):
            inspect_source_function(self.sources(document), "AWorker::BeginPlay")

    def test_same_name_definitions_remain_explicitly_ambiguous(self):
        write_text(self.fixture.header, "class AWorker { void BeginPlay() {} }; class AWorker { void BeginPlay() {} }; struct Unclassified {};")
        write_text(self.fixture.source, "// Definitions are in the header.")
        document = self.saved_map()
        self.validate(document)
        unit = document["units"][0]
        self.assertEqual(unit["types"][0]["definition_count"], 2)
        self.assertEqual(unit["types"][1]["roles"], [])
        self.assertEqual(unit["entry_points"][0]["definition_count"], 2)
        result = inspect_source_function(self.sources(document), unit["entry_points"][0]["name"])
        self.assertEqual(result["match_count"], 2)

    def test_export_cli_and_input_errors(self):
        output = self.profile.parent / "export.json"
        completed, document = run_cli("sourcetools/lyra/export_navigation_map.py", "--project", self.fixture.project,
                                      "--profile", self.profile, "--output", output)
        self.assertEqual(completed.returncode, 0, document)
        self.assertEqual(completed.stderr, "")
        self.validate(document)
        self.assertEqual(document, self.saved_map())
        self.assertEqual(document, json.loads(output.read_text(encoding="utf-8")))
        completed, error = run_cli("sourcetools/lyra/export_navigation_map.py", "--project", self.fixture.project)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stderr, "")
        self.validate(error)


if __name__ == "__main__":
    unittest.main()
