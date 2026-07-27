from __future__ import annotations

from pathlib import Path

from tests.fixture import CLI_SCHEMAS, FixtureTestCase


class NavigationWorkflowTests(FixtureTestCase):
    def test_all_public_clis_form_one_explicit_navigation_workflow(self) -> None:
        project = str(self.fixture.project_file)
        commands = {
            "ue_find_projects.py": [
                "--search-root",
                str(self.fixture.project_root),
            ],
            "ue_read_project_descriptor.py": ["--project", project],
            "ue_resolve_engine.py": ["--project", project],
            "ue_inspect_modules.py": ["--project", project],
            "ue_inspect_targets.py": ["--project", project],
            "ue_resolve_plugins.py": [
                "--project",
                project,
                "--engine-root",
                str(self.fixture.engine_root),
                "--operation",
                "scan",
                "--platform",
                "Win64",
                "--target-type",
                "Editor",
                "--plugin-name",
                "CurrentPlugin",
            ],
            "ue_classify_project_paths.py": ["--project", project],
            "ue_read_plugin_descriptor.py": [
                "--plugin",
                str(self.fixture.plugin_file),
            ],
            "ue_inspect_module_rules.py": [
                "--rules",
                str(self.fixture.plugin_rules),
            ],
            "ue_inspect_target_rules.py": [
                "--target",
                str(self.fixture.target_file),
            ],
            "ue_inspect_cs_function.py": [
                "--source",
                str(self.fixture.target_file),
                "--function",
                "CurrentGameTarget",
            ],
            "ue_inspect_module_entry.py": [
                "--rules",
                str(self.fixture.plugin_rules),
            ],
            "ue_list_cxx_includes.py": [
                "--source",
                str(self.fixture.source_file),
            ],
            "ue_list_cxx_types.py": [
                "--source",
                str(self.fixture.source_file),
            ],
            "ue_inspect_cxx_function.py": [
                "--source",
                str(self.fixture.source_file),
                "--function",
                "Execute",
            ],
        }
        results = {}
        for script in CLI_SCHEMAS:
            with self.subTest(script=script):
                result = self.cli(script, *commands[script])
                self.assertNotEqual(result["validation"]["status"], "error")
                results[script] = result

        discovered = Path(results["ue_find_projects.py"]["candidates"][0]).resolve()
        self.assertEqual(discovered, self.fixture.project_file.resolve())
        module_rules = Path(
            results["ue_inspect_modules.py"]["items"][0]["build_rules"]["candidates"][
                0
            ]["path"]
        ).resolve()
        self.assertEqual(module_rules, self.fixture.game_rules.resolve())
        target = Path(results["ue_inspect_targets.py"]["items"][0]["path"]).resolve()
        self.assertEqual(target, self.fixture.target_file.resolve())

        plugin_result = results["ue_resolve_plugins.py"]
        plugin = plugin_result["items"][0]
        plugin_path = (
            Path(plugin_result["path_roots"]["project"]) / plugin["descriptor"]
        ).resolve()
        self.assertEqual(plugin_path, self.fixture.plugin_file.resolve())

        plugin_rules = Path(
            results["ue_read_plugin_descriptor.py"]["modules"][0]["build_rules"][
                "candidates"
            ][0]["path"]
        ).resolve()
        self.assertEqual(plugin_rules, self.fixture.plugin_rules.resolve())

        entry = results["ue_inspect_module_entry.py"]
        entry_path = (
            Path(entry["module"]["root"]) / entry["registration"]["evidence"]["path"]
        ).resolve()
        self.assertEqual(entry_path, self.fixture.plugin_entry.resolve())

        cxx_functions = {
            member["name"]
            for item in results["ue_list_cxx_types.py"]["types"]
            for member in item.get("member_details", {}).get("functions", [])
        }
        self.assertIn("Execute", cxx_functions)
        self.assertEqual(
            results["ue_inspect_cxx_function.py"]["match_count"],
            1,
        )
        self.assertEqual(
            results["ue_inspect_cs_function.py"]["match_count"],
            1,
        )
