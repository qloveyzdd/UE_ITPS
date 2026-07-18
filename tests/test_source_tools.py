from __future__ import annotations

import json
from pathlib import Path
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
            plugin = Path(temporary_directory) / "Fixture.uplugin"
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

            result = read_plugin_descriptor(plugin)

        self.assertEqual(result["schema_version"], "ue-itps.plugin-descriptor.v1")
        self.assertEqual(result["syntax_extensions"], ["trailing-commas"])
        self.assertEqual(result["fields"]["FriendlyName"], "Fixture")
        self.assertEqual(result["unmodeled_top_level_fields"], ["CustomAuthorityField"])
        module = result["modules"][0]
        self.assertEqual(module["loading_phase"], "PostEngineInit")
        self.assertEqual(module["restrictions"]["PlatformAllowList"], ["Win64"])
        self.assertEqual(module["restrictions"]["TargetDenyList"], ["Server"])
        self.assertEqual(result["plugin_dependencies"][0]["name"], "GameplayTags")
        self.assertNotIn("module_inventory", result)

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
