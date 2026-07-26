from __future__ import annotations

import json
from pathlib import Path
import tempfile

from tests.support import (
    CLI_SCRIPTS,
    EnvelopeAssertions,
    create_fixture,
    run_cli,
)


class NavigationFlowTests(EnvelopeAssertions):
    def test_all_fifteen_clis_form_one_explicit_navigation_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            project = str(fixture.project_file)
            engine = str(fixture.engine_root)

            commands = {
                "ue_find_projects.py": [
                    "--search-root",
                    str(fixture.workspace),
                ],
                "ue_read_project_descriptor.py": ["--project", project],
                "ue_resolve_engine.py": ["--project", project],
                "ue_inspect_modules.py": ["--project", project],
                "ue_inspect_targets.py": ["--project", project],
                "ue_resolve_plugins.py": [
                    "--project",
                    project,
                    "--engine-root",
                    engine,
                    "--operation",
                    "scan",
                    "--platform",
                    "Win64",
                    "--target-type",
                    "Editor",
                    "--plugin-name",
                    "FixturePlugin",
                ],
                "ue_classify_project_paths.py": ["--project", project],
                "ue_read_plugin_descriptor.py": [
                    "--plugin",
                    str(fixture.plugin_file),
                ],
                "ue_inspect_module_rules.py": [
                    "--rules",
                    str(fixture.plugin_rules),
                ],
                "ue_inspect_target_rules.py": [
                    "--target",
                    str(fixture.target_file),
                ],
                "ue_inspect_cs_function.py": [
                    "--source",
                    str(fixture.target_file),
                    "--function",
                    "FixtureGameTarget",
                ],
                "ue_inspect_module_entry.py": [
                    "--rules",
                    str(fixture.plugin_rules),
                ],
                "ue_list_source_includes.py": [
                    "--source",
                    str(fixture.source_file),
                ],
                "ue_list_source_types.py": [
                    "--source",
                    str(fixture.source_file),
                ],
                "ue_inspect_source_function.py": [
                    "--source",
                    str(fixture.source_file),
                    "--function",
                    "Execute",
                ],
            }

            results = {}
            for script in CLI_SCRIPTS:
                with self.subTest(script=script):
                    completed = run_cli(script, *commands[script])
                    self.assertEqual(
                        completed.returncode,
                        0,
                        msg=completed.stderr or completed.stdout,
                    )
                    self.assertEqual(completed.stderr, "")
                    result = json.loads(completed.stdout)
                    self.assert_envelope(result)
                    self.assertNotEqual(result["validation"]["status"], "error")
                    results[script] = result

        discovered = Path(
            results["ue_find_projects.py"]["candidates"][0]
        ).resolve()
        self.assertEqual(discovered, fixture.project_file.resolve())

        module_rules = Path(
            results["ue_inspect_modules.py"]["items"][0]["build_rules"][
                "candidates"
            ][0]["path"]
        ).resolve()
        self.assertEqual(module_rules, fixture.game_rules.resolve())

        target_path = Path(
            results["ue_inspect_targets.py"]["items"][0]["path"]
        ).resolve()
        self.assertEqual(target_path, fixture.target_file.resolve())

        plugin_result = results["ue_resolve_plugins.py"]
        self.assertEqual(plugin_result["count"], 1)
        plugin_item = next(
            item
            for item in plugin_result["items"]
            if item["name"] == "FixturePlugin"
        )
        plugin_path = (
            Path(plugin_result["path_roots"]["project"])
            / plugin_item["descriptor"]
        ).resolve()
        self.assertEqual(plugin_path, fixture.plugin_file.resolve())

        plugin_rules = Path(
            results["ue_read_plugin_descriptor.py"]["modules"][0][
                "build_rules"
            ]["candidates"][0]["path"]
        ).resolve()
        self.assertEqual(plugin_rules, fixture.plugin_rules.resolve())

        entry = results["ue_inspect_module_entry.py"]
        entry_path = (
            Path(entry["module"]["root"]) / entry["registration"]["evidence"]["path"]
        ).resolve()
        self.assertEqual(entry_path, fixture.plugin_entry.resolve())

        type_functions = {
            member["name"]
            for item in results["ue_list_source_types.py"]["types"]
            for member in item["member_details"]["functions"]
        }
        self.assertIn("Execute", type_functions)
        self.assertEqual(
            results["ue_inspect_source_function.py"]["selection"]["name"],
            "Execute",
        )
        self.assertEqual(
            results["ue_inspect_source_function.py"]["match_count"],
            1,
        )
        self.assertEqual(
            results["ue_inspect_cs_function.py"]["selection"]["name"],
            "FixtureGameTarget",
        )
        self.assertEqual(
            results["ue_inspect_cs_function.py"]["match_count"],
            1,
        )
