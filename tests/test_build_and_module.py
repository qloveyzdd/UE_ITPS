from __future__ import annotations

from tests.support import CliTestCase, write_text


class BuildAndModuleTests(CliTestCase):
    def test_plugin_descriptor_reconciles_module_and_dependency(self) -> None:
        result = self.cli(
            "ue_read_plugin_descriptor.py",
            "--plugin",
            str(self.fixture.plugin),
        )
        self.assertEqual(result["file_version"], 3)
        self.assertEqual(result["descriptor_fields"]["FriendlyName"], "Sample Plugin")
        self.assertEqual(result["modules"][0]["name"], "SamplePlugin")
        self.assertEqual(
            result["modules"][0]["build_rules"]["status"],
            "resolved",
        )
        self.assertEqual(
            result["plugin_dependencies"][0]["name"],
            "GameplayAbilities",
        )

    def test_plugin_descriptor_accepts_comments_and_trailing_commas(self) -> None:
        plugin_root = self.fixture.project_root / "Plugins" / "Commented"
        plugin = write_text(
            plugin_root / "Commented.uplugin",
            """
            {
              // Unreal descriptors commonly contain comments.
              "FileVersion": 3,
              "FriendlyName": "Commented",
              "Modules": [
                {
                  "Name": "Commented",
                  "Type": "Runtime",
                  "LoadingPhase": "Default",
                },
              ],
            }
            """,
        )
        write_text(
            plugin_root / "Source" / "Commented" / "Commented.Build.cs",
            """
            public class Commented : ModuleRules
            {
                public Commented(ReadOnlyTargetRules Target) : base(Target) {}
            }
            """,
        )
        result = self.cli(
            "ue_read_plugin_descriptor.py",
            "--plugin",
            str(plugin),
        )
        self.assertEqual(result["modules"][0]["name"], "Commented")
        self.assertEqual(result["validation"]["status"], "ok")

    def test_plugin_descriptor_reports_duplicate_fields(self) -> None:
        plugin = write_text(
            self.fixture.root / "Duplicate.uplugin",
            """
            {
              "FileVersion": 3,
              "FileVersion": 4,
              "Modules": []
            }
            """,
        )
        result = self.cli(
            "ue_read_plugin_descriptor.py",
            "--plugin",
            str(plugin),
            expected_code=1,
        )
        self.assertEqual(result["validation"]["status"], "error")
        self.assertTrue(
            any(
                problem["code"] == "duplicate-plugin-descriptor-field"
                for problem in result["validation"]["problems"]
            )
        )

    def test_plugin_descriptor_rejects_wrong_suffix(self) -> None:
        wrong = write_text(
            self.fixture.root / "Plugin.json",
            '{"FileVersion": 3}',
        )
        result = self.cli(
            "ue_read_plugin_descriptor.py",
            "--plugin",
            str(wrong),
            expected_code=2,
        )
        self.assert_request_failure(result, kind="input")

    def test_module_rules_report_only_direct_dependency_names(self) -> None:
        result = self.cli(
            "ue_inspect_module_rules.py",
            "--rules",
            str(self.fixture.module_rules),
        )
        self.assertNotIn("path", result)
        rules = result["rules_classes"][0]
        self.assertEqual(
            rules,
            {
                "name": "SampleGame",
                "dependencies": {
                    "public": ["Core", "GameplayTags"],
                    "private": ["UnrealEd"],
                    "dynamic": [],
                },
            },
        )

    def test_module_rules_group_and_deduplicate_all_dependency_kinds(self) -> None:
        path = write_text(
            self.fixture.root / "AllDependencies.Build.cs",
            """
            public class AllDependencies : ModuleRules
            {
                public AllDependencies(ReadOnlyTargetRules Target) : base(Target)
                {
                    PublicDependencyModuleNames.Add("Core");
                    PublicDependencyModuleNames.AddRange(
                        new string[] { "Engine", "Core" }
                    );
                    PrivateDependencyModuleNames.Add("Slate");
                    if (Target.bBuildEditor)
                    {
                        DynamicallyLoadedModuleNames.Add("AssetTools");
                    }
                    Configure();
                    PublicDefinitions.Add("WITH_SAMPLE=1");
                }

                private void Configure()
                {
                    PrivateDependencyModuleNames.Add("InputCore");
                }
            }
            """,
        )
        result = self.cli(
            "ue_inspect_module_rules.py",
            "--rules",
            str(path),
        )
        self.assertEqual(
            result["rules_classes"][0]["dependencies"],
            {
                "public": ["Core", "Engine"],
                "private": ["Slate", "InputCore"],
                "dynamic": ["AssetTools"],
            },
        )

    def test_module_rules_warn_when_dependency_expression_is_unresolved(self) -> None:
        path = write_text(
            self.fixture.root / "ComputedDependencies.Build.cs",
            """
            public class ComputedDependencies : ModuleRules
            {
                public ComputedDependencies(ReadOnlyTargetRules Target) : base(Target)
                {
                    PublicDependencyModuleNames.AddRange(
                        new string[] { "Core", Target.Name }
                    );
                    DynamicallyLoadedModuleNames.Add(GetDynamicModule());
                }
            }
            """,
        )
        result = self.cli(
            "ue_inspect_module_rules.py",
            "--rules",
            str(path),
        )
        self.assertEqual(
            result["rules_classes"][0]["dependencies"],
            {
                "public": ["Core"],
                "private": [],
                "dynamic": [],
            },
        )
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertEqual(
            [problem["code"] for problem in result["validation"]["problems"]],
            [
                "module-dependency-expression-unresolved",
                "module-dependency-expression-unresolved",
            ],
        )

    def test_module_rules_accept_empty_add_range_without_warning(self) -> None:
        path = write_text(
            self.fixture.root / "EmptyDependencies.Build.cs",
            """
            public class EmptyDependencies : ModuleRules
            {
                public EmptyDependencies(ReadOnlyTargetRules Target) : base(Target)
                {
                    DynamicallyLoadedModuleNames.AddRange(
                        new string[] {
                        }
                    );
                }
            }
            """,
        )
        result = self.cli(
            "ue_inspect_module_rules.py",
            "--rules",
            str(path),
        )
        self.assertEqual(result["rules_classes"][0]["dependencies"]["dynamic"], [])
        self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(result["validation"]["problems"], [])

    def test_non_module_rules_class_fails_closed(self) -> None:
        path = write_text(
            self.fixture.root / "Wrong.Build.cs",
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
            str(path),
            expected_code=1,
        )
        self.assertEqual(result["rules_classes"], [])
        self.assertEqual(result["validation"]["status"], "error")

    def test_target_rules_index_class_variables_and_functions(self) -> None:
        result = self.cli(
            "ue_inspect_target_rules.py",
            "--target",
            str(self.fixture.game_target),
        )
        rules_class = result["rules_classes"][0]
        self.assertEqual(rules_class["name"], "SampleGameTarget")
        self.assertEqual(rules_class["inheritance"]["kind"], "confirmed")
        self.assertEqual(
            [item["name"] for item in rules_class["member_details"]["variables"]],
            ["Flavor"],
        )
        self.assertEqual(
            [item["name"] for item in rules_class["member_details"]["functions"]],
            ["SampleGameTarget", "Configure"],
        )

    def test_csharp_function_reports_external_types_and_methods(self) -> None:
        result = self.cli(
            "ue_inspect_cs_function.py",
            "--source",
            str(self.fixture.game_target),
            "--function",
            "SampleGameTarget",
        )
        self.assertEqual(result["match_count"], 1)
        match = result["matches"][0]
        self.assertIn("TargetInfo", match["external_types"])
        self.assertIn("TargetType", match["external_types"])
        self.assertIn('Configure(Target)', match["external_methods"])

    def test_csharp_function_returns_all_same_name_overloads(self) -> None:
        source = write_text(
            self.fixture.root / "Overloads.cs",
            """
            public class Overloads
            {
                public void Configure(TargetInfo Target) {}
                public void Configure(ReadOnlyTargetRules Target) {}
            }
            """,
        )
        result = self.cli(
            "ue_inspect_cs_function.py",
            "--source",
            str(source),
            "--function",
            "Configure",
        )
        self.assertEqual(result["match_count"], 2)
        self.assertEqual(
            len({match["function_id"] for match in result["matches"]}),
            2,
        )

    def test_missing_csharp_function_is_structured_domain_error(self) -> None:
        result = self.cli(
            "ue_inspect_cs_function.py",
            "--source",
            str(self.fixture.game_target),
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
        self.assertEqual(result["module"]["name"], "SamplePlugin")
        self.assertEqual(
            result["registration"]["module_class"],
            "FSamplePluginModule",
        )
        self.assertEqual(len(result["callback_bindings"]), 1)
        binding = result["callback_bindings"][0]
        self.assertEqual(binding["bind"]["api"], "AddRaw")
        self.assertEqual(binding["callback"]["kind"], "function")
        self.assertEqual(binding["unbind"][0]["api"], "RemoveAll")
        self.assertEqual(result["unmatched_cleanups"], [])

    def test_default_game_module_registration_does_not_invent_local_class(self) -> None:
        result = self.cli(
            "ue_inspect_module_entry.py",
            "--rules",
            str(self.fixture.module_rules),
        )
        self.assertEqual(result["module"]["name"], "SampleGame")
        self.assertIsNone(result["module"]["class"])
        self.assertEqual(
            result["registration"]["module_class"],
            "FDefaultGameModuleImpl",
        )
        self.assertEqual(result["callback_bindings"], [])
