from __future__ import annotations

from unittest.mock import patch

from tests.support import CliTestCase, write_json, write_text
from ue_project_tools.engine import engine_resolution_status, resolve_engine


class ProjectNavigationTests(CliTestCase):
    def test_build_descriptor_finds_project_module_by_name(self) -> None:
        result = self.cli(
            "ue_find_build_descriptor.py",
            "--project",
            str(self.fixture.project),
            "--modulename",
            "SampleGame",
        )
        self.assertEqual(
            result["candidates"],
            [self.fixture.module_rules.resolve().as_posix()],
        )

    def test_build_descriptor_finds_project_plugin_case_insensitively(self) -> None:
        result = self.cli(
            "ue_find_build_descriptor.py",
            "--project",
            str(self.fixture.project),
            "--pluginname",
            "sampleplugin",
        )
        self.assertEqual(
            result["candidates"][0],
            self.fixture.plugin.resolve().as_posix(),
        )

    def test_build_descriptor_does_not_search_engine_modules(self) -> None:
        result = self.cli(
            "ue_find_build_descriptor.py",
            "--project",
            str(self.fixture.project),
            "--modulename",
            "Core",
        )
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertIn(
            "--engine-build-version FILE",
            result["validation"]["problems"][0]["message"],
        )

    def test_build_descriptor_searches_explicit_engine_build_version(self) -> None:
        result = self.cli(
            "ue_find_build_descriptor.py",
            "--project",
            str(self.fixture.project),
            "--modulename",
            "Core",
            "--engine-build-version",
            str(
                self.fixture.engine_root
                / "Engine"
                / "Build"
                / "Build.version"
            ),
        )
        self.assertEqual(len(result["candidates"]), 1)
        self.assertTrue(result["candidates"][0].endswith("/Core/Core.Build.cs"))

    def test_build_descriptor_reports_missing_name(self) -> None:
        result = self.cli(
            "ue_find_build_descriptor.py",
            "--project",
            str(self.fixture.project),
            "--pluginname",
            "MissingPlugin",
        )
        self.assertEqual(result["candidates"], [])
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "build-descriptor-not-found-in-project",
        )

    def test_build_descriptor_reports_missing_name_after_engine_search(self) -> None:
        result = self.cli(
            "ue_find_build_descriptor.py",
            "--project",
            str(self.fixture.project),
            "--pluginname",
            "MissingPlugin",
            "--engine-build-version",
            str(
                self.fixture.engine_root
                / "Engine"
                / "Build"
                / "Build.version"
            ),
            expected_code=1,
        )
        self.assertEqual(result["candidates"], [])
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "build-descriptor-not-found",
        )

    def test_build_descriptor_rejects_missing_engine_build_version(self) -> None:
        result = self.cli(
            "ue_find_build_descriptor.py",
            "--project",
            str(self.fixture.project),
            "--modulename",
            "Core",
            "--engine-build-version",
            str(self.fixture.root / "Missing" / "Build.version"),
            expected_code=2,
        )
        self.assert_request_failure(result, kind="input")

    def test_build_descriptor_reports_ambiguous_name(self) -> None:
        write_text(
            self.fixture.project_root / "Source" / "Core" / "Core.Build.cs",
            "public class Core : ModuleRules {}",
        )
        write_text(
            self.fixture.project_root
            / "Plugins"
            / "DuplicateCore"
            / "Source"
            / "Core"
            / "Core.Build.cs",
            "public class Core : ModuleRules {}",
        )
        result = self.cli(
            "ue_find_build_descriptor.py",
            "--project",
            str(self.fixture.project),
            "--modulename",
            "Core",
            expected_code=1,
        )
        self.assertEqual(len(result["candidates"]), 2)
        self.assertTrue(
            all(path.endswith("/Core/Core.Build.cs") for path in result["candidates"])
        )

    def test_build_descriptor_requires_exactly_one_name_type(self) -> None:
        result = self.cli(
            "ue_find_build_descriptor.py",
            "--project",
            str(self.fixture.project),
            "--modulename",
            "SampleGame",
            "--pluginname",
            "SamplePlugin",
            expected_code=2,
        )
        self.assert_request_failure(result, kind="argument")

    def test_discovery_selects_the_only_project(self) -> None:
        result = self.cli(
            "ue_find_projects.py",
            "--search-root",
            str(self.fixture.project_root),
        )
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["validation"]["status"], "ok")

    def test_discovery_reports_no_project_as_domain_error(self) -> None:
        empty = self.fixture.root / "Empty"
        empty.mkdir()
        result = self.cli(
            "ue_find_projects.py",
            "--search-root",
            str(empty),
            expected_code=1,
        )
        self.assertEqual(result["status"], "not-found")
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["validation"]["status"], "error")

    def test_discovery_refuses_ambiguous_projects(self) -> None:
        write_json(
            self.fixture.project_root / "Second.uproject",
            {"FileVersion": 3},
        )
        result = self.cli(
            "ue_find_projects.py",
            "--search-root",
            str(self.fixture.project_root),
            expected_code=1,
        )
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "project-discovery-ambiguous",
        )

    def test_discovery_skips_generated_directories(self) -> None:
        write_json(
            self.fixture.project_root
            / "Intermediate"
            / "Hidden.uproject",
            {"FileVersion": 3},
        )
        result = self.cli(
            "ue_find_projects.py",
            "--search-root",
            str(self.fixture.project_root),
        )
        self.assertEqual(result["candidate_count"], 1)

    def test_project_descriptor_projects_explicit_navigation_facts(self) -> None:
        result = self.cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(self.fixture.project),
            "--engine-build-version",
            str(self.fixture.engine_root / "Engine" / "Build" / "Build.version"),
        )
        self.assertEqual(result["declared_modules"], ["SampleGame"])
        self.assertEqual(
            result["plugin_declarations"]["enabled"],
            ["SamplePlugin"],
        )
        self.assertEqual(
            result["plugin_declarations"]["disabled"],
            ["DisabledPlugin"],
        )
        self.assertEqual(
            result["plugin_declarations"]["target_allow_list"],
            [],
        )
        self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "declared-plugin-descriptor-missing",
        )
        self.assertEqual(
            result["validation"]["problems"][0]["severity"],
            "info",
        )
        self.assertIn(
            "not enabled",
            result["validation"]["problems"][0]["message"],
        )
        self.assertEqual(
            list(result),
            [
                "schema_version",
                "declared_modules",
                "plugin_declarations",
                "validation",
                "limits",
            ],
        )

    def test_project_descriptor_reports_only_non_empty_target_allow_lists(self) -> None:
        descriptor = {
            "FileVersion": 3,
            "Plugins": [
                {
                    "Name": "ConditionalPlugin",
                    "Enabled": True,
                    "TargetAllowList": ["Editor"],
                    "TargetDenyList": ["Server"],
                },
                {
                    "Name": "DisabledConditionalPlugin",
                    "Enabled": False,
                    "TargetAllowList": ["Server", "Program"],
                },
                {
                    "Name": "EmptyAllowListPlugin",
                    "Enabled": True,
                    "TargetAllowList": [],
                },
                {"Name": "NoAllowListPlugin", "Enabled": True},
            ],
            "CustomField": {"ignored": True},
        }
        project = write_json(
            self.fixture.root / "Extended.uproject",
            descriptor,
        )
        for plugin_name in (
            "ConditionalPlugin",
            "DisabledConditionalPlugin",
            "EmptyAllowListPlugin",
            "NoAllowListPlugin",
        ):
            write_json(
                self.fixture.root
                / "Plugins"
                / plugin_name
                / f"{plugin_name}.uplugin",
                {"FileVersion": 3},
            )
        result = self.cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(project),
            "--engine-build-version",
            str(self.fixture.engine_root / "Engine" / "Build" / "Build.version"),
        )
        declarations = result["plugin_declarations"]
        self.assertEqual(
            declarations["enabled"],
            ["ConditionalPlugin", "EmptyAllowListPlugin", "NoAllowListPlugin"],
        )
        self.assertEqual(
            declarations["disabled"],
            ["DisabledConditionalPlugin"],
        )
        self.assertEqual(
            declarations["target_allow_list"],
            [
                {"name": "ConditionalPlugin", "targets": ["Editor"]},
                {
                    "name": "DisabledConditionalPlugin",
                    "targets": ["Server", "Program"],
                },
            ],
        )

    def test_project_descriptor_rejects_invalid_target_allow_list(self) -> None:
        project = write_json(
            self.fixture.root / "InvalidTargetAllowList.uproject",
            {
                "Plugins": [
                    {
                        "Name": "InvalidPlugin",
                        "Enabled": True,
                        "TargetAllowList": ["Editor", ""],
                    }
                ]
            },
        )
        write_json(
            self.fixture.root
            / "Plugins"
            / "InvalidPlugin"
            / "InvalidPlugin.uplugin",
            {"FileVersion": 3},
        )
        result = self.cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(project),
            "--engine-build-version",
            str(self.fixture.engine_root / "Engine" / "Build" / "Build.version"),
            expected_code=1,
        )
        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "invalid-plugin-target-allow-list",
        )
        self.assertEqual(
            result["plugin_declarations"]["target_allow_list"],
            [],
        )

    def test_project_descriptor_rejects_missing_module_build_rules(self) -> None:
        project = write_json(
            self.fixture.root / "MissingModule.uproject",
            {"Modules": [{"Name": "MissingModule"}]},
        )
        result = self.cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(project),
            "--engine-build-version",
            str(self.fixture.engine_root / "Engine" / "Build" / "Build.version"),
            expected_code=1,
        )
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "project-module-build-rules-missing",
        )

    def test_project_descriptor_rejects_ambiguous_module_build_rules(self) -> None:
        project = write_json(
            self.fixture.root / "AmbiguousModule.uproject",
            {"Modules": [{"Name": "AmbiguousModule"}]},
        )
        write_text(
            self.fixture.root
            / "Source"
            / "AmbiguousModule"
            / "AmbiguousModule.Build.cs",
            "public class AmbiguousModule {}",
        )
        write_text(
            self.fixture.root
            / "Platforms"
            / "Win64"
            / "Source"
            / "AmbiguousModule"
            / "AmbiguousModule.Build.cs",
            "public class AmbiguousModule {}",
        )
        result = self.cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(project),
            "--engine-build-version",
            str(self.fixture.engine_root / "Engine" / "Build" / "Build.version"),
            expected_code=1,
        )
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "project-module-build-rules-ambiguous",
        )

    def test_project_descriptor_rejects_missing_enabled_plugin(self) -> None:
        project = write_json(
            self.fixture.root / "MissingPlugin.uproject",
            {
                "Plugins": [
                    {
                        "Name": "DefinitelyMissingFixturePlugin",
                        "Enabled": True,
                    }
                ]
            },
        )
        result = self.cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(project),
            "--engine-build-version",
            str(self.fixture.engine_root / "Engine" / "Build" / "Build.version"),
            expected_code=1,
        )
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "declared-plugin-descriptor-missing",
        )

    def test_project_descriptor_accepts_plugin_from_explicit_engine(self) -> None:
        plugin_name = "EngineFixturePlugin"
        write_json(
            self.fixture.engine_root
            / "Engine"
            / "Plugins"
            / plugin_name
            / f"{plugin_name}.uplugin",
            {"FileVersion": 3},
        )
        project = write_json(
            self.fixture.root / "EnginePlugin.uproject",
            {"Plugins": [{"Name": plugin_name, "Enabled": True}]},
        )
        result = self.cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(project),
            "--engine-build-version",
            str(self.fixture.engine_root / "Engine" / "Build" / "Build.version"),
        )
        self.assertEqual(result["validation"]["status"], "ok")

    def test_project_descriptor_ignores_engine_association_and_build_contents(
        self,
    ) -> None:
        plugin_name = "TrustedBuildVersionPlugin"
        write_json(
            self.fixture.engine_root
            / "Engine"
            / "Plugins"
            / plugin_name
            / f"{plugin_name}.uplugin",
            {"FileVersion": 3},
        )
        engine_build_version = write_text(
            self.fixture.engine_root / "Engine" / "Build" / "Build.version",
            "not parsed by ue_read_project_descriptor.py",
        )
        project = write_json(
            self.fixture.root / "UnresolvedEnginePlugin.uproject",
            {
                "EngineAssociation": "../NoSuchFixtureEngine",
                "Plugins": [{"Name": plugin_name, "Enabled": True}],
            },
        )
        result = self.cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(project),
            "--engine-build-version",
            str(engine_build_version),
        )
        self.assertEqual(result["validation"]["status"], "ok")

    def test_engine_resolution_reads_build_version(self) -> None:
        result = self.cli(
            "ue_resolve_engine.py",
            "--project",
            str(self.fixture.project),
        )
        self.assertEqual(
            list(result),
            [
                "schema_version",
                "association_raw",
                "engine_root",
                "build_version_file",
                "version",
                "validation",
                "limits",
            ],
        )
        self.assertEqual(result["version"], "5.6.1")
        self.assertEqual(
            result["build_version_file"],
            str(
                self.fixture.engine_root
                / "Engine"
                / "Build"
                / "Build.version"
            ).replace("\\", "/"),
        )
        self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(result["limits"]["analysis_engines"], ["ue-itps"])

    def test_engine_resolution_reports_ambiguous_candidates_as_error(self) -> None:
        candidates = [
            {"root": "D:/UE_5.6_A", "source": "test:first"},
            {"root": "D:/UE_5.6_B", "source": "test:second"},
        ]
        with patch(
            "ue_project_tools.engine.registry_engine_candidates",
            return_value=candidates,
        ):
            result = resolve_engine(self.fixture.project, "5.6")

        self.assertEqual(engine_resolution_status(result), "ambiguous")
        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(
            result["validation"]["problems"][0]["code"],
            "engine-ambiguous",
        )
        self.assertNotIn("status", result)
        self.assertNotIn("resolution_candidates", result)

    def test_engine_resolution_honors_explicit_override(self) -> None:
        alternate = self.fixture.root / "AlternateEngine"
        write_json(
            alternate / "Engine" / "Build" / "Build.version",
            {
                "MajorVersion": 5,
                "MinorVersion": 7,
                "PatchVersion": 0,
            },
        )
        result = self.cli(
            "ue_resolve_engine.py",
            "--project",
            str(self.fixture.project),
            "--engine-root",
            str(alternate),
        )
        self.assertEqual(result["version"], "5.7.0")

    def test_module_inventory_reconciles_rules_and_entrypoint(self) -> None:
        result = self.cli(
            "ue_inspect_modules.py",
            "--project",
            str(self.fixture.project),
        )
        self.assertEqual(result["reconciled_module_count"], 1)
        item = result["items"][0]
        self.assertEqual(item["name"], "SampleGame")
        self.assertEqual(item["build_rules"]["status"], "resolved")
        self.assertGreaterEqual(
            len(item["actual"]["module_entrypoint_candidates"]),
            1,
        )

    def test_target_inventory_finds_game_and_editor_targets(self) -> None:
        result = self.cli(
            "ue_inspect_targets.py",
            "--project",
            str(self.fixture.project),
        )
        by_name = {item["name"]: item for item in result["items"]}
        self.assertEqual(
            set(by_name),
            {"SampleGameTarget", "SampleGameEditorTarget"},
        )
        self.assertEqual(by_name["SampleGameTarget"]["target_type"], "Game")
        self.assertEqual(
            by_name["SampleGameTarget"]["extra_module_names"],
            ["SampleGame"],
        )
        self.assertEqual(
            by_name["SampleGameEditorTarget"]["target_type"],
            "Editor",
        )
        self.assertEqual(
            by_name["SampleGameEditorTarget"]["extra_module_names"],
            ["SampleGame"],
        )
        self.assertNotIn("classification", result)
        self.assertNotIn("is_root_target", by_name["SampleGameTarget"])
        self.assertNotIn("rules_classes", by_name["SampleGameTarget"])
        self.assertNotIn("syntax", by_name["SampleGameTarget"])
        self.assertEqual(
            result["limits"]["analysis_engines"],
            ["ue-itps", "tree-sitter/ast-outline+gdep"],
        )

    def test_target_inventory_reads_nested_client_and_server_declarations(
        self,
    ) -> None:
        write_text(
            self.fixture.project_root / "Source" / "Targets" / "Client.Target.cs",
            """
            using UnrealBuildTool;

            public class ClientTarget : TargetRules
            {
                public ClientTarget(TargetInfo Target) : base(Target)
                {
                    Type = TargetType.Client;
                    ExtraModuleNames.AddRange(new[] { "ClientCore", "Shared" });
                }
            }
            """,
        )
        write_text(
            self.fixture.project_root / "Source" / "Targets" / "Server.Target.cs",
            """
            using UnrealBuildTool;

            public class ServerTarget : TargetRules
            {
                public ServerTarget(TargetInfo Target) : base(Target)
                {
                    Configure();
                }

                private void Configure()
                {
                    Type = TargetType.Server;
                    ExtraModuleNames.Add("ServerCore");
                }
            }
            """,
        )
        result = self.cli(
            "ue_inspect_targets.py",
            "--project",
            str(self.fixture.project),
        )
        by_name = {item["name"]: item for item in result["items"]}
        self.assertEqual(by_name["ClientTarget"]["target_type"], "Client")
        self.assertEqual(
            by_name["ClientTarget"]["extra_module_names"],
            ["ClientCore", "Shared"],
        )
        self.assertEqual(by_name["ServerTarget"]["target_type"], "Server")
        self.assertEqual(
            by_name["ServerTarget"]["extra_module_names"],
            ["ServerCore"],
        )
        problem_codes = {
            problem["code"] for problem in result["validation"]["problems"]
        }
        self.assertNotIn("project-target-root-missing", problem_codes)
        self.assertNotIn("project-target-nested", problem_codes)

    def test_target_inventory_infers_inherited_values_as_info(self) -> None:
        write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGameVariant.Target.cs",
            """
            using UnrealBuildTool;

            public class SampleGameVariantTarget : SampleGameTarget
            {
                public SampleGameVariantTarget(TargetInfo Target) : base(Target)
                {
                    ExtraModuleNames.Add("VariantModule");
                }
            }
            """,
        )
        write_text(
            self.fixture.project_root
            / "Source"
            / "SampleGameDeepVariant.Target.cs",
            """
            using UnrealBuildTool;

            public class SampleGameDeepVariantTarget : SampleGameVariantTarget
            {
                public SampleGameDeepVariantTarget(TargetInfo Target) : base(Target)
                {
                }
            }
            """,
        )
        result = self.cli(
            "ue_inspect_targets.py",
            "--project",
            str(self.fixture.project),
        )
        by_name = {item["name"]: item for item in result["items"]}
        variant = by_name["SampleGameVariantTarget"]
        self.assertEqual(variant["target_type"], "Game")
        self.assertEqual(
            variant["extra_module_names"],
            ["SampleGame", "VariantModule"],
        )
        deep_variant = by_name["SampleGameDeepVariantTarget"]
        self.assertEqual(deep_variant["target_type"], "Game")
        self.assertEqual(
            deep_variant["extra_module_names"],
            ["SampleGame", "VariantModule"],
        )
        inheritance_info = {
            problem["inheritance_chain"][0]: problem
            for problem in result["validation"]["problems"]
            if problem["code"] == "target-values-inherited"
        }
        variant_info = inheritance_info["SampleGameVariantTarget"]
        self.assertEqual(variant_info["severity"], "info")
        self.assertEqual(
            variant_info["inheritance_chain"],
            ["SampleGameVariantTarget", "SampleGameTarget"],
        )
        self.assertEqual(
            variant_info["inferred_fields"],
            ["target_type", "extra_module_names"],
        )
        deep_info = inheritance_info["SampleGameDeepVariantTarget"]
        self.assertEqual(
            deep_info["inheritance_chain"],
            [
                "SampleGameDeepVariantTarget",
                "SampleGameVariantTarget",
                "SampleGameTarget",
            ],
        )
        self.assertNotIn("target_name", variant_info)
        self.assertNotIn("base_class", variant_info)
        self.assertEqual(result["validation"]["status"], "ok")

    def test_target_inventory_warns_for_dynamic_declarations(self) -> None:
        write_text(
            self.fixture.project_root / "Source" / "Dynamic.Target.cs",
            """
            using UnrealBuildTool;

            public class DynamicTarget : TargetRules
            {
                public DynamicTarget(TargetInfo Target) : base(Target)
                {
                    Type = ResolveType();
                    ExtraModuleNames.Add(GetModuleName());
                    ExtraModuleNames.AddRange(
                        new string[] { "Known", GetModuleName() }
                    );
                }

                private TargetType ResolveType() => TargetType.Program;
                private string GetModuleName() => "DynamicModule";
            }
            """,
        )
        result = self.cli(
            "ue_inspect_targets.py",
            "--project",
            str(self.fixture.project),
        )
        dynamic = next(
            item for item in result["items"] if item["name"] == "DynamicTarget"
        )
        self.assertIsNone(dynamic["target_type"])
        self.assertEqual(dynamic["extra_module_names"], [])
        problem_codes = [
            problem["code"]
            for problem in result["validation"]["problems"]
            if problem.get("path") == dynamic["path"]
        ]
        self.assertEqual(
            problem_codes,
            [
                "target-type-unresolved",
                "target-extra-modules-unresolved",
                "target-extra-modules-unresolved",
            ],
        )

    def test_target_inventory_reports_syntax_errors_with_path(self) -> None:
        broken = write_text(
            self.fixture.project_root / "Source" / "Broken.Target.cs",
            """
            using UnrealBuildTool;

            public class BrokenTarget : TargetRules
            {
            """,
        )
        result = self.cli(
            "ue_inspect_targets.py",
            "--project",
            str(self.fixture.project),
            expected_code=1,
        )
        syntax_problem = next(
            problem
            for problem in result["validation"]["problems"]
            if problem["code"] == "csharp-syntax-tree-errors"
        )
        self.assertEqual(
            syntax_problem["path"],
            str(broken.resolve()).replace("\\", "/"),
        )
        self.assertGreater(syntax_problem["count"], 0)

    def test_project_source_inventory_groups_project_and_plugin_modules(self) -> None:
        result = self.cli(
            "ue_list_project_cxx_sources.py",
            "--project",
            str(self.fixture.project),
        )
        self.assertEqual(result["module_count"], 2)
        by_name = {item["module"]: item for item in result["modules"]}
        self.assertEqual(set(by_name), {"SampleGame", "SamplePlugin"})
        self.assertIn(
            "Source/SampleGame/Public/SampleActor.h",
            by_name["SampleGame"]["headers"]["public"],
        )
        self.assertEqual(by_name["SamplePlugin"]["plugin"], "SamplePlugin")

    def test_module_source_inventory_scans_only_selected_module(self) -> None:
        nested_root = self.fixture.module_rules.parent / "Nested"
        write_text(nested_root / "Nested.Build.cs", "// nested rules")
        write_text(nested_root / "Private" / "Nested.cpp", "// nested source")
        write_text(
            self.fixture.module_rules.parent / "Public" / "Ignored.generated.h",
            "#pragma once",
        )

        result = self.cli(
            "ue_list_module_cxx_sources.py",
            "--rules",
            str(self.fixture.module_rules),
        )

        self.assertEqual(result["schema_version"], "ue_list_module_cxx_sources")
        self.assertEqual(
            set(result),
            {"schema_version", "headers", "cpp", "validation", "limits"},
        )
        self.assertIn(
            "Source/SampleGame/Public/SampleActor.h",
            result["headers"],
        )
        self.assertIn(
            "Source/SampleGame/Private/SampleActor.cpp",
            result["cpp"],
        )
        all_paths = [*result["headers"], *result["cpp"]]
        self.assertFalse(any("Nested" in path for path in all_paths))
        self.assertFalse(any("generated" in path.casefold() for path in all_paths))
        self.assertEqual(result["headers"], sorted(result["headers"], key=str.casefold))
        self.assertEqual(result["cpp"], sorted(result["cpp"], key=str.casefold))

    def test_module_source_inventory_scans_selected_plugin_module(self) -> None:
        result = self.cli(
            "ue_list_module_cxx_sources.py",
            "--rules",
            str(self.fixture.plugin_rules),
        )

        self.assertEqual(
            result["headers"],
            [],
        )
        self.assertEqual(
            result["cpp"],
            [
                "Plugins/SamplePlugin/Source/SamplePlugin/Private/"
                "SamplePluginModule.cpp"
            ],
        )

    def test_plugin_resolution_keeps_enabled_and_disabled_declarations(self) -> None:
        result = self.cli(
            "ue_resolve_plugins.py",
            "--project",
            str(self.fixture.project),
        )
        self.assertEqual(result["count"], 2)
        by_name = {item["name"]: item for item in result["items"]}
        self.assertTrue(by_name["SamplePlugin"]["declared_enabled"])
        self.assertEqual(by_name["SamplePlugin"]["origin"], "project")
        self.assertFalse(by_name["DisabledPlugin"]["declared_enabled"])
        self.assertIsNone(by_name["DisabledPlugin"]["descriptor"])

    def test_plugin_filter_is_case_insensitive(self) -> None:
        result = self.cli(
            "ue_resolve_plugins.py",
            "--project",
            str(self.fixture.project),
            "--plugin-name",
            "sampleplugin",
        )
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["name"], "SamplePlugin")

    def test_path_classification_reports_roles_without_deletion_claims(self) -> None:
        result = self.cli(
            "ue_classify_project_paths.py",
            "--project",
            str(self.fixture.project),
        )
        path_items = [
            *result["project_directories"],
            *result["build_and_ide_paths"],
            *result["cache_and_local_state_paths"],
        ]
        by_path = {
            item["project_relative_path"]: item
            for item in path_items
        }
        self.assertEqual(by_path["Content"]["role"], "content")
        self.assertEqual(by_path["Source"]["actual_type"], "directory")
        self.assertEqual(
            result["unclassified_root_directories"][0]["project_relative_path"],
            "Reports",
        )
        self.assertTrue(
            any("deletion" in boundary.lower() for boundary in result["limits"]["boundaries"])
        )
