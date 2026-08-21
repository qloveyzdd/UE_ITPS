from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INFORMATION_POOL_ROOT = REPOSITORY_ROOT / "information_pool"
for path in (str(REPOSITORY_ROOT), str(INFORMATION_POOL_ROOT)):
    while path in sys.path:
        sys.path.remove(path)
sys.path.insert(0, str(INFORMATION_POOL_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT))

from tests.support import create_fixture, write_text  # noqa: E402
from ue_itps_information_pool import (  # noqa: E402
    build_information_pool,
    query_information_pool,
)
from ue_itps_information_pool.batch_analyzer import analyze_source_unit  # noqa: E402
from ue_itps_information_pool.graph_model import Graph  # noqa: E402
from ue_itps_information_pool.identity import symbol_id  # noqa: E402
from ue_itps_information_pool.probe_adapter import (  # noqa: E402
    SourceUnitProbe,
    _raw_probe_results,
)
from ue_project_tools.source_unit import (  # noqa: E402
    inspect_source_function,
    list_source_functions,
    list_source_includes,
    list_source_types,
)


class InformationPoolWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = create_fixture(self.root)
        self.pool = self.root / ".information-pool"
        (self.root / ".gitignore").write_text(
            ".information-pool/\n.pool-*/\n",
            encoding="utf-8",
        )
        self._git("init", "--quiet")
        self._git("config", "user.email", "tests@ue-itps.invalid")
        self._git("config", "user.name", "UE ITPS Tests")
        self._git("add", ".")
        self._git("commit", "--quiet", "-m", "fixture")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _git(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        return result.stdout.strip()

    def _commit(self, message: str) -> str:
        self._git("add", ".")
        self._git("commit", "--quiet", "-m", message)
        return self._git("rev-parse", "HEAD")

    def _write_delegate_fixture(self) -> None:
        write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Public"
            / "DelegateSample.h",
            """
            #pragma once

            class FDelegateOwner
            {
            public:
                DECLARE_EVENT_OneParam(FDelegateOwner, FChangedEvent, int32 Value)
                FChangedEvent OnChanged;
                void Publish();
            };

            class SDelegateSubscriber
            {
            public:
                void Subscribe(FDelegateOwner* Owner);
                void HandleChanged(int32 Value);
            };
            """,
        )
        write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Private"
            / "DelegateSample.cpp",
            """
            #include "DelegateSample.h"

            void FDelegateOwner::Publish()
            {
                OnChanged.Broadcast(1);
            }

            void SDelegateSubscriber::Subscribe(FDelegateOwner* Owner)
            {
                Owner->OnChanged.AddSP(this, &SDelegateSubscriber::HandleChanged);
            }

            void SDelegateSubscriber::HandleChanged(int32 Value)
            {
            }
            """,
        )

    def _write_gameplay_message_knowledge_graph(self) -> Path:
        self.pool.mkdir(parents=True, exist_ok=True)
        path = self.pool / "gameplay-messages.json"
        publisher_key = "/Game/BP_MessagePublisher|EventGraph|Broadcast"
        subscriber_key = "/Game/BP_MessageSubscriber|EventGraph|Listen"
        document = {
            "schema_version": "ue_build_knowledge_graph",
            "validation": {"status": "ok"},
            "graph": {
                "counts": {"nodes": 4, "relations": 3, "evidence": 3},
                "nodes": [
                    {
                        "node_id": "cxx-publisher",
                        "kind": "cxx_function",
                        "name": "BeginPlay",
                        "properties": {
                            "qualified_name": "Gameplay::ASampleActor::BeginPlay"
                        },
                    },
                    {
                        "node_id": "blueprint-publisher",
                        "kind": "blueprint_node",
                        "name": "Broadcast Message",
                        "canonical_key": (
                            f"Sample|blueprint_node|{publisher_key}"
                        ),
                        "properties": {"asset": "/Game/BP_MessagePublisher"},
                    },
                    {
                        "node_id": "blueprint-subscriber",
                        "kind": "blueprint_node",
                        "name": "ListenForGameplayMessages",
                        "canonical_key": (
                            f"Sample|blueprint_node|{subscriber_key}"
                        ),
                        "properties": {"asset": "/Game/BP_MessageSubscriber"},
                    },
                    {
                        "node_id": "message-tag",
                        "kind": "gameplay_tag",
                        "name": "Gameplay.Message.Test",
                        "canonical_key": (
                            "Sample|gameplay_tag|Gameplay.Message.Test"
                        ),
                        "properties": {"tag": "Gameplay.Message.Test"},
                    },
                ],
                "relations": [
                    {
                        "relation_id": "cxx-publishes",
                        "source_id": "cxx-publisher",
                        "kind": "PUBLISHES_EVENT",
                        "target_id": "message-tag",
                        "certainty": "confirmed",
                    },
                    {
                        "relation_id": "blueprint-publishes",
                        "source_id": "blueprint-publisher",
                        "kind": "PUBLISHES_EVENT",
                        "target_id": "message-tag",
                        "certainty": "confirmed",
                    },
                    {
                        "relation_id": "blueprint-subscribes",
                        "source_id": "blueprint-subscriber",
                        "kind": "SUBSCRIBES_EVENT",
                        "target_id": "message-tag",
                        "certainty": "confirmed",
                        "properties": {"match_type": "ExactMatch"},
                    },
                ],
                "evidence": [
                    {
                        "evidence_id": "cxx-publish-evidence",
                        "relation_id": "cxx-publishes",
                        "path": "Source/SampleGame/Private/SampleActor.cpp",
                        "line": 7,
                    },
                    {
                        "evidence_id": "blueprint-publish-evidence",
                        "relation_id": "blueprint-publishes",
                        "node": publisher_key,
                    },
                    {
                        "evidence_id": "blueprint-subscribe-evidence",
                        "relation_id": "blueprint-subscribes",
                        "node": subscriber_key,
                    },
                ],
            },
        }
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def test_gameplay_message_publishers_reach_blueprint_subscriber(self) -> None:
        knowledge_graph = self._write_gameplay_message_knowledge_graph()
        build = build_information_pool(
            self.fixture.project,
            self.pool,
            knowledge_graphs=[knowledge_graph],
        )

        connection = sqlite3.connect(build["snapshot"])
        connection.row_factory = sqlite3.Row
        try:
            dispatches = connection.execute(
                """
                SELECT r.properties_json
                FROM relations r
                JOIN nodes source ON source.node_id = r.source_id
                JOIN nodes target ON target.node_id = r.target_id
                WHERE r.kind = 'DISPATCHES_TO'
                  AND source.kind = 'gameplay_tag'
                  AND target.kind = 'blueprint_node'
                """
            ).fetchall()
            self.assertEqual(len(dispatches), 1)
            bridge = json.loads(dispatches[0]["properties_json"])
            self.assertEqual(len(bridge["publisher_relation_ids"]), 2)
            self.assertTrue(bridge["subscriber_relation_id"])
        finally:
            connection.close()

        expected_relations = ["PUBLISHES_EVENT", "DISPATCHES_TO"]
        cxx_path = query_information_pool(
            self.pool,
            "path",
            selector="Gameplay::ASampleActor::BeginPlay",
            target="/Game/BP_MessageSubscriber|EventGraph|Listen",
            depth=3,
        )
        self.assertEqual(cxx_path["status"], "selected")
        self.assertEqual(
            [item["kind"] for item in cxx_path["result"]["relations"]],
            expected_relations,
        )

        blueprint_path = query_information_pool(
            self.pool,
            "path",
            selector="/Game/BP_MessagePublisher|EventGraph|Broadcast",
            target="/Game/BP_MessageSubscriber|EventGraph|Listen",
            depth=3,
        )
        self.assertEqual(blueprint_path["status"], "selected")
        self.assertEqual(
            [item["kind"] for item in blueprint_path["result"]["relations"]],
            expected_relations,
        )

    def test_delegate_publish_subscribe_edges_form_runtime_path(self) -> None:
        self._write_delegate_fixture()
        self._commit("add delegate fixture")

        build_information_pool(self.fixture.project, self.pool)
        path = query_information_pool(
            self.pool,
            "path",
            selector="FDelegateOwner::Publish",
            target="SDelegateSubscriber::HandleChanged",
            depth=4,
        )

        self.assertEqual(path["status"], "selected")
        self.assertEqual(
            [item["qualified_name"] for item in path["result"]["path"]],
            [
                "FDelegateOwner::Publish",
                "FDelegateOwner::OnChanged",
                "SDelegateSubscriber::HandleChanged",
            ],
        )
        self.assertEqual(
            [item["kind"] for item in path["result"]["relations"]],
            ["PUBLISHES_EVENT", "DISPATCHES_TO"],
        )

        lookup = query_information_pool(
            self.pool,
            "lookup",
            selector="SDelegateSubscriber::Subscribe",
            depth=1,
        )
        relations = {
            item["kind"] for item in lookup["result"]["relations"]
        }
        self.assertIn("SUBSCRIBES_EVENT", relations)
        self.assertIn("BINDS_CALLBACK", relations)

    def test_build_and_query_resolved_relations(self) -> None:
        build = build_information_pool(self.fixture.project, self.pool)
        self.assertGreater(build["node_count"], 0)
        self.assertGreater(build["relation_count"], 0)

        response = query_information_pool(
            self.pool,
            "lookup",
            selector="Gameplay::ASampleActor::BeginPlay",
            depth=1,
        )
        query = response["result"]
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
        call_targets = {relation["target_id"] for relation in calls}
        self.assertFalse(
            call_targets.intersection(
                relation["target_id"] for relation in references
            )
        )

    def test_relation_identity_merges_multiple_evidence_locations(self) -> None:
        graph = Graph("SampleGame|SampleGame.uproject", "project:test")
        for line in (10, 20):
            graph.add_relation(
                source_id="source",
                kind="CALLS",
                target_id="target",
                certainty="inferred",
                resolution_status="resolved",
                confidence=0.85,
                probe_schema="test",
                location={
                    "root": "project",
                    "path": "Source/Test.cpp",
                    "line": line,
                },
            )
        self.assertEqual(len(graph.relations), 1)
        self.assertEqual(len(graph.evidence), 2)

    def test_class_path_projects_member_call_to_owner_types(self) -> None:
        self.fixture.source_header.write_text(
            self.fixture.source_header.read_text(encoding="utf-8").replace(
                "extern int32 GSampleCount;",
                """
        class AHelperService : public AActor
        {
        public:
            void Execute();
        };

extern int32 GSampleCount;""",
            ),
            encoding="utf-8",
        )
        self.fixture.source_cpp.write_text(
            self.fixture.source_cpp.read_text(encoding="utf-8").replace(
                """    FGameplayTag Tag;
    Helper();""",
                """    FGameplayTag Tag;
    AHelperService Service;
    Service.Execute();
    Helper();""",
            ).replace(
                "void ASampleActor::Helper()",
                """void AHelperService::Execute() {}

void ASampleActor::Helper()""",
            ),
            encoding="utf-8",
        )
        self._commit("add helper service")
        build_information_pool(self.fixture.project, self.pool)

        result = query_information_pool(
            self.pool,
            "path",
            selector="Gameplay::ASampleActor",
            target="Gameplay::AHelperService",
        )["result"]
        self.assertEqual(result["status"], "selected")
        self.assertEqual(
            [item["qualified_name"] for item in result["path"]],
            ["Gameplay::ASampleActor", "Gameplay::AHelperService"],
        )
        self.assertEqual([item["kind"] for item in result["relations"]], ["CALLS"])
        self.assertEqual(result["relations"][0]["member_relation_count"], 1)

    def test_ambiguous_name_returns_candidates_without_guessing(self) -> None:
        build_information_pool(self.fixture.project, self.pool)
        result = query_information_pool(
            self.pool,
            "lookup",
            selector="SampleGame",
        )["result"]
        self.assertEqual(result["status"], "ambiguous")
        self.assertGreaterEqual(len(result["candidates"]), 2)
        self.assertEqual(result["nodes"], [])

    def test_qualified_type_resolution_does_not_fall_back_to_short_name(self) -> None:
        graph = Graph("SampleGame|SampleGame.uproject", "project:test")
        expected_id = ""
        for qualified_name in ("EWindowMode::Type", "ETravelFailure::Type"):
            node_id, canonical_key = symbol_id(
                graph.key,
                kind="enum",
                qualified_name=qualified_name,
            )
            graph.add_node(
                node_id=node_id,
                kind="enum",
                name="Type",
                qualified_name=qualified_name,
                canonical_key=canonical_key,
            )
            if qualified_name == "EWindowMode::Type":
                expected_id = node_id

        exact = graph.resolve("type", "EWindowMode::Type")
        self.assertEqual(exact.status, "resolved")
        self.assertEqual(exact.node_id, expected_id)
        self.assertEqual(exact.candidates, [expected_id])

        missing = graph.resolve("type", "EWorldType::Type")
        self.assertEqual(missing.status, "unresolved")
        self.assertEqual(missing.candidates, [])

    def test_unchanged_function_probes_are_loaded_from_cache(self) -> None:
        first = build_information_pool(
            self.fixture.project,
            self.pool,
            workers=1,
        )
        with patch(
            "ue_itps_information_pool.probe_adapter.analyze_source_unit",
            side_effect=AssertionError("source-unit cache was not used"),
        ):
            second = build_information_pool(
                self.fixture.project,
                self.pool,
                workers=1,
            )
        self.assertEqual(first["generation_id"], second["generation_id"])
        self.assertEqual(first["node_count"], second["node_count"])
        self.assertEqual(first["relation_count"], second["relation_count"])
        self.assertEqual(second["cache_hits"], second["source_unit_count"])
        self.assertEqual(second["cache_misses"], 0)

    def test_changed_source_invalidates_function_probe_cache(self) -> None:
        build_information_pool(
            self.fixture.project,
            self.pool,
            workers=1,
        )
        original = self.fixture.source_cpp.read_text(encoding="utf-8")
        self.fixture.source_cpp.write_text(
            original.replace("Count = 1;", "Count = 2;"),
            encoding="utf-8",
        )
        self._commit("change source")
        with patch(
            "ue_itps_information_pool.probe_adapter.analyze_source_unit",
            wraps=analyze_source_unit,
        ) as unit_probe:
            result = build_information_pool(
                self.fixture.project,
                self.pool,
                workers=1,
            )
        self.assertEqual(unit_probe.call_count, 1)
        self.assertEqual(result["cache_misses"], 1)

    def test_batch_analyzer_parses_once_and_matches_legacy_facts(self) -> None:
        with patch(
            "ue_itps_information_pool.batch_analyzer.load_source_context",
            wraps=__import__(
                "ue_itps_information_pool.batch_analyzer",
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
        single_pool = self.root / ".pool-single"
        multi_pool = self.root / ".pool-multi"
        single = build_information_pool(
            self.fixture.project,
            single_pool,
            workers=1,
        )
        multi = build_information_pool(
            self.fixture.project,
            multi_pool,
            workers=2,
        )
        self.assertEqual(single["generation_id"], multi["generation_id"])
        self.assertEqual(single["node_count"], multi["node_count"])
        self.assertEqual(single["relation_count"], multi["relation_count"])
        self.assertEqual(
            query_information_pool(
                single_pool,
                "lookup",
                selector="Gameplay::ASampleActor::BeginPlay",
                depth=2,
            ),
            query_information_pool(
                multi_pool,
                "lookup",
                selector="Gameplay::ASampleActor::BeginPlay",
                depth=2,
            ),
        )

    def test_interrupted_scan_resumes_from_completed_unit_cache(self) -> None:
        cache_dir = self.pool / "resume-cache"
        calls = 0

        def fail_after_first(source_file: Path, **kwargs: object):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("simulated interruption")
            return analyze_source_unit(source_file, **kwargs)

        with patch(
            "ue_itps_information_pool.probe_adapter.analyze_source_unit",
            side_effect=fail_after_first,
        ):
            with self.assertRaises(RuntimeError):
                build_information_pool(
                    self.fixture.project,
                    self.pool,
                    cache_dir=cache_dir,
                    workers=1,
                )

        result = build_information_pool(
            self.fixture.project,
            self.pool,
            cache_dir=cache_dir,
            workers=1,
        )
        self.assertGreaterEqual(result["cache_hits"], 1)
        self.assertEqual(
            result["cache_hits"] + result["cache_misses"],
            result["source_unit_count"],
        )

    def test_results_validate_against_information_pool_schemas(self) -> None:
        build = build_information_pool(self.fixture.project, self.pool)
        query = query_information_pool(
            self.pool,
            "lookup",
            selector="Gameplay::ASampleActor",
            depth=2,
        )
        build_schema = json.loads(
            (
                INFORMATION_POOL_ROOT
                / "schemas"
                / "build_information_pool.schema.json"
            ).read_text(encoding="utf-8")
        )
        query_schema = json.loads(
            (
                INFORMATION_POOL_ROOT
                / "schemas"
                / "query_information_pool.schema.json"
            ).read_text(encoding="utf-8")
        )
        Draft202012Validator(build_schema).validate(build)
        Draft202012Validator(query_schema).validate(query)

    def test_database_contains_raw_probe_evidence(self) -> None:
        build = build_information_pool(self.fixture.project, self.pool)
        connection = sqlite3.connect(build["snapshot"])
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM probe_results"
            ).fetchone()[0]
            self.assertGreater(count, 0)
        finally:
            connection.close()

    def test_overloaded_function_probe_documents_have_distinct_keys(self) -> None:
        unit = SourceUnitProbe(
            entry="Source/Test.cpp",
            unit_paths=("Source/Test.cpp",),
            owner_by_path={},
            types={"schema_version": "types"},
            includes={"schema_version": "includes"},
            functions={"schema_version": "functions"},
            function_references=[
                {
                    "schema_version": "references",
                    "selection": {"name": "Overloaded"},
                    "matches": [
                        {
                            "function_id": "overload:same-id",
                            "function": {"signature": "int32 Overloaded()"},
                        }
                    ],
                },
                {
                    "schema_version": "references",
                    "selection": {"name": "Overloaded"},
                    "matches": [
                        {
                            "function_id": "overload:same-id",
                            "function": {"signature": "float Overloaded()"},
                        }
                    ],
                },
                {
                    "schema_version": "references",
                    "selection": {"name": "Overloaded"},
                    "matches": [
                        {
                            "function_id": "overload:same-id",
                            "function": {"signature": "int32 Overloaded()"},
                        }
                    ],
                },
            ],
            input_hash="input",
            cache_status="miss",
            parse_count=1,
        )
        results = _raw_probe_results(unit)
        keys = [item["probe_key"] for item in results]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(results), 5)

    def test_cache_keeps_one_atomic_file_per_function_match(self) -> None:
        result = build_information_pool(
            self.fixture.project,
            self.pool,
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

    def test_build_requires_clean_git_and_binds_head_commit(self) -> None:
        self.fixture.source_cpp.write_text(
            self.fixture.source_cpp.read_text(encoding="utf-8") + "\n// dirty\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "must be clean"):
            build_information_pool(self.fixture.project, self.pool)
        self.assertFalse((self.pool / "manifest.json").exists())

        self._git("restore", ".")
        (self.root / "unrelated-tool-change.txt").write_text(
            "not part of the selected UE project",
            encoding="utf-8",
        )
        result = build_information_pool(self.fixture.project, self.pool)
        self.assertEqual(result["source_commit"], self._git("rev-parse", "HEAD"))

    def test_failed_candidate_does_not_replace_active_snapshot(self) -> None:
        first = build_information_pool(self.fixture.project, self.pool)
        manifest = (self.pool / "manifest.json").read_bytes()
        with patch(
            "ue_itps_information_pool.builder.validate_snapshot",
            return_value=[{"code": "forced", "message": "forced failure"}],
        ):
            with self.assertRaisesRegex(ValueError, "failed validation"):
                build_information_pool(self.fixture.project, self.pool)
        self.assertEqual((self.pool / "manifest.json").read_bytes(), manifest)
        active = query_information_pool(
            self.pool,
            "lookup",
            selector="Gameplay::ASampleActor",
        )
        self.assertEqual(
            active["generation"]["generation_id"],
            first["generation_id"],
        )

    def test_task_queries_use_the_activated_snapshot(self) -> None:
        build_information_pool(self.fixture.project, self.pool)

        search = query_information_pool(
            self.pool,
            "search",
            selector="SampleActor",
        )
        self.assertEqual(search["status"], "selected")
        self.assertTrue(
            any(
                item["name"] == "ASampleActor"
                for item in search["result"]["matches"]
            )
        )

        hierarchy = query_information_pool(
            self.pool,
            "hierarchy",
            selector="Gameplay::ASampleActor",
        )
        self.assertEqual(hierarchy["status"], "selected")

        impact = query_information_pool(
            self.pool,
            "impact",
            selector="Gameplay::ASampleActor::Helper",
        )
        self.assertTrue(
            any(
                item["name"] == "BeginPlay"
                for item in impact["result"]["affected"]
            )
        )

        callers = query_information_pool(
            self.pool,
            "callers",
            selector="Gameplay::ASampleActor::Helper",
        )
        self.assertEqual(
            [item["name"] for item in callers["result"]["callers"]],
            ["BeginPlay"],
        )

        path = query_information_pool(
            self.pool,
            "path",
            selector="Gameplay::ASampleActor::BeginPlay",
            target="Gameplay::ASampleActor::Helper",
        )
        self.assertEqual(path["status"], "selected")
        self.assertEqual(
            [item["name"] for item in path["result"]["path"]],
            ["BeginPlay", "Helper"],
        )

        cycles = query_information_pool(self.pool, "cycles")
        self.assertIn(cycles["status"], {"selected", "not_found"})

    def test_snapshot_diff_preserves_both_revisions(self) -> None:
        first = build_information_pool(self.fixture.project, self.pool)
        self.fixture.source_header.write_text(
            self.fixture.source_header.read_text(encoding="utf-8").replace(
                "void Utility();",
                "void Utility();\n        void AddedUtility();",
            ),
            encoding="utf-8",
        )
        self.fixture.source_cpp.write_text(
            self.fixture.source_cpp.read_text(encoding="utf-8").replace(
                "void ASampleActor::BeginPlay()",
                "void AddedUtility() {}\n\n        void ASampleActor::BeginPlay()",
            ),
            encoding="utf-8",
        )
        second_commit = self._commit("add utility")
        second = build_information_pool(self.fixture.project, self.pool)

        self.assertNotEqual(first["generation_id"], second["generation_id"])
        self.assertEqual(second["source_commit"], second_commit)
        self.assertEqual(len(list((self.pool / "snapshots").glob("*.sqlite3"))), 2)

        difference = query_information_pool(
            self.pool,
            "diff",
            against=first["generation_id"],
        )
        self.assertEqual(difference["status"], "selected")
        self.assertTrue(difference["result"]["added_nodes"])


if __name__ == "__main__":
    unittest.main()
