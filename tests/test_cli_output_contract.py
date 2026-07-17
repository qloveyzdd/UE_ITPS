from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
sys.path.insert(0, str(TOOLS_ROOT))

from ue_project_tools.code_inventory import inspect_modules, inspect_targets
from ue_project_tools.common import result_document
from ue_project_tools.descriptor import descriptor_result
from ue_project_tools.discovery import discovery_result
from ue_project_tools.engine import resolve_engine
from ue_project_tools.plugins import resolve_project_plugins
from ue_project_tools.snapshot import build_snapshot
from ue_project_tools.structure import classify_project_paths


CLI_SCRIPTS = (
    "ue_find_projects.py",
    "ue_read_project_descriptor.py",
    "ue_resolve_engine.py",
    "ue_inspect_modules.py",
    "ue_inspect_targets.py",
    "ue_resolve_plugins.py",
    "ue_classify_project_paths.py",
    "inspect_uproject.py",
)


class CliOutputContractTests(unittest.TestCase):
    def assert_envelope(self, result: dict[str, object]) -> None:
        keys = list(result)
        self.assertEqual(keys[0], "schema_version")
        self.assertEqual(keys[-2:], ["validation", "limits"])
        self.assertEqual(
            list(result["validation"]),
            ["status", "problem_count", "problems"],
        )
        self.assertEqual(
            list(result["limits"]),
            ["responsibility", "boundaries"],
        )
        self.assertIsInstance(result["limits"]["responsibility"], str)
        self.assertTrue(result["limits"]["responsibility"])
        self.assertIsInstance(result["limits"]["boundaries"], list)
        self.assertTrue(result["limits"]["boundaries"])

    def write_project(self, root: Path) -> Path:
        project = root / "Fixture.uproject"
        project.write_text(
            json.dumps({"FileVersion": 3, "Modules": [], "Plugins": []}),
            encoding="utf-8",
        )
        return project

    def test_all_service_results_use_the_common_envelope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = self.write_project(root)
            _, descriptor = descriptor_result(project)
            results = [
                ("ue-itps.project-discovery.v2", discovery_result(root)),
                ("ue-itps.project-descriptor.v4", descriptor),
                (
                    "ue-itps.engine-resolution.v2",
                    resolve_engine(project, "", root / "MissingEngine"),
                ),
                ("ue-itps.project-modules.v4", inspect_modules(root, [], [])),
                ("ue-itps.project-targets.v2", inspect_targets(root)),
                (
                    "ue-itps.project-plugin-references.v3",
                    resolve_project_plugins(
                        project,
                        root,
                        None,
                        [],
                        [],
                        "scan",
                        "Win64",
                        "Editor",
                        "Development",
                    ),
                ),
                (
                    "ue-itps.project-paths.v2",
                    classify_project_paths(root, project),
                ),
                (
                    "ue-itps.uproject-structure.v5",
                    build_snapshot(
                        project=str(project),
                        engine_root=str(root / "MissingEngine"),
                    ),
                ),
            ]

            for expected_schema, result in results:
                with self.subTest(schema=expected_schema):
                    self.assertEqual(result["schema_version"], expected_schema)
                    self.assert_envelope(result)

            snapshot = results[-1][1]
            self.assertEqual(
                snapshot["component_schemas"],
                {
                    "descriptor": "ue-itps.project-descriptor.v4",
                    "engine": "ue-itps.engine-resolution.v2",
                    "modules": "ue-itps.project-modules.v4",
                    "targets": "ue-itps.project-targets.v2",
                    "plugins": "ue-itps.project-plugin-references.v3",
                    "paths": "ue-itps.project-paths.v2",
                },
            )

    def test_validation_status_reports_warnings(self) -> None:
        result = result_document(
            "fixture.v1",
            {"value": 1},
            [
                {
                    "severity": "warning",
                    "code": "fixture-warning",
                    "message": "Fixture warning",
                }
            ],
            responsibility="Exercise the result contract.",
            boundaries=["This is a test fixture."],
        )

        self.assertEqual(result["validation"]["status"], "warning")
        self.assertEqual(result["validation"]["problem_count"], 1)

    def test_discovery_failure_is_json_and_returns_one(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS_ROOT / "ue_find_projects.py"),
                    "--search-root",
                    temporary_directory,
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stderr, "")
        result = json.loads(completed.stdout)
        self.assert_envelope(result)
        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "project-discovery-not-found",
        )

    def test_all_cli_help_is_bilingual(self) -> None:
        for script in CLI_SCRIPTS:
            with self.subTest(script=script):
                completed = subprocess.run(
                    [sys.executable, str(TOOLS_ROOT / script), "--help"],
                    cwd=REPOSITORY_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                self.assertEqual(completed.returncode, 0)
                self.assertIn("用法 / usage", completed.stdout)
                self.assertIn("选项 / Options", completed.stdout)
                self.assertIn("显示帮助并退出", completed.stdout)
                self.assertIn("输出契约", completed.stdout)
                self.assertIn("Output contract", completed.stdout)
                self.assertIn("退出码", completed.stdout)
                self.assertIn("Exit codes", completed.stdout)

    def test_composer_stdout_matches_archived_json_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = self.write_project(root)
            json_output = root / "snapshot.json"
            markdown_output = root / "snapshot.md"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS_ROOT / "inspect_uproject.py"),
                    "--project",
                    str(project),
                    "--engine-root",
                    str(root / "MissingEngine"),
                    "--json-out",
                    str(json_output),
                    "--markdown-out",
                    str(markdown_output),
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

            stdout_result = json.loads(completed.stdout)
            archived_result = json.loads(json_output.read_text(encoding="utf-8"))
            markdown = markdown_output.read_text(encoding="utf-8")

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(stdout_result, archived_result)
        self.assert_envelope(stdout_result)
        self.assertIn("职责：", markdown)


if __name__ == "__main__":
    unittest.main()
