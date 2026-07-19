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

from ue_project_tools.module_entry import inspect_module_entry
from ue_project_tools.plugin_descriptor import read_plugin_descriptor
from ue_project_tools.plugin_modules import inspect_plugin_modules
from ue_project_tools.rule_source import inspect_module_rules, inspect_target_rules


class SourceToolsTests(unittest.TestCase):
    def test_target_rules_are_a_standalone_source_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory) / "Fixture.Target.cs"
            target.write_text(
                """
public class FixtureTarget : TargetRules
{
    public FixtureTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        ExtraModuleNames.AddRange(new string[] { "Fixture", GetEditorModule() });
        ApplyShared(Target);
    }

    static void ApplyShared(TargetRules Target)
    {
        if (Target.bBuildEditor)
        {
            Target.GlobalDefinitions.Add("WITH_EDITOR_CODE=1");
        }
        else
        {
            Target.GlobalDefinitions.Remove("WITH_EDITOR_CODE=1");
        }
    }
}
""",
                encoding="utf-8",
            )

            result = inspect_target_rules(target)

        self.assertEqual(result["schema_version"], "ue-itps.target-rules-source.v1")
        self.assertEqual(result["validation"]["status"], "ok")
        rules_class = result["rules_classes"][0]
        self.assertEqual(rules_class["name"], "FixtureTarget")
        self.assertEqual(rules_class["base_types"], ["TargetRules"])
        self.assertEqual(
            rules_class["same_file_calls"],
            [
                {
                    "caller": "FixtureTarget",
                    "callee": "ApplyShared",
                    "location": rules_class["same_file_calls"][0]["location"],
                }
            ],
        )
        constructor = next(
            method for method in rules_class["methods"] if method["is_constructor"]
        )
        add_range = next(
            operation
            for operation in constructor["operations"]
            if operation.get("callee") == "ExtraModuleNames.AddRange"
        )
        self.assertEqual(add_range["evaluation"]["status"], "partial")
        self.assertEqual(add_range["evaluation"]["literal_values"], ["Fixture"])
        helper = next(
            method for method in rules_class["methods"] if method["name"] == "ApplyShared"
        )
        branches = {
            operation["conditions"][0]["branch"]
            for operation in helper["operations"]
            if operation.get("callee", "").endswith((".Add", ".Remove"))
        }
        self.assertEqual(branches, {"then", "else"})
        self.assertTrue(
            all(
                operation["conditions"][0]["expression"] == "Target.bBuildEditor"
                for operation in helper["operations"]
                if operation.get("callee", "").endswith((".Add", ".Remove"))
            )
        )

    def test_module_rules_classify_declared_operations_without_effective_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            rules = Path(temporary_directory) / "Fixture.Build.cs"
            rules.write_text(
                """
public class Fixture : ModuleRules
{
    public Fixture(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        bEnforceIWYU = true;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "Engine" });
        ConfigureEditor(Target);
    }

    void ConfigureEditor(ReadOnlyTargetRules Target)
    {
        if (Target.bBuildEditor)
            PrivateDependencyModuleNames.Add(EditorModuleName);
    }
}
""",
                encoding="utf-8",
            )

            result = inspect_module_rules(rules)

        self.assertEqual(result["schema_version"], "ue-itps.module-rules-source.v1")
        rules_class = result["rules_classes"][0]
        operations = [
            operation
            for method in rules_class["methods"]
            for operation in method["operations"]
        ]
        public_dependencies = next(
            operation
            for operation in operations
            if operation.get("rule", {}).get("kind") == "public_dependency"
        )
        self.assertEqual(
            public_dependencies["evaluation"],
            {"status": "literal", "literal_values": ["Core", "Engine"]},
        )
        private_dependencies = next(
            operation
            for operation in operations
            if operation.get("rule", {}).get("kind") == "private_dependency"
        )
        self.assertEqual(private_dependencies["evaluation"]["status"], "unresolved")
        self.assertEqual(
            private_dependencies["conditions"][0]["expression"],
            "Target.bBuildEditor",
        )
        self.assertIn(
            "Static declarations are not effective UBT build results.",
            result["limits"]["boundaries"],
        )

    def test_plugin_descriptor_is_read_one_file_at_a_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            plugin = root / "Fixture.uplugin"
            plugin.write_text(
                """
{
  "FileVersion": 3,
  "Version": 7,
  "FriendlyName": "Fixture",
  "CustomAuthorityField": "preserve",
  "Modules": [
    {
      "Name": "FixtureRuntime",
      "Type": "Runtime",
      "LoadingPhase": "PostEngineInit",
      "PlatformAllowList": ["Win64"],
      "TargetDenyList": ["Server"]
    }
  ],
  "Plugins": [
    {"Name": "GameplayTags", "Enabled": true, "Optional": true}
  ],
}
""",
                encoding="utf-8",
            )
            rules = root / "Source" / "Nested" / "FixtureRuntime.Build.cs"
            rules.parent.mkdir(parents=True)
            rules.write_text(
                "public class FixtureRuntime : ModuleRules {}",
                encoding="utf-8",
            )

            result = read_plugin_descriptor(plugin)

        self.assertEqual(result["schema_version"], "ue-itps.plugin-descriptor.v2")
        self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(result["descriptor_fields"]["FriendlyName"], "Fixture")
        self.assertEqual(result["unmodeled_top_level_fields"], ["CustomAuthorityField"])
        module = result["modules"][0]
        self.assertEqual(module["loading_phase"], "PostEngineInit")
        self.assertEqual(module["restrictions"]["PlatformAllowList"], ["Win64"])
        self.assertEqual(module["restrictions"]["TargetDenyList"], ["Server"])
        self.assertEqual(module["build_rules"]["status"], "resolved")
        self.assertEqual(module["build_rules"]["candidates"][0]["path"], rules.resolve().as_posix())
        self.assertFalse(module["build_rules"]["candidates"][0]["conventional"])
        self.assertEqual(result["plugin_dependencies"][0]["name"], "GameplayTags")
        self.assertEqual(
            result["plugin_dependencies"][0]["additional_fields"],
            {"Optional": True},
        )
        self.assertNotIn("localization_targets", result)
        self.assertNotIn("build_steps", result)
        self.assertNotIn("module_inventory", result)

    def test_plugin_descriptor_emits_declared_localization_and_build_steps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            plugin = Path(temporary_directory) / "Fixture.uplugin"
            plugin.write_text(
                json.dumps(
                    {
                        "FileVersion": 3,
                        "LocalizationTargets": [],
                        "PreBuildSteps": {"Win64": ["Prepare.bat"]},
                    }
                ),
                encoding="utf-8",
            )

            result = read_plugin_descriptor(plugin)

        self.assertEqual(result["localization_targets"], [])
        self.assertEqual(
            result["build_steps"],
            {"PreBuildSteps": {"Win64": ["Prepare.bat"]}},
        )

    def test_plugin_descriptor_reports_all_duplicate_fields_with_pointers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            plugin = Path(temporary_directory) / "Fixture.uplugin"
            plugin.write_text(
                """
{
  "FileVersion": 3,
  "FriendlyName": "First",
  "FriendlyName": "Last",
  "Plugins": [],
  "Plugins": [
    {
      "Name": "Dependency",
      "Enabled": true,
      "Optional": true,
      "Optional": false
    }
  ]
}
""",
                encoding="utf-8",
            )

            result = read_plugin_descriptor(plugin)

        self.assertEqual(result["validation"]["status"], "error")
        duplicate_problems = [
            problem
            for problem in result["validation"]["problems"]
            if problem["code"] == "duplicate-plugin-descriptor-field"
        ]
        duplicates = {
            item["descriptor_pointer"]: item for item in duplicate_problems
        }
        self.assertEqual(
            set(duplicates),
            {"/FriendlyName", "/Plugins", "/Plugins/0/Optional"},
        )
        self.assertTrue(
            all(item["occurrence_count"] == 2 for item in duplicates.values())
        )
        self.assertEqual(result["descriptor_fields"]["FriendlyName"], "Last")
        self.assertEqual(result["plugin_dependencies"][0]["name"], "Dependency")
        self.assertEqual(len(duplicate_problems), 3)
        self.assertTrue(
            all(problem["severity"] == "error" for problem in duplicate_problems)
        )

    def test_plugin_descriptor_keeps_unclosed_block_comment_tolerance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            plugin = Path(temporary_directory) / "Fixture.uplugin"
            plugin.write_text(
                '{"FileVersion": 3} /* intentionally left open',
                encoding="utf-8",
            )

            result = read_plugin_descriptor(plugin)

        self.assertEqual(result["validation"]["status"], "ok")

    def test_plugin_descriptor_validates_ue_enums_and_duplicate_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            plugin = root / "Fixture.uplugin"
            plugin.write_text(
                json.dumps(
                    {
                        "FileVersion": 3,
                        "Modules": [
                            {
                                "Name": "FixtureRuntime",
                                "Type": "NotAHostType",
                                "LoadingPhase": "NotAPhase",
                                "TargetAllowList": ["Game", "NotATarget"],
                            },
                            {
                                "Name": "fixtureruntime",
                                "Type": "Runtime",
                            },
                        ],
                        "Plugins": [
                            {"Name": "Dependency", "Enabled": True},
                            {
                                "Name": "dependency",
                                "Enabled": True,
                                "TargetConfigurationAllowList": ["NotAConfig"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            rules = root / "Platforms" / "Win64" / "Source" / "Nested" / "FixtureRuntime.Build.cs"
            rules.parent.mkdir(parents=True)
            rules.write_text(
                "public class FixtureRuntime : ModuleRules {}",
                encoding="utf-8",
            )

            result = read_plugin_descriptor(plugin)

        problems = result["validation"]["problems"]
        codes = {problem["code"] for problem in problems}
        self.assertIn("invalid-plugin-module-enum-value", codes)
        self.assertIn("invalid-plugin-dependency-enum-value", codes)
        self.assertIn("plugin-module-declaration-duplicate", codes)
        self.assertIn("plugin-dependency-declaration-duplicate", codes)
        module_duplicate = next(
            problem
            for problem in problems
            if problem["code"] == "plugin-module-declaration-duplicate"
        )
        self.assertEqual(
            module_duplicate["descriptor_pointers"],
            ["/Modules/0", "/Modules/1"],
        )
        self.assertTrue(
            all(
                module["build_rules"]["status"] == "duplicate-declaration"
                for module in result["modules"]
            )
        )

    def test_plugin_descriptor_reconciles_missing_ambiguous_and_unlisted_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            plugin = root / "Fixture.uplugin"
            plugin.write_text(
                json.dumps(
                    {
                        "FileVersion": 3,
                        "Modules": [
                            {"Name": "Missing", "Type": "Runtime"},
                            {"Name": "Ambiguous", "Type": "runtime"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            for relative in (
                "Source/First/Ambiguous.Build.cs",
                "Platforms/Win64/Source/Second/Ambiguous.Build.cs",
                "Source/Nested/Undeclared.Build.cs",
            ):
                rules = root / relative
                rules.parent.mkdir(parents=True, exist_ok=True)
                rules.write_text("public class Rules {}", encoding="utf-8")

            result = read_plugin_descriptor(plugin)

        codes = {problem["code"] for problem in result["validation"]["problems"]}
        self.assertIn("plugin-module-build-rules-missing", codes)
        self.assertIn("plugin-module-build-rules-ambiguous", codes)
        self.assertIn("plugin-module-build-rules-unlisted", codes)
        self.assertEqual(
            result["modules"][1]["build_rules"]["status"],
            "ambiguous",
        )
        self.assertNotIn("unlisted_build_rules", result)
        unlisted_problem = next(
            problem
            for problem in result["validation"]["problems"]
            if problem["code"] == "plugin-module-build-rules-unlisted"
        )
        self.assertEqual(unlisted_problem["module_name"], "Undeclared")

    def test_plugin_descriptor_rejects_invalid_input_and_file_version_type(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            wrong_suffix = root / "Fixture.json"
            wrong_suffix.write_text('{"FileVersion": 3}', encoding="utf-8")
            plugin = root / "Fixture.uplugin"
            plugin.write_text('{"FileVersion": true}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Expected a .uplugin file"):
                read_plugin_descriptor(wrong_suffix)
            result = read_plugin_descriptor(plugin)

        self.assertEqual(result["validation"]["status"], "error")
        self.assertIn(
            "missing-or-invalid-plugin-file-version",
            {problem["code"] for problem in result["validation"]["problems"]},
        )

    def test_plugin_descriptor_cli_uses_zero_one_and_two_exit_codes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            valid = root / "Valid.uplugin"
            valid.write_text('{"FileVersion": 3}', encoding="utf-8")
            invalid = root / "Invalid.uplugin"
            invalid.write_text('{"FileVersion": false}', encoding="utf-8")
            wrong_suffix = root / "Wrong.json"
            wrong_suffix.write_text('{"FileVersion": 3}', encoding="utf-8")

            return_codes = []
            for descriptor in (valid, invalid, wrong_suffix):
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(TOOLS_ROOT / "ue_read_plugin_descriptor.py"),
                        "--plugin",
                        str(descriptor),
                    ],
                    cwd=REPOSITORY_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )
                return_codes.append(completed.returncode)

        self.assertEqual(return_codes, [0, 1, 2])

    def test_plugin_module_navigation_does_not_expand_source_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            plugin = root / "Fixture.uplugin"
            plugin.write_text(
                json.dumps(
                    {
                        "FileVersion": 3,
                        "Modules": [{"Name": "FixtureRuntime", "Type": "Runtime"}],
                    }
                ),
                encoding="utf-8",
            )
            module_root = root / "Source" / "FixtureRuntime"
            module_root.mkdir(parents=True)
            rules = module_root / "FixtureRuntime.Build.cs"
            rules.write_text("public class FixtureRuntime : ModuleRules {}", encoding="utf-8")
            entry = module_root / "Private" / "FixtureRuntimeModule.cpp"
            entry.parent.mkdir()
            entry.write_text(
                "IMPLEMENT_MODULE(FFixtureRuntimeModule, FixtureRuntime)",
                encoding="utf-8",
            )

            result = inspect_plugin_modules(plugin)

        self.assertEqual(result["schema_version"], "ue-itps.plugin-modules.v1")
        self.assertEqual(result["validation"]["status"], "ok")
        item = result["items"][0]
        self.assertEqual(item["build_rules"]["status"], "resolved")
        self.assertEqual(item["build_rules"]["candidates"][0]["path"], rules.resolve().as_posix())
        self.assertEqual(item["entrypoints"]["status"], "resolved")
        self.assertEqual(item["entrypoints"]["candidates"][0]["path"], entry.resolve().as_posix())
        self.assertNotIn("source_facts", json.dumps(result))
        self.assertNotIn("rules_classes", json.dumps(result))

    def test_module_entry_follows_only_lifecycle_helpers_and_bound_callbacks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            rules = root / "Fixture.Build.cs"
            rules.write_text("public class Fixture : ModuleRules {}", encoding="utf-8")
            header = root / "FixtureModule.h"
            header.write_text(
                """
class FFixtureModule : public IModuleInterface
{
public:
    virtual void StartupModule() override;
    virtual void ShutdownModule() override;
    void BindEditorDelegates();
    void OnBeginPIE(bool bSimulating);
    void UnrelatedMethod();
};
""",
                encoding="utf-8",
            )
            source = root / "FixtureModule.cpp"
            source.write_text(
                """
void FFixtureModule::StartupModule()
{
    BindEditorDelegates();
}

void FFixtureModule::BindEditorDelegates()
{
    if (!IsRunningGame())
        FEditorDelegates::BeginPIE.AddRaw(this, &FFixtureModule::OnBeginPIE);
}

void FFixtureModule::OnBeginPIE(bool bSimulating)
{
    ExperienceManager->OnPlayInEditorBegun();
}

void FFixtureModule::ShutdownModule()
{
    FEditorDelegates::BeginPIE.RemoveAll(this);
}

void FFixtureModule::UnrelatedMethod()
{
    OtherDelegate.AddRaw(this, &FFixtureModule::OnBeginPIE);
}

IMPLEMENT_MODULE(FFixtureModule, Fixture)
""",
                encoding="utf-8",
            )

            result = inspect_module_entry(rules)

        self.assertEqual(result["schema_version"], "ue-itps.module-entry-source.v1")
        self.assertEqual(result["validation"]["status"], "ok")
        module_class = result["module_classes"][0]
        self.assertEqual(module_class["name"], "FFixtureModule")
        phases = {
            item["method"]: item["roots"]
            for item in module_class["lifecycle_reachability"]
        }
        self.assertEqual(phases["BindEditorDelegates"], ["StartupModule"])
        self.assertEqual(phases["OnBeginPIE"], ["bound-callback"])
        self.assertNotIn("UnrelatedMethod", phases)
        registrations = [
            operation
            for operation in module_class["delegate_operations"]
            if operation["action"] == "register"
        ]
        self.assertEqual(len(registrations), 1)
        self.assertEqual(registrations[0]["delegate_source"], "FEditorDelegates::BeginPIE")
        self.assertEqual(registrations[0]["binding_api"], "AddRaw")
        self.assertEqual(registrations[0]["callback_target"], "FFixtureModule::OnBeginPIE")
        self.assertEqual(registrations[0]["conditions"][0]["expression"], "!IsRunningGame()")
        unregister = next(
            operation
            for operation in module_class["delegate_operations"]
            if operation["action"] == "unregister"
        )
        self.assertEqual(unregister["binding_api"], "RemoveAll")


if __name__ == "__main__":
    unittest.main()
