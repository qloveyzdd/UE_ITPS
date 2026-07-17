from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


TOOLS_ROOT = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_ROOT))

from ue_project_tools.code_inventory import inspect_modules
from ue_project_tools.common import read_json
from ue_project_tools.descriptor import (
    descriptor_result,
    directory_finding_problems,
    resolve_internal_directories,
)
from ue_project_tools.plugins import resolve_project_plugins


class ProjectDescriptorContractTests(unittest.TestCase):
    def write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_json_reader_rejects_duplicate_keys_and_nonstandard_constants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "Fixture.uproject"
            cases = (
                ('{"FileVersion": 3, "FileVersion": 2}', "Duplicate JSON object key"),
                ('{"FileVersion": NaN}', "Non-standard JSON constant"),
                ('{"FileVersion": Infinity}', "Non-standard JSON constant"),
                ('{"FileVersion": -Infinity}', "Non-standard JSON constant"),
            )

            for content, expected_message in cases:
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, expected_message):
                        read_json(path)

    def test_json_reader_rejects_malformed_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "Fixture.uproject"
            cases = (
                '{"FileVersion": 3',
                '{"Modules": [}',
                '{"Plugins": [],}',
            )

            for content in cases:
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        read_json(path)

    def test_descriptor_validates_modules_and_core_field_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_file = Path(temporary_directory) / "Fixture.uproject"
            self.write_json(
                project_file,
                {
                    "FileVersion": 3,
                    "EngineAssociation": 5,
                    "Category": [],
                    "Description": {},
                    "Modules": [
                        {"Name": "Fixture"},
                        {"Name": "fixture"},
                        {"Name": ""},
                        {"Type": "Runtime"},
                        42,
                    ],
                    "Plugins": [],
                },
            )

            _, result = descriptor_result(project_file)

        self.assertEqual(result["declared_modules"], ["Fixture", "fixture"])
        self.assertEqual(result["validation"]["status"], "error")
        problems = result["validation"]["problems"]
        self.assertEqual(
            {
                problem.get("descriptor_pointer")
                for problem in problems
                if problem["code"] == "invalid-project-field-type"
            },
            {"/EngineAssociation", "/Category", "/Description"},
        )
        duplicate = next(
            problem
            for problem in problems
            if problem["code"] == "duplicate-module-declaration"
        )
        self.assertEqual(
            duplicate["descriptor_pointers"], ["/Modules/0", "/Modules/1"]
        )
        self.assertEqual(
            {
                problem["descriptor_pointer"]
                for problem in problems
                if problem["code"] == "invalid-module-declaration"
            },
            {"/Modules/2", "/Modules/3", "/Modules/4"},
        )

    def test_descriptor_rejects_non_array_modules_and_boolean_file_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_file = Path(temporary_directory) / "Fixture.uproject"
            self.write_json(
                project_file,
                {"FileVersion": True, "Modules": {}, "Plugins": []},
            )

            _, result = descriptor_result(project_file)

        self.assertEqual(result["declared_modules"], [])
        self.assertEqual(
            {problem["code"] for problem in result["validation"]["problems"]},
            {"unsupported-project-file-version", "invalid-module-declarations"},
        )

    def test_descriptor_compacts_modules_and_plugin_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_file = Path(temporary_directory) / "Fixture.uproject"
            self.write_json(
                project_file,
                {
                    "FileVersion": 3,
                    "Modules": [
                        {
                            "Name": "Fixture",
                            "Type": "Runtime",
                            "LoadingPhase": "Default",
                        }
                    ],
                    "Plugins": [
                        {"Name": "SimpleEnabled", "Enabled": True},
                        {"Name": "SimpleDisabled", "Enabled": False},
                        {
                            "Name": "Extended",
                            "Enabled": True,
                            "Optional": True,
                        },
                        {"Name": "Invalid"},
                    ],
                },
            )

            _, result = descriptor_result(project_file)

            self.assertEqual(
                result["schema_version"], "ue-itps.project-descriptor.v5"
            )
            self.assertEqual(result["declared_modules"], ["Fixture"])
            self.assertNotIn("descriptor_sha256", result["project"])
            self.assertNotIn("declared_module_count", result)
            self.assertEqual(
                result["descriptor_top_level_fields"],
                ["FileVersion", "Modules", "Plugins"],
            )
            self.assertNotIn("top_level_fields", result)
            self.assertNotIn("module_declarations", result)
            self.assertNotIn("plugin_references", result)
            self.assertEqual(
                result["plugin_declarations"],
                {
                    "enabled": ["SimpleEnabled"],
                    "disabled": ["SimpleDisabled"],
                    "extended": [
                        {
                            "name": "Extended",
                            "declared_enabled": True,
                            "descriptor_pointer": "/Plugins/2",
                            "additional_fields": ["Optional"],
                        }
                    ],
                },
            )
            self.assertEqual(result["validation"]["status"], "error")
            self.assertEqual(
                result["validation"]["problems"][0]["code"],
                "invalid-plugin-reference",
            )

    def test_descriptor_rejects_invalid_directories_and_duplicate_plugins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_file = Path(temporary_directory) / "Fixture.uproject"
            self.write_json(
                project_file,
                {
                    "FileVersion": 3,
                    "Plugins": [
                        {"Name": "FixturePlugin", "Enabled": True},
                        {"Name": "fixtureplugin", "Enabled": False},
                    ],
                    "AdditionalPluginDirectories": "Plugins",
                },
            )

            _, result = descriptor_result(project_file)

        problems = {
            problem["code"]: problem
            for problem in result["validation"]["problems"]
        }
        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(
            problems["duplicate-plugin-reference"]["descriptor_pointers"],
            ["/Plugins/0", "/Plugins/1"],
        )
        self.assertEqual(
            problems["invalid-additional-directory"]["descriptor_pointer"],
            "/AdditionalPluginDirectories",
        )

    def test_external_additional_plugin_directory_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "Project"
            project_root.mkdir()
            project_file = project_root / "Fixture.uproject"
            self.write_json(project_file, {"FileVersion": 3, "Plugins": []})
            descriptor = {"AdditionalPluginDirectories": ["../ExternalPlugins"]}
            roots, findings = resolve_internal_directories(
                project_file, descriptor, "AdditionalPluginDirectories"
            )
            problems = directory_finding_problems(
                "AdditionalPluginDirectories", findings, warn_external=True
            )
            result = resolve_project_plugins(
                project_file,
                project_root,
                None,
                [],
                roots,
                "scan",
                "Win64",
                "Editor",
                findings,
                problems,
            )

        self.assertEqual(roots, [])
        self.assertEqual(findings[0]["status"], "skipped_external")
        self.assertEqual(
            problems[0]["code"], "external-additional-plugin-directory-skipped"
        )
        self.assertEqual(result["additional_plugin_directories"], findings)
        self.assertEqual(result["validation"]["status"], "warning")

    def test_plugin_resolution_rejects_non_array_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            project_file = project_root / "Fixture.uproject"
            self.write_json(project_file, {"FileVersion": 3, "Plugins": 42})

            result = resolve_project_plugins(
                project_file,
                project_root,
                None,
                42,
                [],
                "scan",
                "Win64",
                "Editor",
            )

        self.assertEqual(result["items"], [])
        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "invalid-plugin-references",
        )

    def test_module_inspection_does_not_repeat_raw_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            module_root = project_root / "Source" / "Fixture"
            module_root.mkdir(parents=True)
            (module_root / "Fixture.Build.cs").write_text("", encoding="utf-8")
            (module_root / "Fixture.cpp").write_text(
                "IMPLEMENT_GAME_MODULE(FDefaultModuleImpl, Fixture);",
                encoding="utf-8",
            )

            result = inspect_modules(
                project_root,
                [{"Name": "Fixture", "Type": "Runtime"}],
                [],
            )

            self.assertEqual(
                result["schema_version"], "ue-itps.project-modules.v5"
            )
            self.assertNotIn("count", result)
            self.assertEqual(result["reconciled_module_count"], 1)
            self.assertEqual(
                result["reconciled_module_count"], len(result["items"])
            )
            self.assertEqual(result["validation"]["status"], "ok")
            module = result["items"][0]
            self.assertNotIn("raw_declaration", module)
            self.assertNotIn("conventional_location", module)
            self.assertNotIn("build_rule_candidates", module["actual"])
            self.assertNotIn("build_rule_evidence", module["actual"])
            self.assertNotIn("source_file_count", module["actual"])
            self.assertNotIn("status", module)
            self.assertEqual(module["build_rules"]["status"], "resolved")
            self.assertEqual(len(module["build_rules"]["candidates"]), 1)
            candidate = module["build_rules"]["candidates"][0]
            self.assertEqual(candidate["path"], module_root.as_posix() + "/Fixture.Build.cs")
            self.assertTrue(candidate["conventional"])
            self.assertNotIn("sha256", candidate)
            self.assertEqual(
                module["actual"]["module_entrypoint_candidates"],
                [
                    {
                        "path": module_root.as_posix() + "/Fixture.cpp",
                        "macro": "IMPLEMENT_GAME_MODULE",
                        "module_class": "FDefaultModuleImpl",
                        "module_name": "Fixture",
                    }
                ],
            )

    def test_module_inspection_reports_missing_build_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = inspect_modules(
                Path(temporary_directory), [{"Name": "Fixture"}], []
            )

            self.assertEqual(result["reconciled_module_count"], 0)
            self.assertEqual(result["items"], [])
            self.assertEqual(result["validation"]["status"], "error")
            problem = result["validation"]["problems"][0]
            self.assertEqual(problem["code"], "project-module-build-rules-missing")
            self.assertEqual(problem["module_name"], "Fixture")
            self.assertEqual(problem["candidates"], [])

    def test_module_inspection_reports_ambiguous_build_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            conventional_root = project_root / "Source" / "Fixture"
            platform_root = project_root / "Platforms" / "Win64" / "Fixture"
            conventional_root.mkdir(parents=True)
            platform_root.mkdir(parents=True)
            (conventional_root / "Fixture.Build.cs").write_text("", encoding="utf-8")
            (platform_root / "Fixture.Build.cs").write_text("", encoding="utf-8")

            result = inspect_modules(project_root, [{"Name": "Fixture"}], [])

            self.assertEqual(result["reconciled_module_count"], 0)
            self.assertEqual(result["items"], [])
            self.assertEqual(result["validation"]["status"], "error")
            problem = result["validation"]["problems"][0]
            self.assertEqual(
                problem["code"], "project-module-build-rules-ambiguous"
            )
            self.assertEqual(problem["module_name"], "Fixture")
            self.assertEqual(len(problem["candidates"]), 2)
            self.assertEqual(
                sum(
                    candidate["conventional"]
                    for candidate in problem["candidates"]
                ),
                1,
            )

    def test_module_inspection_reports_undeclared_build_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            declared_root = project_root / "Source" / "Fixture"
            undeclared_root = project_root / "Source" / "ExtraModule"
            declared_root.mkdir(parents=True)
            undeclared_root.mkdir(parents=True)
            (declared_root / "Fixture.Build.cs").write_text("", encoding="utf-8")
            (undeclared_root / "ExtraModule.Build.cs").write_text(
                "", encoding="utf-8"
            )

            result = inspect_modules(project_root, [{"Name": "Fixture"}], [])

            self.assertEqual(result["reconciled_module_count"], 1)
            self.assertEqual([item["name"] for item in result["items"]], ["Fixture"])
            self.assertEqual(result["validation"]["status"], "error")
            problem = result["validation"]["problems"][0]
            self.assertEqual(
                problem["code"], "project-module-build-rules-undeclared"
            )
            self.assertEqual(problem["module_name"], "ExtraModule")
            self.assertEqual(len(problem["candidates"]), 1)
            candidate = problem["candidates"][0]
            self.assertEqual(
                candidate["path"],
                undeclared_root.as_posix() + "/ExtraModule.Build.cs",
            )
            self.assertNotIn("sha256", candidate)

    def test_module_inspection_compares_names_when_counts_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            actual_root = project_root / "Source" / "Actual"
            actual_root.mkdir(parents=True)
            (actual_root / "Actual.Build.cs").write_text("", encoding="utf-8")

            result = inspect_modules(project_root, [{"Name": "Expected"}], [])

            self.assertEqual(result["reconciled_module_count"], 0)
            self.assertEqual(result["items"], [])
            self.assertEqual(result["validation"]["status"], "error")
            self.assertEqual(
                {
                    problem["code"]
                    for problem in result["validation"]["problems"]
                },
                {
                    "project-module-build-rules-missing",
                    "project-module-build-rules-undeclared",
                },
            )

    def test_module_inspection_reports_duplicate_declarations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            module_root = project_root / "Source" / "Fixture"
            module_root.mkdir(parents=True)
            (module_root / "Fixture.Build.cs").write_text("", encoding="utf-8")

            result = inspect_modules(
                project_root,
                [{"Name": "Fixture"}, {"Name": "Fixture"}],
                [],
            )

            self.assertEqual(result["reconciled_module_count"], 0)
            self.assertEqual(result["items"], [])
            self.assertEqual(result["validation"]["status"], "error")
            self.assertEqual(
                result["validation"]["problems"][0]["code"],
                "project-module-declaration-duplicate",
            )
            self.assertEqual(
                result["validation"]["problems"][0]["descriptor_pointer"],
                "/Modules/1",
            )

    def test_plugin_resolution_uses_declared_state_without_raw_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            project_file = project_root / "Fixture.uproject"
            declarations = [
                {"Name": "FixturePlugin", "Enabled": True},
                {"Name": "OptionalPlugin", "Enabled": True, "Optional": True},
                {"Name": "DisabledPlugin", "Enabled": False},
            ]
            self.write_json(
                project_file,
                {"FileVersion": 3, "Plugins": declarations},
            )
            self.write_json(
                project_root
                / "Plugins"
                / "FixturePlugin"
                / "FixturePlugin.uplugin",
                {"FileVersion": 3},
            )
            self.write_json(
                project_root
                / "Plugins"
                / "DisabledPlugin"
                / "DisabledPlugin.uplugin",
                {"FileVersion": 3},
            )

            result = resolve_project_plugins(
                project_file,
                project_root,
                None,
                declarations,
                [],
                "scan",
                "Win64",
                "Editor",
            )

            self.assertEqual(
                result["schema_version"],
                "ue-itps.project-plugin-references.v5",
            )
            self.assertEqual(result["declared_enabled_count"], 2)
            self.assertEqual(result["declared_disabled_count"], 1)
            self.assertEqual(result["project_descriptor"]["path"], "Fixture.uproject")
            self.assertNotIn("sha256", result["project_descriptor"])
            self.assertEqual(
                result["items"][0]["descriptor"],
                "Plugins/FixturePlugin/FixturePlugin.uplugin",
            )
            self.assertTrue(result["item_defaults"]["declared_enabled"])
            self.assertNotIn("declared_enabled", result["items"][0])
            self.assertNotIn("descriptor_pointer", result["items"][0])
            self.assertNotIn("raw_declaration", result["items"][0])
            self.assertEqual(result["items"][1]["status"], "not-found")
            self.assertTrue(result["items"][1]["declared_enabled"])
            self.assertIsNone(result["items"][1]["descriptor"])
            self.assertEqual(result["items"][1]["alternate_descriptors"], [])
            self.assertEqual(result["items"][1]["filters"], {})
            self.assertFalse(result["items"][2]["declared_enabled"])
            self.assertNotIn("status", result["items"][2])

            result["item_defaults"]["filters"]["mutated"] = True
            second_result = resolve_project_plugins(
                project_file,
                project_root,
                None,
                declarations,
                [],
                "scan",
                "Win64",
                "Editor",
            )
            self.assertEqual(second_result["item_defaults"]["filters"], {})


if __name__ == "__main__":
    unittest.main()
