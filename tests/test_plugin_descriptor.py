from __future__ import annotations

from pathlib import Path
import tempfile

from tools.ue_project_tools.plugin_descriptor import read_plugin_descriptor

from tests.support import EnvelopeAssertions, create_fixture, write_text


class PluginDescriptorTests(EnvelopeAssertions):
    def test_descriptor_reconciles_declared_module_and_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            result = read_plugin_descriptor(fixture.plugin_file)

        self.assert_envelope(result)
        self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(result["modules"][0]["name"], "FixturePlugin")
        self.assertEqual(
            result["modules"][0]["build_rules"]["status"],
            "resolved",
        )
        self.assertEqual(
            result["plugin_dependencies"][0]["name"],
            "GameplayTags",
        )

    def test_descriptor_reports_duplicate_fields_and_missing_build_rules(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            fixture.plugin_rules.unlink()
            write_text(
                fixture.plugin_file,
                """
                {
                  "FileVersion": 3,
                  "FriendlyName": "First",
                  "FriendlyName": "Second",
                  "Modules": [
                    {
                      "Name": "FixturePlugin",
                      "Type": "Runtime",
                      "LoadingPhase": "Default"
                    }
                  ]
                }
                """,
            )
            result = read_plugin_descriptor(fixture.plugin_file)

        codes = {problem["code"] for problem in result["validation"]["problems"]}
        self.assertEqual(result["validation"]["status"], "error")
        self.assertIn("duplicate-plugin-descriptor-field", codes)
        self.assertIn("plugin-module-build-rules-missing", codes)

    def test_descriptor_rejects_wrong_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "Fixture.json"
            write_text(path, '{"FileVersion": 3}')
            with self.assertRaisesRegex(ValueError, r"Expected a \.uplugin file"):
                read_plugin_descriptor(path)
