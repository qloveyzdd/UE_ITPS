from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tests.support import CliTestCase, PUBLIC_CLIS, run_cli, validator_for


class EndToEndWorkflowTests(CliTestCase):
    def success_calls(self) -> dict[str, tuple[str, ...]]:
        return {
            "ue_list_tools.py": (),
            "ue_find_projects.py": (
                "--search-root",
                str(self.fixture.project_root),
            ),
            "ue_find_build_descriptor.py": (
                "--project",
                str(self.fixture.project),
                "--modulename",
                "SampleGame",
            ),
            "ue_read_project_descriptor.py": (
                "--project",
                str(self.fixture.project),
                "--engine-build-version",
                str(
                    self.fixture.engine_root
                    / "Engine"
                    / "Build"
                    / "Build.version"
                ),
            ),
            "ue_resolve_engine.py": (
                "--project",
                str(self.fixture.project),
            ),
            "ue_inspect_modules.py": (
                "--project",
                str(self.fixture.project),
            ),
            "ue_inspect_targets.py": (
                "--project",
                str(self.fixture.project),
            ),
            "ue_list_project_cxx_sources.py": (
                "--project",
                str(self.fixture.project),
            ),
            "ue_list_module_cxx_sources.py": (
                "--rules",
                str(self.fixture.module_rules),
            ),
            "ue_resolve_plugins.py": (
                "--project",
                str(self.fixture.project),
            ),
            "ue_classify_project_paths.py": (
                "--project",
                str(self.fixture.project),
            ),
            "ue_read_plugin_descriptor.py": (
                "--plugin",
                str(self.fixture.plugin),
            ),
            "ue_inspect_module_rules.py": (
                "--rules",
                str(self.fixture.module_rules),
            ),
            "ue_inspect_target_rules.py": (
                "--target",
                str(self.fixture.game_target),
            ),
            "ue_inspect_cs_function.py": (
                "--source",
                str(self.fixture.game_target),
                "--function",
                "SampleGameTarget",
            ),
            "ue_inspect_module_entry.py": (
                "--rules",
                str(self.fixture.plugin_rules),
            ),
            "ue_list_cxx_includes.py": (
                "--source",
                str(self.fixture.source_cpp),
            ),
            "ue_list_cxx_types.py": (
                "--source",
                str(self.fixture.source_cpp),
            ),
            "ue_inspect_cxx_function.py": (
                "--source",
                str(self.fixture.source_cpp),
                "--function",
                "BeginPlay",
            ),
            "ue_analyze_cxx_dependencies.py": (
                "--project",
                str(self.fixture.project),
            ),
            "ue_query_cxx_hierarchy.py": (
                "--project",
                str(self.fixture.project),
                "--class",
                "ASampleActor",
            ),
            "ue_analyze_cxx_impact.py": (
                "--project",
                str(self.fixture.project),
                "--symbol",
                "ASampleActor",
            ),
            "ue_trace_cxx_function_flow.py": (
                "--source",
                str(self.fixture.source_cpp),
                "--function",
                "BeginPlay",
            ),
        }

    def test_all_public_clis_form_one_explicit_navigation_workflow(self) -> None:
        calls = self.success_calls()
        self.assertEqual(set(calls), set(PUBLIC_CLIS))
        results: dict[str, dict] = {}
        for script, arguments in calls.items():
            with self.subTest(script=script):
                results[script] = self.cli(script, *arguments)

        descriptor = results["ue_read_project_descriptor.py"]
        self.assertEqual(descriptor["declared_modules"], ["SampleGame"])
        plugin_path = results["ue_resolve_plugins.py"]["items"][0]["descriptor"]
        self.assertEqual(plugin_path, "Plugins/SamplePlugin/SamplePlugin.uplugin")
        types = results["ue_list_cxx_types.py"]
        self.assertEqual(types["classes"][0]["member_anchors"][0]["name"], "BeginPlay")
        function = results["ue_inspect_cxx_function.py"]
        self.assertEqual(function["selection"]["name"], "BeginPlay")

    def test_repeated_scans_are_byte_deterministic(self) -> None:
        for script, arguments in self.success_calls().items():
            with self.subTest(script=script):
                first = run_cli(script, *arguments)
                second = run_cli(script, *arguments)
                self.assertEqual(first.returncode, second.returncode)
                self.assertEqual(first.stdout, second.stdout)
                self.assertEqual(first.stderr, second.stderr)
                result = json.loads(first.stdout)
                self.assertEqual(
                    list(validator_for(script).iter_errors(result)),
                    [],
                )

    def test_complete_workflow_does_not_modify_fixture_files(self) -> None:
        before = self.file_fingerprints(self.fixture.root)
        for script, arguments in self.success_calls().items():
            completed = run_cli(script, *arguments)
            self.assertEqual(
                completed.returncode,
                0,
                msg=completed.stderr or completed.stdout,
            )
        after = self.file_fingerprints(self.fixture.root)
        self.assertEqual(after, before)

    @staticmethod
    def file_fingerprints(root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }
