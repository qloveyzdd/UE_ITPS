from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


TOOLS_ROOT = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_ROOT))

from ue_project_tools.code_inventory import inspect_modules
from ue_project_tools.descriptor import descriptor_result
from ue_project_tools.plugins import resolve_project_plugins


class ProjectDescriptorContractTests(unittest.TestCase):
    def write_json(self, path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

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
                result["schema_version"], "ue-itps.project-descriptor.v3"
            )
            self.assertEqual(result["declared_modules"], ["Fixture"])
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
                    "count": 4,
                    "enabled_count": 1,
                    "disabled_count": 1,
                    "extended_count": 1,
                    "invalid_count": 1,
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
                result["schema_version"], "ue-itps.project-modules.v2"
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
            self.assertEqual(len(candidate["sha256"]), 64)
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

            module = result["items"][0]
            self.assertEqual(module["build_rules"]["status"], "missing")
            self.assertEqual(module["build_rules"]["candidates"], [])
            self.assertEqual(result["validation"]["status"], "error")
            self.assertEqual(
                result["validation"]["problems"][0]["code"],
                "project-module-build-rules-missing",
            )

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

            module = result["items"][0]
            self.assertEqual(module["build_rules"]["status"], "ambiguous")
            self.assertEqual(len(module["build_rules"]["candidates"]), 2)
            self.assertEqual(
                sum(
                    candidate["conventional"]
                    for candidate in module["build_rules"]["candidates"]
                ),
                1,
            )
            self.assertEqual(result["validation"]["status"], "error")
            self.assertEqual(
                result["validation"]["problems"][0]["code"],
                "project-module-build-rules-ambiguous",
            )

    def test_plugin_resolution_uses_declared_state_without_raw_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            project_file = project_root / "Fixture.uproject"
            declarations = [
                {"Name": "FixturePlugin", "Enabled": True},
                {"Name": "OptionalPlugin", "Enabled": True, "Optional": True},
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

            result = resolve_project_plugins(
                project_file,
                project_root,
                None,
                declarations,
                [],
                "scan",
                "Win64",
                "Editor",
                "Development",
            )

            self.assertEqual(
                result["schema_version"],
                "ue-itps.project-plugin-references.v2",
            )
            self.assertEqual(result["declared_enabled_count"], 2)
            self.assertEqual(result["declared_disabled_count"], 0)
            self.assertIsNotNone(result["project_descriptor"]["sha256"])
            self.assertTrue(result["items"][0]["declared_enabled"])
            self.assertNotIn("raw_declaration", result["items"][0])


if __name__ == "__main__":
    unittest.main()
