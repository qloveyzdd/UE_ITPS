from __future__ import annotations

from tests.fixture import FixtureTestCase, run_cli, write_text


class BuildLayerTests(FixtureTestCase):
    def test_plugin_descriptor_reconciles_module_and_dependency(self) -> None:
        result = self.cli(
            "ue_read_plugin_descriptor.py",
            "--plugin",
            str(self.fixture.plugin_file),
        )
        self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(result["modules"][0]["name"], "CurrentPlugin")
        self.assertEqual(
            result["modules"][0]["build_rules"]["status"],
            "resolved",
        )
        self.assertEqual(
            result["plugin_dependencies"][0]["name"],
            "GameplayTags",
        )

    def test_plugin_descriptor_reports_duplicates_and_missing_rules(self) -> None:
        self.fixture.plugin_rules.unlink()
        write_text(
            self.fixture.plugin_file,
            """
            {
              "FileVersion": 3,
              "FriendlyName": "First",
              "FriendlyName": "Second",
              "Modules": [
                {
                  "Name": "CurrentPlugin",
                  "Type": "Runtime",
                  "LoadingPhase": "Default"
                }
              ]
            }
            """,
        )
        result = self.cli(
            "ue_read_plugin_descriptor.py",
            "--plugin",
            str(self.fixture.plugin_file),
            expected_code=1,
        )
        codes = {problem["code"] for problem in result["validation"]["problems"]}
        self.assertIn("duplicate-plugin-descriptor-field", codes)
        self.assertIn("plugin-module-build-rules-missing", codes)

    def test_plugin_descriptor_rejects_non_uplugin_input(self) -> None:
        wrong = self.fixture.workspace / "CurrentPlugin.json"
        write_text(wrong, '{"FileVersion": 3}')
        completed = run_cli(
            "ue_read_plugin_descriptor.py",
            "--plugin",
            str(wrong),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("Expected a .uplugin file", completed.stderr)

    def test_module_rules_follow_local_helper_and_preserve_condition(self) -> None:
        result = self.cli(
            "ue_inspect_module_rules.py",
            "--rules",
            str(self.fixture.game_rules),
        )
        rules = result["rules_classes"][0]
        mutations = rules["declared_mutations"]
        settings = {item["setting"] for item in mutations}
        self.assertTrue(
            {
                "PCHUsage",
                "PublicDependencyModuleNames",
                "PrivateDependencyModuleNames",
                "DynamicallyLoadedModuleNames",
            }.issubset(settings)
        )
        conditional = next(
            item
            for item in mutations
            if item["setting"] == "PrivateDependencyModuleNames"
        )
        self.assertEqual(conditional["applicability"]["kind"], "conditional")
        self.assertEqual(
            conditional["applicability"]["control_path"],
            ["if"],
        )

    def test_target_rules_indexes_variables_functions_and_inheritance(self) -> None:
        result = self.cli(
            "ue_inspect_target_rules.py",
            "--target",
            str(self.fixture.target_file),
        )
        rules = result["rules_classes"][0]
        self.assertEqual(rules["name"], "CurrentGameTarget")
        self.assertEqual(rules["base_types"], ["TargetRules"])
        self.assertEqual(rules["inheritance"]["kind"], "confirmed")
        self.assertEqual(
            rules["member_details"]["variables"][0]["name"],
            "SharedDefinition",
        )
        functions = {
            item["name"]: item for item in rules["member_details"]["functions"]
        }
        self.assertTrue(functions["CurrentGameTarget"]["is_constructor"])
        self.assertFalse(functions["ApplySharedSettings"]["is_constructor"])
        self.assertNotIn("declared_mutations", rules)

    def test_csharp_function_reports_external_types_and_local_calls(self) -> None:
        result = self.cli(
            "ue_inspect_cs_function.py",
            "--source",
            str(self.fixture.target_file),
            "--function",
            "CurrentGameTarget",
        )
        self.assertEqual(result["selection"]["name"], "CurrentGameTarget")
        self.assertEqual(result["match_count"], 1)
        match = result["matches"][0]
        self.assertIn("TargetInfo", match["external_types"])
        self.assertIn("ApplySharedSettings(Target)", match["external_methods"])

    def test_missing_csharp_function_is_a_structured_scan_error(self) -> None:
        result = self.cli(
            "ue_inspect_cs_function.py",
            "--source",
            str(self.fixture.target_file),
            "--function",
            "DoesNotExist",
            expected_code=1,
        )
        self.assertEqual(result["match_count"], 0)
        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "function-not-found",
        )

    def test_module_entry_reports_registration_binding_and_cleanup(self) -> None:
        result = self.cli(
            "ue_inspect_module_entry.py",
            "--rules",
            str(self.fixture.plugin_rules),
        )
        self.assertEqual(result["registration"]["macro"], "IMPLEMENT_MODULE")
        self.assertEqual(
            result["registration"]["module_class"],
            "FCurrentPluginModule",
        )
        binding = result["callback_bindings"][0]
        self.assertEqual(binding["bind"]["api"], "AddRaw")
        self.assertEqual(
            binding["callback"]["target"],
            "FCurrentPluginModule::HandleReady",
        )
        self.assertEqual(binding["unbind"][0]["api"], "Remove")

    def test_wrong_module_rules_base_fails_closed(self) -> None:
        wrong = self.fixture.workspace / "Wrong.Build.cs"
        write_text(
            wrong,
            """
            public class Wrong : NotModuleRules
            {
                public Wrong(ReadOnlyTargetRules Target) {}
            }
            """,
        )
        result = self.cli(
            "ue_inspect_module_rules.py",
            "--rules",
            str(wrong),
            expected_code=1,
        )
        self.assertEqual(result["rules_classes"], [])
        self.assertEqual(result["validation"]["status"], "error")
