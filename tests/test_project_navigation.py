from __future__ import annotations

from pathlib import Path

from tests.support import CliTestCase, write_json, write_text


class ProjectNavigationTests(CliTestCase):
    def test_discovery_selects_the_only_project(self) -> None:
        result = self.cli(
            "ue_find_projects.py",
            "--search-root",
            str(self.fixture.project_root),
        )
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["validation"]["status"], "ok")

    def test_discovery_reports_no_project_as_domain_error(self) -> None:
        empty = self.fixture.root / "Empty"
        empty.mkdir()
        result = self.cli(
            "ue_find_projects.py",
            "--search-root",
            str(empty),
            expected_code=1,
        )
        self.assertEqual(result["status"], "not-found")
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["validation"]["status"], "error")

    def test_discovery_refuses_ambiguous_projects(self) -> None:
        write_json(
            self.fixture.project_root / "Second.uproject",
            {"FileVersion": 3},
        )
        result = self.cli(
            "ue_find_projects.py",
            "--search-root",
            str(self.fixture.project_root),
            expected_code=1,
        )
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "project-discovery-ambiguous",
        )

    def test_discovery_skips_generated_directories(self) -> None:
        write_json(
            self.fixture.project_root
            / "Intermediate"
            / "Hidden.uproject",
            {"FileVersion": 3},
        )
        result = self.cli(
            "ue_find_projects.py",
            "--search-root",
            str(self.fixture.project_root),
        )
        self.assertEqual(result["candidate_count"], 1)

    def test_project_descriptor_projects_explicit_navigation_facts(self) -> None:
        result = self.cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(self.fixture.project),
        )
        self.assertEqual(result["declared_modules"], ["SampleGame"])
        self.assertEqual(
            result["plugin_declarations"]["enabled"],
            ["SamplePlugin"],
        )
        self.assertEqual(
            result["plugin_declarations"]["disabled"],
            ["DisabledPlugin"],
        )
        self.assertEqual(
            result["unmodeled_top_level_fields"],
            {"CustomFixtureField": {"kept": True}},
        )

    def test_project_descriptor_preserves_extended_plugin_declaration(self) -> None:
        descriptor = {
            "FileVersion": 3,
            "Plugins": [
                {
                    "Name": "ConditionalPlugin",
                    "Enabled": True,
                    "TargetAllowList": ["Editor"],
                }
            ],
        }
        project = write_json(
            self.fixture.root / "Extended.uproject",
            descriptor,
        )
        result = self.cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(project),
        )
        extended = result["plugin_declarations"]["extended"]
        self.assertEqual(len(extended), 1)
        self.assertEqual(extended[0]["name"], "ConditionalPlugin")
        self.assertEqual(extended[0]["additional_fields"], ["TargetAllowList"])

    def test_engine_resolution_reads_build_version(self) -> None:
        result = self.cli(
            "ue_resolve_engine.py",
            "--project",
            str(self.fixture.project),
        )
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["version"], "5.6.1")
        self.assertEqual(result["build"]["Changelist"], 12345)
        self.assertEqual(result["validation"]["status"], "ok")

    def test_engine_resolution_honors_explicit_override(self) -> None:
        alternate = self.fixture.root / "AlternateEngine"
        write_json(
            alternate / "Engine" / "Build" / "Build.version",
            {
                "MajorVersion": 5,
                "MinorVersion": 7,
                "PatchVersion": 0,
            },
        )
        result = self.cli(
            "ue_resolve_engine.py",
            "--project",
            str(self.fixture.project),
            "--engine-root",
            str(alternate),
        )
        self.assertEqual(result["version"], "5.7.0")

    def test_module_inventory_reconciles_rules_and_entrypoint(self) -> None:
        result = self.cli(
            "ue_inspect_modules.py",
            "--project",
            str(self.fixture.project),
        )
        self.assertEqual(result["reconciled_module_count"], 1)
        item = result["items"][0]
        self.assertEqual(item["name"], "SampleGame")
        self.assertEqual(item["build_rules"]["status"], "resolved")
        self.assertGreaterEqual(
            len(item["actual"]["module_entrypoint_candidates"]),
            1,
        )

    def test_target_inventory_finds_game_and_editor_targets(self) -> None:
        result = self.cli(
            "ue_inspect_targets.py",
            "--project",
            str(self.fixture.project),
        )
        self.assertEqual(
            {item["name"] for item in result["items"]},
            {"SampleGame", "SampleGameEditor"},
        )
        self.assertEqual(result["classification"], "native-project")

    def test_project_source_inventory_groups_project_and_plugin_modules(self) -> None:
        result = self.cli(
            "ue_list_project_cxx_sources.py",
            "--project",
            str(self.fixture.project),
        )
        self.assertEqual(result["module_count"], 2)
        by_name = {item["module"]: item for item in result["modules"]}
        self.assertEqual(set(by_name), {"SampleGame", "SamplePlugin"})
        self.assertIn(
            "Source/SampleGame/Public/SampleActor.h",
            by_name["SampleGame"]["headers"]["public"],
        )
        self.assertEqual(by_name["SamplePlugin"]["plugin"], "SamplePlugin")

    def test_plugin_resolution_keeps_enabled_and_disabled_declarations(self) -> None:
        result = self.cli(
            "ue_resolve_plugins.py",
            "--project",
            str(self.fixture.project),
        )
        self.assertEqual(result["count"], 2)
        by_name = {item["name"]: item for item in result["items"]}
        self.assertTrue(by_name["SamplePlugin"]["declared_enabled"])
        self.assertEqual(by_name["SamplePlugin"]["origin"], "project")
        self.assertFalse(by_name["DisabledPlugin"]["declared_enabled"])
        self.assertIsNone(by_name["DisabledPlugin"]["descriptor"])

    def test_plugin_filter_is_case_insensitive(self) -> None:
        result = self.cli(
            "ue_resolve_plugins.py",
            "--project",
            str(self.fixture.project),
            "--plugin-name",
            "sampleplugin",
        )
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["name"], "SamplePlugin")

    def test_path_classification_reports_roles_without_deletion_claims(self) -> None:
        result = self.cli(
            "ue_classify_project_paths.py",
            "--project",
            str(self.fixture.project),
        )
        path_items = [
            *result["project_directories"],
            *result["build_and_ide_paths"],
            *result["cache_and_local_state_paths"],
        ]
        by_path = {
            item["project_relative_path"]: item
            for item in path_items
        }
        self.assertEqual(by_path["Content"]["role"], "content")
        self.assertEqual(by_path["Source"]["actual_type"], "directory")
        self.assertEqual(
            result["unclassified_root_directories"][0]["project_relative_path"],
            "Reports",
        )
        self.assertTrue(
            any("deletion" in boundary.lower() for boundary in result["limits"]["boundaries"])
        )
