from __future__ import annotations

from pathlib import Path

from tests.fixture import FixtureTestCase, write_json, write_text


class ProjectLayerTests(FixtureTestCase):
    def test_discovery_selects_the_only_project(self) -> None:
        result = self.cli(
            "ue_find_projects.py",
            "--search-root",
            str(self.fixture.project_root),
        )
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(
            Path(result["candidates"][0]).resolve(),
            self.fixture.project_file.resolve(),
        )

    def test_discovery_refuses_to_choose_between_projects(self) -> None:
        write_json(
            self.fixture.workspace / "Other" / "Other.uproject",
            {"FileVersion": 3},
        )
        result = self.cli(
            "ue_find_projects.py",
            "--search-root",
            str(self.fixture.workspace),
            expected_code=1,
        )
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "project-discovery-ambiguous",
        )

    def test_project_descriptor_compacts_declared_navigation_facts(self) -> None:
        result = self.cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(self.fixture.project_file),
        )
        self.assertEqual(result["declared_modules"], ["CurrentGame"])
        self.assertEqual(
            result["plugin_declarations"]["enabled"],
            ["CurrentPlugin"],
        )
        self.assertEqual(
            result["plugin_declarations"]["disabled"],
            ["DisabledPlugin"],
        )
        self.assertEqual(
            result["unmodeled_top_level_fields"],
            {"CustomField": {"preserved": True}},
        )

    def test_engine_resolution_reads_the_actual_build_version(self) -> None:
        result = self.cli(
            "ue_resolve_engine.py",
            "--project",
            str(self.fixture.project_file),
        )
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["version"], "5.6.1")
        self.assertEqual(
            Path(result["engine_root"]).resolve(),
            self.fixture.workspace.resolve(),
        )

    def test_module_inventory_reconciles_rules_and_registration(self) -> None:
        result = self.cli(
            "ue_inspect_modules.py",
            "--project",
            str(self.fixture.project_file),
        )
        self.assertEqual(result["reconciled_module_count"], 1)
        module = result["items"][0]
        self.assertEqual(module["name"], "CurrentGame")
        self.assertEqual(
            module["actual"]["module_entrypoint_candidates"][0]["macro"],
            "IMPLEMENT_PRIMARY_GAME_MODULE",
        )
        self.assertEqual(
            Path(module["build_rules"]["candidates"][0]["path"]).resolve(),
            self.fixture.game_rules.resolve(),
        )

    def test_target_inventory_classifies_a_native_project(self) -> None:
        result = self.cli(
            "ue_inspect_targets.py",
            "--project",
            str(self.fixture.project_file),
        )
        self.assertEqual(result["classification"], "native-project")
        self.assertEqual([item["name"] for item in result["items"]], ["CurrentGame"])
        self.assertEqual(
            Path(result["items"][0]["path"]).resolve(),
            self.fixture.target_file.resolve(),
        )

    def test_project_cxx_sources_groups_manual_files_and_excludes_generated_and_engine(
        self,
    ) -> None:
        write_text(
            self.fixture.project_root / "Source" / "CurrentGame" / "Loose.hpp",
            "#pragma once",
        )
        write_text(
            self.fixture.project_root
            / "Source"
            / "CurrentGame"
            / "Private"
            / "Transient.gen.cpp",
            "void GeneratedByTool() {}",
        )
        write_text(
            self.fixture.plugin_root
            / "Source"
            / "CurrentPlugin"
            / "Public"
            / "CurrentPluginApi.hpp",
            "#pragma once",
        )
        write_text(
            self.fixture.engine_root
            / "Engine"
            / "Source"
            / "Runtime"
            / "Core"
            / "Private"
            / "Core.cpp",
            "void EngineSource() {}",
        )

        result = self.cli(
            "ue_list_project_cxx_sources.py",
            "--project",
            str(self.fixture.project_file),
        )

        self.assertEqual(result["module_count"], 2)
        self.assertEqual(result["file_count"], 6)
        modules = {item["module"]: item for item in result["modules"]}
        game = modules["CurrentGame"]
        self.assertIsNone(game["plugin"])
        self.assertIsNone(game["plugin_descriptor"])
        self.assertEqual(
            game["headers"]["public"],
            ["Source/CurrentGame/Public/CurrentFeature.h"],
        )
        self.assertEqual(
            game["headers"]["unclassified"],
            ["Source/CurrentGame/Loose.hpp"],
        )
        self.assertEqual(
            game["cpp"]["private"],
            [
                "Source/CurrentGame/Private/CurrentFeature.cpp",
                "Source/CurrentGame/Private/CurrentGameModule.cpp",
            ],
        )

        plugin = modules["CurrentPlugin"]
        self.assertEqual(plugin["plugin"], "CurrentPlugin")
        self.assertEqual(
            plugin["plugin_descriptor"],
            "Plugins/CurrentPlugin/CurrentPlugin.uplugin",
        )
        self.assertEqual(
            plugin["headers"]["public"],
            ["Plugins/CurrentPlugin/Source/CurrentPlugin/Public/CurrentPluginApi.hpp"],
        )
        all_paths = [
            path
            for item in result["modules"]
            for kind in ("headers", "cpp")
            for paths in item[kind].values()
            for path in paths
        ]
        self.assertFalse(any(".gen." in path for path in all_paths))
        self.assertFalse(any(path.startswith("Engine/") for path in all_paths))

    def test_plugin_resolution_preserves_profile_and_disabled_items(self) -> None:
        result = self.cli(
            "ue_resolve_plugins.py",
            "--project",
            str(self.fixture.project_file),
            "--engine-root",
            str(self.fixture.engine_root),
            "--operation",
            "scan",
            "--platform",
            "Win64",
            "--target-type",
            "Editor",
        )
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["declared_enabled_count"], 1)
        self.assertEqual(result["declared_disabled_count"], 1)
        self.assertEqual(
            result["profile"],
            {
                "operation": "scan",
                "platform": "Win64",
                "target_type": "Editor",
            },
        )
        enabled = next(
            item for item in result["items"] if item["name"] == "CurrentPlugin"
        )
        self.assertEqual(enabled["origin"], "project")
        self.assertEqual(
            enabled["descriptor"],
            "Plugins/CurrentPlugin/CurrentPlugin.uplugin",
        )

    def test_plugin_resolution_name_filter_is_case_insensitive(self) -> None:
        result = self.cli(
            "ue_resolve_plugins.py",
            "--project",
            str(self.fixture.project_file),
            "--engine-root",
            str(self.fixture.engine_root),
            "--plugin-name",
            "disabledplugin",
        )
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["name"], "DisabledPlugin")
        self.assertEqual(result["items"][0]["descriptor_pointer"], "/Plugins/1")

    def test_path_classification_reports_state_not_deletion_safety(self) -> None:
        result = self.cli(
            "ue_classify_project_paths.py",
            "--project",
            str(self.fixture.project_file),
        )
        source = next(
            item for item in result["project_directories"] if item["role"] == "source"
        )
        self.assertEqual(source["actual_type"], "directory")
        self.assertNotIn("deletion_safe", source)
        self.assertTrue(
            any(
                "deletion safety" in boundary
                for boundary in result["limits"]["boundaries"]
            )
        )
