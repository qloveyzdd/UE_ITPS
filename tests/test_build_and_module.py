from __future__ import annotations

from tests.support import CliTestCase, write_text


class BuildAndModuleTests(CliTestCase):
    def test_plugin_descriptor_reports_only_modules_and_plugins(self) -> None:
        result = self.cli(
            "ue_read_plugin_descriptor.py",
            "--plugin",
            str(self.fixture.plugin),
        )
        self.assertEqual(
            list(result),
            [
                "schema_version",
                "modules",
                "plugin_dependencies",
                "validation",
                "limits",
            ],
        )
        self.assertEqual(result["modules"][0]["name"], "SamplePlugin")
        self.assertNotIn("build_rules", result["modules"][0])
        self.assertEqual(
            result["plugin_dependencies"][0]["name"],
            "GameplayAbilities",
        )
        self.assertNotIn("dependency_graph", result)

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
        result = self.cli(
            "ue_read_plugin_descriptor.py",
            "--plugin",
            str(plugin),
        )
        self.assertEqual(result["modules"][0]["name"], "Commented")
        self.assertEqual(result["validation"]["status"], "ok")

    def test_plugin_descriptor_ignores_other_top_level_fields(self) -> None:
        plugin = write_text(
            self.fixture.root / "Duplicate.uplugin",
            """
            {
              "FileVersion": "invalid but ignored",
              "FileVersion": 4,
              "LocalizationTargets": "invalid but ignored",
              "Modules": []
            }
            """,
        )
        result = self.cli(
            "ue_read_plugin_descriptor.py",
            "--plugin",
            str(plugin),
        )
        self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(result["modules"], [])
        self.assertEqual(result["plugin_dependencies"], [])

    def test_plugin_descriptor_reports_duplicate_modeled_fields(self) -> None:
        plugin = write_text(
            self.fixture.root / "Duplicate.uplugin",
            """
            {
              "Modules": [],
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
                    "public_dependency_modules": ["Core", "GameplayTags"],
                    "private_dependency_modules": ["UnrealEd"],
                    "dynamically_loaded_modules": [],
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
                "public_dependency_modules": ["Core", "Engine"],
                "private_dependency_modules": ["Slate", "InputCore"],
                "dynamically_loaded_modules": ["AssetTools"],
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
                "public_dependency_modules": ["Core"],
                "private_dependency_modules": [],
                "dynamically_loaded_modules": [],
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
        self.assertEqual(
            result["rules_classes"][0]["dependencies"][
                "dynamically_loaded_modules"
            ],
            [],
        )
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

    def test_module_entry_reports_registration_source_without_header(self) -> None:
        result = self.cli(
            "ue_inspect_module_entry.py",
            "--rules",
            str(self.fixture.plugin_rules),
        )
        self.assertNotIn("module", result)
        self.assertNotIn("registration", result)
        self.assertNotIn("callback_bindings", result)
        self.assertEqual(len(result["entrypoints"]), 1)
        entrypoint = result["entrypoints"][0]
        self.assertIsNone(entrypoint["header"])
        self.assertEqual(
            entrypoint["source"],
            self.fixture.plugin_source.resolve().as_posix(),
        )
        self.assertEqual(
            entrypoint["registration"]["module_class"],
            "FSamplePluginModule",
        )
        self.assertEqual(
            entrypoint["registration"]["macro"],
            "IMPLEMENT_MODULE",
        )
        self.assertIsInstance(
            entrypoint["registration"]["source_line"],
            int,
        )
        self.assertNotIn("line", entrypoint["registration"])

    def test_primary_game_module_reports_registration_source(self) -> None:
        result = self.cli(
            "ue_inspect_module_entry.py",
            "--rules",
            str(self.fixture.module_rules),
        )
        self.assertNotIn("module", result)
        self.assertEqual(len(result["entrypoints"]), 1)
        self.assertEqual(
            result["entrypoints"][0]["registration"]["module_class"],
            "FDefaultGameModuleImpl",
        )
        self.assertEqual(
            result["entrypoints"][0]["registration"]["macro"],
            "IMPLEMENT_PRIMARY_GAME_MODULE",
        )

    def test_module_entry_matches_public_header(self) -> None:
        module_root = self.fixture.root / "HeaderModule"
        rules = write_text(module_root / "HeaderModule.Build.cs", "// rules")
        write_text(
            module_root / "Private" / "HeaderModule.cpp",
            "IMPLEMENT_MODULE(FHeaderModule, HeaderModule)",
        )
        write_text(module_root / "Public" / "HeaderModule.h", "#pragma once")

        result = self.cli(
            "ue_inspect_module_entry.py",
            "--rules",
            str(rules),
        )

        self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(
            result["entrypoints"][0]["header"],
            (module_root / "Public" / "HeaderModule.h").resolve().as_posix(),
        )
        self.assertEqual(
            result["entrypoints"][0]["source"],
            (module_root / "Private" / "HeaderModule.cpp").resolve().as_posix(),
        )

    def test_module_entry_rejects_unsupported_registration_macro(self) -> None:
        module_root = self.fixture.root / "Unsupported"
        rules = write_text(module_root / "Unsupported.Build.cs", "// rules")
        write_text(
            module_root / "Private" / "Unsupported.cpp",
            "IMPLEMENT_GAME_MODULE(FUnsupportedModule, Unsupported)",
        )

        result = self.cli(
            "ue_inspect_module_entry.py",
            "--rules",
            str(rules),
            expected_code=1,
        )

        self.assertEqual(result["entrypoints"], [])
        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "module-entry-registration-not-found",
        )

    def test_module_entry_warns_for_ambiguous_headers(self) -> None:
        module_root = self.fixture.root / "AmbiguousHeader"
        rules = write_text(
            module_root / "AmbiguousHeader.Build.cs",
            "// rules",
        )
        write_text(
            module_root / "Private" / "AmbiguousHeader.cpp",
            "IMPLEMENT_MODULE(FAmbiguousHeaderModule, AmbiguousHeader)",
        )
        write_text(
            module_root / "Private" / "AmbiguousHeader.h",
            "#pragma once",
        )
        write_text(
            module_root / "Public" / "AmbiguousHeader.h",
            "#pragma once",
        )

        result = self.cli(
            "ue_inspect_module_entry.py",
            "--rules",
            str(rules),
        )

        self.assertIsNone(result["entrypoints"][0]["header"])
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "module-entry-header-ambiguous",
        )
