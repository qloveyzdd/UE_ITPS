from __future__ import annotations

from pathlib import Path

from tests.support import PUBLIC_CLIS, WorkspaceTestCase, run_cli


class EndToEndWorkflowTests(WorkspaceTestCase):
    def workflow_commands(self) -> dict[str, list[str]]:
        project = str(self.fixture.project_file)
        return {
            "ue_find_projects.py": [
                "--search-root",
                str(self.fixture.project_root),
            ],
            "ue_read_project_descriptor.py": ["--project", project],
            "ue_resolve_engine.py": ["--project", project],
            "ue_inspect_modules.py": ["--project", project],
            "ue_inspect_targets.py": ["--project", project],
            "ue_list_project_cxx_sources.py": ["--project", project],
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
                "SamplePlugin",
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
                "SampleGameTarget",
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

    def test_all_public_clis_form_explicit_navigation_workflow(self) -> None:
        commands = self.workflow_commands()
        self.assertEqual(set(commands), set(PUBLIC_CLIS))
        results = {}
        for script in PUBLIC_CLIS:
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
        self.assertEqual(
            {
                item["module"]
                for item in results["ue_list_project_cxx_sources.py"]["modules"]
            },
            {"SampleGame", "SamplePlugin"},
        )

        plugin_result = results["ue_resolve_plugins.py"]
        plugin_path = (
            Path(plugin_result["path_roots"]["project"])
            / plugin_result["items"][0]["descriptor"]
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
        self.assertEqual(results["ue_inspect_cxx_function.py"]["match_count"], 1)
        self.assertEqual(results["ue_inspect_cs_function.py"]["match_count"], 1)

    def test_repeated_scans_are_byte_deterministic(self) -> None:
        commands = self.workflow_commands()
        for script in (
            "ue_find_projects.py",
            "ue_inspect_modules.py",
            "ue_read_plugin_descriptor.py",
            "ue_inspect_module_entry.py",
            "ue_list_cxx_types.py",
            "ue_inspect_cxx_function.py",
        ):
            with self.subTest(script=script):
                first = run_cli(script, *commands[script])
                second = run_cli(script, *commands[script])
                self.assertEqual(first.returncode, 0)
                self.assertEqual(second.returncode, 0)
                self.assertEqual(first.stderr, second.stderr)
                self.assertEqual(first.stdout, second.stdout)


if __name__ == "__main__":
    import unittest

    unittest.main()
