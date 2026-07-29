from __future__ import annotations

import json

from tests.support import WorkspaceTestCase, run_cli, write_json, write_text


class BuildAnalysisTests(WorkspaceTestCase):
    def test_plugin_descriptor_reconciles_module_and_dependency(self) -> None:
        result = self.cli(
            "ue_read_plugin_descriptor.py",
            "--plugin",
            str(self.fixture.plugin_file),
        )
        self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(result["modules"][0]["name"], "SamplePlugin")
        self.assertEqual(
            result["modules"][0]["build_rules"]["status"],
            "resolved",
        )
        self.assertEqual(
            result["plugin_dependencies"][0]["name"],
            "GameplayTags",
        )

    def test_plugin_descriptor_accepts_comments_and_trailing_commas(self) -> None:
        write_text(
            self.fixture.plugin_file,
            """
            {
              // Unreal descriptors commonly use comments.
              "FileVersion": 3,
              "FriendlyName": "Commented Plugin",
              "Modules": [
                {
                  "Name": "SamplePlugin",
                  "Type": "Runtime",
                  "LoadingPhase": "Default",
                },
              ],
            }
            """,
        )
        result = self.cli(
            "ue_read_plugin_descriptor.py",
            "--plugin",
            str(self.fixture.plugin_file),
        )
        self.assertEqual(
            result["descriptor_fields"]["FriendlyName"],
            "Commented Plugin",
        )
        self.assertEqual(result["modules"][0]["name"], "SamplePlugin")

    def test_plugin_descriptor_reports_duplicate_field_and_missing_rules(self) -> None:
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
                  "Name": "SamplePlugin",
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

    def test_plugin_descriptor_rejects_wrong_suffix(self) -> None:
        wrong = self.fixture.workspace / "SamplePlugin.json"
        write_text(wrong, '{"FileVersion": 3}')
        completed = run_cli(
            "ue_read_plugin_descriptor.py",
            "--plugin",
            str(wrong),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stderr, "")
        result = json.loads(completed.stdout)
        self.assert_request_failure(result, kind="input")
        self.assertIn(
            "Expected a .uplugin file",
            result["validation"]["problems"][0]["message"],
        )

    def test_plugin_resolution_reports_alternate_descriptor(self) -> None:
        alternate = (
            self.fixture.engine_root
            / "Engine"
            / "Plugins"
            / "Runtime"
            / "SamplePlugin"
            / "SamplePlugin.uplugin"
        )
        write_json(alternate, {"FileVersion": 3})
        result = self.cli(
            "ue_resolve_plugins.py",
            "--project",
            str(self.fixture.project_file),
            "--engine-root",
            str(self.fixture.engine_root),
            "--plugin-name",
            "SamplePlugin",
        )
        plugin = result["items"][0]
        self.assertEqual(plugin["origin"], "project")
        self.assertEqual(
            plugin["alternate_descriptors"],
            [
                {
                    "origin": "engine",
                    "path": "Engine/Plugins/Runtime/SamplePlugin/SamplePlugin.uplugin",
                }
            ],
        )

    def test_module_rules_follow_helper_and_preserve_condition(self) -> None:
        result = self.cli(
            "ue_inspect_module_rules.py",
            "--rules",
            str(self.fixture.game_rules),
        )
        mutations = result["rules_classes"][0]["declared_mutations"]
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
        self.assertEqual(conditional["applicability"]["control_path"], ["if"])

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

    def test_target_rules_index_variables_functions_and_inheritance(self) -> None:
        result = self.cli(
            "ue_inspect_target_rules.py",
            "--target",
            str(self.fixture.target_file),
        )
        rules = result["rules_classes"][0]
        self.assertEqual(rules["name"], "SampleGameTarget")
        self.assertEqual(rules["base_types"], ["TargetRules"])
        self.assertEqual(rules["inheritance"]["kind"], "confirmed")
        self.assertEqual(
            rules["member_details"]["variables"][0]["name"],
            "SharedDefinition",
        )
        functions = {
            item["name"]: item for item in rules["member_details"]["functions"]
        }
        self.assertTrue(functions["SampleGameTarget"]["is_constructor"])
        self.assertFalse(functions["ApplySharedSettings"]["is_constructor"])
        self.assertNotIn("declared_mutations", rules)

    def test_csharp_function_reports_external_types_and_local_calls(self) -> None:
        result = self.cli(
            "ue_inspect_cs_function.py",
            "--source",
            str(self.fixture.target_file),
            "--function",
            "SampleGameTarget",
        )
        self.assertEqual(result["selection"]["name"], "SampleGameTarget")
        self.assertEqual(result["match_count"], 1)
        match = result["matches"][0]
        self.assertIn("TargetInfo", match["external_types"])
        self.assertIn("ApplySharedSettings(Target)", match["external_methods"])

    def test_csharp_function_selection_returns_all_overloads(self) -> None:
        source = self.fixture.workspace / "Plain.cs"
        write_text(
            source,
            """
            public class Plain
            {
                public void Run(int Count) {}
                public void Run(string Name) {}
            }
            """,
        )
        result = self.cli(
            "ue_inspect_cs_function.py",
            "--source",
            str(source),
            "--function",
            "Run",
        )
        self.assertEqual(result["match_count"], 2)
        signatures = [item["function"]["signature"] for item in result["matches"]]
        self.assertEqual(len(signatures), len(set(signatures)))

    def test_missing_csharp_function_is_structured_scan_error(self) -> None:
        result = self.cli(
            "ue_inspect_cs_function.py",
            "--source",
            str(self.fixture.target_file),
            "--function",
            "DoesNotExist",
            expected_code=1,
        )
        self.assertEqual(result["match_count"], 0)
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
            "FSamplePluginModule",
        )
        binding = result["callback_bindings"][0]
        self.assertEqual(binding["bind"]["api"], "AddRaw")
        self.assertEqual(
            binding["callback"]["target"],
            "FSamplePluginModule::HandleReady",
        )
        self.assertEqual(binding["unbind"][0]["api"], "Remove")

    def test_default_module_registration_does_not_invent_local_state(self) -> None:
        write_text(
            self.fixture.plugin_entry,
            """
            #include "Modules/ModuleManager.h"
            IMPLEMENT_MODULE(FDefaultModuleImpl, SamplePlugin)
            """,
        )
        result = self.cli(
            "ue_inspect_module_entry.py",
            "--rules",
            str(self.fixture.plugin_rules),
        )
        self.assertEqual(
            result["registration"]["module_class"],
            "FDefaultModuleImpl",
        )
        self.assertIsNone(result["module"]["class"])
        self.assertEqual(result["callback_bindings"], [])
        self.assertEqual(result["state_models"], [])

    def test_unbalanced_module_source_keeps_partial_registration(self) -> None:
        write_text(
            self.fixture.plugin_entry,
            """
            #include "Modules/ModuleManager.h"
            class FBrokenModule : public IModuleInterface
            {
            public:
                virtual void StartupModule() override
                {
            IMPLEMENT_MODULE(FBrokenModule, SamplePlugin)
            """,
        )
        result = self.cli(
            "ue_inspect_module_entry.py",
            "--rules",
            str(self.fixture.plugin_rules),
            expected_code=1,
        )
        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(
            result["registration"]["module_class"],
            "FBrokenModule",
        )
        self.assertGreater(result["validation"]["problem_count"], 0)


if __name__ == "__main__":
    import unittest

    unittest.main()
