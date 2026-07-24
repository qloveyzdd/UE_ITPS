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
from ue_project_tools.structure import classify_project_paths


CLI_SCRIPTS = (
    "ue_find_projects.py",
    "ue_read_project_descriptor.py",
    "ue_resolve_engine.py",
    "ue_inspect_modules.py",
    "ue_inspect_targets.py",
    "ue_resolve_plugins.py",
    "ue_classify_project_paths.py",
    "ue_read_plugin_descriptor.py",
    "ue_inspect_module_rules.py",
    "ue_inspect_target_rules.py",
    "ue_inspect_module_entry.py",
    "ue_list_source_includes.py",
    "ue_list_source_types.py",
    "ue_list_source_variables.py",
    "ue_list_source_functions.py",
    "ue_inspect_source_function.py",
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
                ("ue-itps.project-discovery.v1", discovery_result(root)),
                ("ue-itps.project-descriptor.v1", descriptor),
                (
                    "ue-itps.engine-resolution.v1",
                    resolve_engine(project, "", root / "MissingEngine"),
                ),
                ("ue-itps.project-modules.v1", inspect_modules(root, [], [])),
                ("ue-itps.project-targets.v1", inspect_targets(root)),
                (
                    "ue-itps.project-plugin-references.v1",
                    resolve_project_plugins(
                        project,
                        root,
                        None,
                        [],
                        [],
                        "scan",
                        "Win64",
                        "Editor",
                    ),
                ),
                (
                    "ue-itps.project-paths.v1",
                    classify_project_paths(
                        project,
                        {"FileVersion": 3, "Modules": [], "Plugins": []},
                    ),
                ),
            ]

            for expected_schema, result in results:
                with self.subTest(schema=expected_schema):
                    self.assertEqual(result["schema_version"], expected_schema)
                    self.assert_envelope(result)
            self.assertNotIn("build_version_sha256", results[2][1])

    def test_project_paths_report_directory_facts_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = self.write_project(root)
            (root / "Source").mkdir()
            (root / "Binaries").mkdir()
            (root / "Saved").mkdir()

            result = classify_project_paths(
                project,
                {"FileVersion": 3, "Modules": [], "Plugins": []},
            )

        project_directories = {
            item["project_relative_path"]: item
            for item in result["project_directories"]
        }
        build_and_ide_paths = {
            item["project_relative_path"]: item
            for item in result["build_and_ide_paths"]
        }
        local_state = {
            item["project_relative_path"]: item
            for item in result["cache_and_local_state_paths"]
        }
        self.assertEqual(result["schema_version"], "ue-itps.project-paths.v1")
        self.assertEqual(result["project_root"], root.as_posix())
        self.assertEqual(
            result["project_descriptor"]["project_relative_path"],
            "Fixture.uproject",
        )
        path_items = [
            result["project_descriptor"],
            *result["project_directories"],
            *result["build_and_ide_paths"],
            *result["cache_and_local_state_paths"],
            *result["unclassified_root_directories"],
        ]
        self.assertTrue(all("path" not in item for item in path_items))
        self.assertTrue(all("reason" not in item for item in path_items))
        self.assertEqual(project_directories["Source"]["role"], "source")
        self.assertEqual(project_directories["Source"]["actual_type"], "directory")
        self.assertEqual(build_and_ide_paths["Binaries"]["role"], "binaries")
        self.assertEqual(local_state["Saved"]["role"], "saved-state")
        self.assertEqual(result["validation"]["status"], "ok")

    def test_project_paths_fail_closed_for_unknown_or_invalid_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = self.write_project(root)
            (root / "Source").write_text("not a directory", encoding="utf-8")
            (root / "CustomDirectory").mkdir()

            result = classify_project_paths(
                project,
                {"FileVersion": 3, "Modules": [], "Plugins": []},
            )

        codes = {problem["code"] for problem in result["validation"]["problems"]}
        self.assertEqual(result["validation"]["status"], "error")
        self.assertIn("project-path-type-mismatch", codes)
        self.assertIn("unclassified-project-root-directory", codes)
        self.assertTrue(
            all(
                "path" not in problem and "project_relative_path" in problem
                for problem in result["validation"]["problems"]
            )
        )
        self.assertEqual(
            result["unclassified_root_directories"][0]["project_relative_path"],
            "CustomDirectory",
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

    def test_target_inventory_classifies_from_root_item_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_root = root / "Source"
            nested_root = source_root / "Nested"
            nested_root.mkdir(parents=True)
            (source_root / "Root.Target.cs").write_text("", encoding="utf-8")
            (nested_root / "Nested.Target.cs").write_text("", encoding="utf-8")

            result = inspect_targets(root)

        items = {item["name"]: item for item in result["items"]}
        self.assertEqual(result["schema_version"], "ue-itps.project-targets.v1")
        self.assertNotIn("count", result)
        self.assertEqual(result["classification"], "native-project")
        self.assertTrue(items["Root"]["is_root_target"])
        self.assertFalse(items["Nested"]["is_root_target"])
        self.assertNotIn("sha256", items["Root"])
        self.assertNotIn("sha256", items["Nested"])
        self.assertNotIn("native_project_evidence", result)
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "project-target-nested",
        )
        self.assertEqual(
            result["validation"]["problems"][0]["target_names"],
            ["Nested"],
        )
        self.assertEqual(
            result["validation"]["problems"][0]["message"],
            (
                "Target.cs files exist both directly under Source and in its "
                "subdirectories; review and move nested targets directly under "
                "Source when possible."
            ),
        )

    def test_nested_target_does_not_prove_native_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            nested_root = root / "Source" / "Nested"
            nested_root.mkdir(parents=True)
            (nested_root / "Nested.Target.cs").write_text("", encoding="utf-8")

            result = inspect_targets(root)

        self.assertEqual(
            result["classification"], "undetermined-no-native-target"
        )
        self.assertFalse(result["items"][0]["is_root_target"])
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "project-target-root-missing",
        )
        self.assertEqual(
            result["validation"]["problems"][0]["target_names"],
            ["Nested"],
        )
        self.assertEqual(
            result["validation"]["problems"][0]["message"],
            (
                "Target.cs files exist only in Source subdirectories; add or move "
                "at least one directly under Source for UE source-project "
                "detection."
            ),
        )

    def test_missing_target_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = inspect_targets(Path(temporary_directory))

        self.assertEqual(result["classification"], "undetermined-no-native-target")
        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "project-target-not-found",
        )
        self.assertEqual(
            result["validation"]["problems"][0]["message"],
            (
                "No project Target.cs files were found under Source; add at least "
                "one, preferably directly under Source."
            ),
        )

    def test_root_targets_without_nested_targets_are_ok(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_root = root / "Source"
            source_root.mkdir()
            (source_root / "Game.Target.cs").write_text("", encoding="utf-8")
            (source_root / "Editor.Target.cs").write_text("", encoding="utf-8")

            result = inspect_targets(root)

        self.assertEqual(result["classification"], "native-project")
        self.assertEqual(result["validation"]["status"], "ok")
        self.assertTrue(all(item["is_root_target"] for item in result["items"]))

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

    def test_path_classifier_rejects_a_missing_project_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            missing_project = Path(temporary_directory) / "Missing.uproject"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS_ROOT / "ue_classify_project_paths.py"),
                    "--project",
                    str(missing_project),
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("Missing.uproject", completed.stderr)

    def test_path_classifier_rejects_invalid_project_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "Fixture.uproject"
            project.write_text("this is intentionally not JSON", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS_ROOT / "ue_classify_project_paths.py"),
                    "--project",
                    str(project),
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("Expecting value", completed.stderr)

    def test_path_classifier_requires_source_for_declared_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "Fixture.uproject"
            descriptor = {
                "FileVersion": 3,
                "Modules": [{"Name": "Fixture", "Type": "Runtime"}],
                "Plugins": [],
            }
            project.write_text(json.dumps(descriptor), encoding="utf-8")

            result = classify_project_paths(project, descriptor)

        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "declared-modules-source-directory-missing",
        )
        self.assertEqual(
            result["validation"]["problems"][0]["project_relative_path"],
            "Source",
        )
        self.assertNotIn("path", result["validation"]["problems"][0])
        source_item = next(
            item for item in result["project_directories"] if item["role"] == "source"
        )
        self.assertEqual(source_item["actual_type"], "missing")
        self.assertNotIn("requiredness", source_item)
        self.assertNotIn("requiredness_evidence", source_item)

    def test_path_classifier_does_not_infer_source_from_absent_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = self.write_project(root)

            result = classify_project_paths(
                project,
                {"FileVersion": 3, "Modules": [], "Plugins": []},
            )

        self.assertEqual(result["validation"]["status"], "ok")

    def test_path_classifier_defers_source_when_additional_roots_are_declared(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "Fixture.uproject"
            descriptor = {
                "FileVersion": 3,
                "Modules": [{"Name": "Fixture", "Type": "Runtime"}],
                "Plugins": [],
                "AdditionalRootDirectories": ["AlternateSource"],
            }
            project.write_text(json.dumps(descriptor), encoding="utf-8")

            result = classify_project_paths(project, descriptor)

        codes = {problem["code"] for problem in result["validation"]["problems"]}
        self.assertNotIn("declared-modules-source-directory-missing", codes)
        self.assertEqual(result["validation"]["status"], "ok")

    def test_plugin_cli_resolves_engine_from_project_association(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project_root = root / "Project"
            project_root.mkdir()
            project = project_root / "Fixture.uproject"
            project.write_text(
                json.dumps(
                    {
                        "FileVersion": 3,
                        "EngineAssociation": "../EngineInstall",
                        "Plugins": [{"Name": "FixturePlugin", "Enabled": True}],
                    }
                ),
                encoding="utf-8",
            )
            engine_root = root / "EngineInstall"
            build_file = engine_root / "Engine" / "Build" / "Build.version"
            build_file.parent.mkdir(parents=True)
            build_file.write_text(
                json.dumps(
                    {"MajorVersion": 5, "MinorVersion": 6, "PatchVersion": 1}
                ),
                encoding="utf-8",
            )
            plugin_file = (
                engine_root
                / "Engine"
                / "Plugins"
                / "Runtime"
                / "FixturePlugin"
                / "FixturePlugin.uplugin"
            )
            plugin_file.parent.mkdir(parents=True)
            plugin_file.write_text(json.dumps({"FileVersion": 3}), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS_ROOT / "ue_resolve_plugins.py"),
                    "--project",
                    str(project),
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, "")
        result = json.loads(completed.stdout)
        self.assert_envelope(result)
        self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(result["resolved_count"], 1)
        self.assertEqual(result["path_roots"]["project"], project_root.as_posix())
        self.assertEqual(result["path_roots"]["engine"], engine_root.as_posix())
        self.assertEqual(result["project_descriptor"]["path"], "Fixture.uproject")
        self.assertNotIn("sha256", result["project_descriptor"])
        self.assertEqual(result["items"][0]["origin"], "engine")
        self.assertEqual(
            result["items"][0]["descriptor"],
            "Engine/Plugins/Runtime/FixturePlugin/FixturePlugin.uplugin",
        )
        self.assertNotIn("declared_enabled", result["items"][0])
        self.assertNotIn("configuration", result["profile"])

    def test_plugin_cli_reports_engine_resolution_failure_as_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "Fixture.uproject"
            project.write_text(
                json.dumps(
                    {
                        "FileVersion": 3,
                        "EngineAssociation": "../MissingEngine",
                        "Plugins": [],
                    }
                ),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TOOLS_ROOT / "ue_resolve_plugins.py"),
                    "--project",
                    str(project),
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
            result["validation"]["problems"][0]["code"], "engine-unresolved"
        )
        self.assertIsNone(result["path_roots"]["engine"])

    def test_plugin_cli_rejects_unknown_operation_and_has_no_configuration(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(TOOLS_ROOT / "ue_resolve_plugins.py"),
                "--project",
                "Fixture.uproject",
                "--operation",
                "typo",
            ],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        help_result = subprocess.run(
            [sys.executable, str(TOOLS_ROOT / "ue_resolve_plugins.py"), "--help"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("invalid choice", completed.stderr)
        self.assertNotIn("--configuration", help_result.stdout)

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

if __name__ == "__main__":
    unittest.main()
