from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
V4_ROOT = REPOSITORY_ROOT / "v4"
for path in (str(REPOSITORY_ROOT), str(V4_ROOT)):
    while path in sys.path:
        sys.path.remove(path)
sys.path.insert(0, str(V4_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT))

from tests.support import create_fixture
from ue_itps_v4 import build_graph, query_graph
from ue_itps_v4.batch_analyzer import analyze_source_unit
from ue_project_tools.source_unit import (
    inspect_source_function,
    list_source_functions,
    list_source_includes,
    list_source_types,
)


class GraphWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = create_fixture(self.root)
        self.database = self.root / "graph.sqlite3"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_build_and_query_resolved_relations(self) -> None:
        build = build_graph(self.fixture.project, self.database)
        self.assertGreater(build["node_count"], 0)
        self.assertGreater(build["relation_count"], 0)

        query = query_graph(
            self.database,
            "Gameplay::ASampleActor::BeginPlay",
            depth=1,
        )
        self.assertEqual(query["status"], "selected")
        nodes_by_name = {item["name"]: item for item in query["nodes"]}
        self.assertIn("Helper", nodes_by_name)
        self.assertIn("Utility", nodes_by_name)
        calls = [
            relation
            for relation in query["relations"]
            if relation["kind"] == "CALLS"
        ]
        self.assertEqual(len(calls), 2)
        self.assertTrue(
            all(relation["certainty"] == "inferred" for relation in calls)
        )
        references = [
            relation
            for relation in query["relations"]
            if relation["kind"] == "REFERENCES"
        ]
        self.assertTrue(
            all(relation["certainty"] == "observed" for relation in references)
        )

    def test_ambiguous_name_returns_candidates_without_guessing(self) -> None:
        build_graph(self.fixture.project, self.database)
        result = query_graph(self.database, "SampleGame")
        self.assertEqual(result["status"], "ambiguous")
        self.assertGreaterEqual(len(result["candidates"]), 2)
        self.assertEqual(result["nodes"], [])

    def test_unchanged_function_probes_are_loaded_from_cache(self) -> None:
        first = build_graph(
            self.fixture.project,
            self.database,
            workers=1,
        )
        with patch(
            "ue_itps_v4.probe_adapter.analyze_source_unit",
            side_effect=AssertionError("source-unit cache was not used"),
        ):
            second = build_graph(
                self.fixture.project,
                self.database,
                workers=1,
            )
        self.assertEqual(first["scan_id"], second["scan_id"])
        self.assertEqual(first["node_count"], second["node_count"])
        self.assertEqual(first["relation_count"], second["relation_count"])
        self.assertEqual(second["cache_hits"], second["source_unit_count"])
        self.assertEqual(second["cache_misses"], 0)

    def test_changed_source_invalidates_function_probe_cache(self) -> None:
        build_graph(
            self.fixture.project,
            self.database,
            workers=1,
        )
        original = self.fixture.source_cpp.read_text(encoding="utf-8")
        self.fixture.source_cpp.write_text(
            original.replace("Count = 1;", "Count = 2;"),
            encoding="utf-8",
        )
        with patch(
            "ue_itps_v4.probe_adapter.analyze_source_unit",
            wraps=analyze_source_unit,
        ) as unit_probe:
            result = build_graph(
                self.fixture.project,
                self.database,
                workers=1,
            )
        self.assertEqual(unit_probe.call_count, 1)
        self.assertEqual(result["cache_misses"], 1)

    def test_batch_analyzer_parses_once_and_matches_legacy_facts(self) -> None:
        with patch(
            "ue_itps_v4.batch_analyzer.load_source_context",
            wraps=__import__(
                "ue_itps_v4.batch_analyzer",
                fromlist=["load_source_context"],
            ).load_source_context,
        ) as context_loader:
            batch = analyze_source_unit(self.fixture.source_cpp)
        self.assertEqual(context_loader.call_count, 1)
        self.assertEqual(batch.parse_count, 1)
        self.assertEqual(
            batch.types,
            list_source_types(self.fixture.source_cpp),
        )
        self.assertEqual(
            batch.includes,
            list_source_includes(self.fixture.source_cpp),
        )
        self.assertEqual(
            batch.functions,
            list_source_functions(self.fixture.source_cpp),
        )
        names = sorted(
            {
                item["name"]
                for item in batch.functions["functions"]
                if item["definitions"]
            },
            key=str.casefold,
        )
        self.assertEqual(
            batch.function_references,
            [
                inspect_source_function(self.fixture.source_cpp, name)
                for name in names
            ],
        )

    def test_single_and_multi_process_graphs_are_deterministic(self) -> None:
        single_database = self.root / "single.sqlite3"
        multi_database = self.root / "multi.sqlite3"
        single = build_graph(
            self.fixture.project,
            single_database,
            cache_dir=self.root / "single-cache",
            workers=1,
        )
        multi = build_graph(
            self.fixture.project,
            multi_database,
            cache_dir=self.root / "multi-cache",
            workers=2,
        )
        self.assertEqual(single["scan_id"], multi["scan_id"])
        self.assertEqual(single["node_count"], multi["node_count"])
        self.assertEqual(single["relation_count"], multi["relation_count"])
        self.assertEqual(
            query_graph(
                single_database,
                "Gameplay::ASampleActor::BeginPlay",
                depth=2,
            ),
            query_graph(
                multi_database,
                "Gameplay::ASampleActor::BeginPlay",
                depth=2,
            ),
        )

    def test_interrupted_scan_resumes_from_completed_unit_cache(self) -> None:
        cache_dir = self.root / "resume-cache"
        calls = 0

        def fail_after_first(source_file: Path, **kwargs: object):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("simulated interruption")
            return analyze_source_unit(source_file, **kwargs)

        with patch(
            "ue_itps_v4.probe_adapter.analyze_source_unit",
            side_effect=fail_after_first,
        ):
            with self.assertRaises(RuntimeError):
                build_graph(
                    self.fixture.project,
                    self.database,
                    cache_dir=cache_dir,
                    workers=1,
                )

        result = build_graph(
            self.fixture.project,
            self.database,
            cache_dir=cache_dir,
            workers=1,
        )
        self.assertGreaterEqual(result["cache_hits"], 1)
        self.assertEqual(
            result["cache_hits"] + result["cache_misses"],
            result["source_unit_count"],
        )

    def test_results_validate_against_v4_schemas(self) -> None:
        build = build_graph(self.fixture.project, self.database)
        query = query_graph(
            self.database,
            "Gameplay::ASampleActor",
            depth=2,
        )
        build_schema = json.loads(
            (V4_ROOT / "schemas" / "build_graph.schema.json").read_text(
                encoding="utf-8"
            )
        )
        query_schema = json.loads(
            (V4_ROOT / "schemas" / "query_graph.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator(build_schema).validate(build)
        Draft202012Validator(query_schema).validate(query)

    def test_database_contains_raw_probe_evidence(self) -> None:
        build_graph(self.fixture.project, self.database)
        connection = sqlite3.connect(self.database)
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM probe_results"
            ).fetchone()[0]
            self.assertGreater(count, 0)
        finally:
            connection.close()

    def test_cache_keeps_one_atomic_file_per_function_match(self) -> None:
        result = build_graph(
            self.fixture.project,
            self.database,
            workers=1,
        )
        cache_root = Path(result["cache_directory"])
        reference_files = [
            path
            for path in cache_root.rglob("references/*.json")
            if path.name != "index.json"
        ]
        self.assertGreater(len(reference_files), 0)
        for path in reference_files:
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["match_count"], 1)
            self.assertEqual(len(document["matches"]), 1)
        for index_path in cache_root.rglob("references/index.json"):
            index = json.loads(index_path.read_text(encoding="utf-8"))
            actual = {
                path.name
                for path in index_path.parent.glob("*.json")
                if path.name != "index.json"
            }
            self.assertEqual(actual, set(index["files"]))
        complete_markers = list(cache_root.rglob("complete.json"))
        self.assertEqual(
            len(complete_markers),
            result["source_unit_count"],
        )


if __name__ == "__main__":
    unittest.main()
