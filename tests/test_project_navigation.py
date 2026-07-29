from __future__ import annotations

from pathlib import Path

from tests.support import WorkspaceTestCase, write_json, write_text


class ProjectNavigationTests(WorkspaceTestCase):
    def test_discovery_selects_one_project(self) -> None:
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

    def test_discovery_reports_no_project(self) -> None:
        empty = self.fixture.workspace / "Empty"
        empty.mkdir()
        result = self.cli(
            "ue_find_projects.py",
            "--search-root",
            str(empty),
            expected_code=1,
        )
        self.assertEqual(result["status"], "not-found")
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "project-discovery-not-found",
        )

    def test_discovery_refuses_ambiguous_projects(self) -> None:
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
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "project-discovery-ambiguous",
        )

    def test_discovery_skips_generated_directories(self) -> None:
        for name in ("Binaries", "Intermediate", "Saved", "DerivedDataCache"):
            write_json(
                self.fixture.project_root / name / f"{name}.uproject",
                {"FileVersion": 3},
            )
        result = self.cli(
            "ue_find_projects.py",
            "--search-root",
            str(self.fixture.project_root),
        )
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(Path(result["candidates"][0]).name, "SampleGame.uproject")

    def test_project_descriptor_projects_navigation_fields(self) -> None:
        result = self.cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(self.fixture.project_file),
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
            {"CustomField": {"preserved": True}},
        )

    def test_project_descriptor_preserves_extended_plugin_declaration(self) -> None:
        descriptor = {
            "FileVersion": 3,
            "Plugins": [
                {
                    "Name": "PlatformPlugin",
                    "Enabled": True,
                    "PlatformAllowList": ["Win64"],
                }
            ],
        }
        write_json(self.fixture.project_file, descriptor)
        result = self.cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(self.fixture.project_file),
        )
        extended = result["plugin_declarations"]["extended"]
        self.assertEqual(len(extended), 1)
        self.assertEqual(extended[0]["name"], "PlatformPlugin")
        self.assertEqual(extended[0]["descriptor_pointer"], "/Plugins/0")

    def test_project_descriptor_rejects_duplicate_json_fields(self) -> None:
        self.fixture.project_file.write_text(
            '{"FileVersion": 3, "FileVersion": 4}',
            encoding="utf-8",
        )
        result = self.cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(self.fixture.project_file),
            expected_code=2,
        )
        self.assert_request_failure(result, kind="input")

    def test_engine_resolution_reads_build_version(self) -> None:
        result = self.cli(
            "ue_resolve_engine.py",
            "--project",
            str(self.fixture.project_file),
        )
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["version"], "5.6.1")
        self.assertEqual(
            Path(result["engine_root"]).resolve(),
            self.fixture.engine_root.resolve(),
        )

    def test_module_inventory_reconciles_rules_and_entrypoint(self) -> None:
        result = self.cli(
            "ue_inspect_modules.py",
            "--project",
            str(self.fixture.project_file),
        )
        self.assertEqual(result["reconciled_module_count"], 1)
        module = result["items"][0]
        self.assertEqual(module["name"], "SampleGame")
        self.assertEqual(
            module["actual"]["module_entrypoint_candidates"][0]["macro"],
            "IMPLEMENT_PRIMARY_GAME_MODULE",
        )
        self.assertEqual(
            Path(module["build_rules"]["candidates"][0]["path"]).resolve(),
            self.fixture.game_rules.resolve(),
        )

    def test_target_inventory_finds_game_and_editor_targets(self) -> None:
        result = self.cli(
            "ue_inspect_targets.py",
            "--project",
            str(self.fixture.project_file),
        )
        self.assertEqual(result["classification"], "native-project")
        self.assertEqual(
            [item["name"] for item in result["items"]],
            ["SampleGame", "SampleGameEditor"],
        )
        self.assertTrue(all(item["is_root_target"] for item in result["items"]))

    def test_project_source_inventory_groups_project_and_plugin_modules(self) -> None:
        write_text(
            self.fixture.project_root / "Source" / "SampleGame" / "Loose.hpp",
            "#pragma once",
        )
        write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Private"
            / "Ignored.gen.cpp",
            "void Generated() {}",
        )
        write_text(
            self.fixture.plugin_root
            / "Source"
            / "SamplePlugin"
            / "Public"
            / "SamplePluginApi.hpp",
            "#pragma once",
        )
        result = self.cli(
            "ue_list_project_cxx_sources.py",
            "--project",
            str(self.fixture.project_file),
        )
        self.assertEqual(result["module_count"], 2)
        self.assertEqual(result["file_count"], 6)
        modules = {item["module"]: item for item in result["modules"]}
        self.assertIsNone(modules["SampleGame"]["plugin"])
        self.assertEqual(
            modules["SampleGame"]["headers"]["unclassified"],
            ["Source/SampleGame/Loose.hpp"],
        )
        self.assertEqual(modules["SamplePlugin"]["plugin"], "SamplePlugin")
        self.assertEqual(
            modules["SamplePlugin"]["plugin_descriptor"],
            "Plugins/SamplePlugin/SamplePlugin.uplugin",
        )
        paths = [
            path
            for module in result["modules"]
            for category in ("headers", "cpp")
            for group in module[category].values()
            for path in group
        ]
        self.assertFalse(any(".gen." in path for path in paths))
        self.assertFalse(any(path.startswith("Engine/") for path in paths))

    def test_plugin_resolution_preserves_profile_and_disabled_items(self) -> None:
        result = self.cli(
            "ue_resolve_plugins.py",
            "--project",
            str(self.fixture.project_file),
            "--engine-root",
            str(self.fixture.engine_root),
            "--operation",
            "build_editor",
            "--platform",
            "Linux",
            "--target-type",
            "Editor",
        )
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["declared_enabled_count"], 1)
        self.assertEqual(result["declared_disabled_count"], 1)
        self.assertEqual(
            result["profile"],
            {
                "operation": "build_editor",
                "platform": "Linux",
                "target_type": "Editor",
            },
        )
        plugin = next(item for item in result["items"] if item["name"] == "SamplePlugin")
        self.assertEqual(plugin["origin"], "project")
        self.assertEqual(
            plugin["descriptor"],
            "Plugins/SamplePlugin/SamplePlugin.uplugin",
        )

    def test_plugin_name_filter_is_case_insensitive(self) -> None:
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

    def test_path_classification_reports_state_without_deletion_claim(self) -> None:
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
            any("deletion safety" in text for text in result["limits"]["boundaries"])
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
