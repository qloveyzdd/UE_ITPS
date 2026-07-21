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
from ue_project_tools.rule_source import inspect_module_rules, inspect_target_rules


class SourceToolsTests(unittest.TestCase):
    def test_target_rules_project_reachable_setting_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory) / "Fixture.Target.cs"
            target.write_text(
                """
public class FixtureTarget : TargetRules
{
    private static bool bClassState = false;
    private static List<string> LocalCache = new List<string>();

    public FixtureTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        ExtraModuleNames.AddRange(new string[] { "Fixture" });
        ApplyShared(Target);
    }

    static void ApplyShared(TargetRules Target)
    {
        bool bLocalState = false;
        if (Target.bBuildEditor)
        {
            Target.GlobalDefinitions.Add("WITH_EDITOR_CODE=1");
            Target.bUseLoggingInShipping = true;
            bLocalState = true;
            ApplyExternalRules(Target);
        }
        else
        {
            Target.GlobalDefinitions.Remove("WITH_EDITOR_CODE=1");
        }

        string[] PluginNames = new string[] { "FixturePlugin" };
        foreach (string PluginName in PluginNames)
        {
            if (PluginName != null)
            {
                Target.DisablePlugins.Add(PluginName);
            }
        }

        Dictionary<string, List<string>> LocalMap = new Dictionary<string, List<string>>();
        LocalMap["Fixture"].Add("IgnoredLocalMutation");
        JsonObject DeferredObject;
        DeferredObject = JsonObject.Read("IgnoredDeferredLocal");
        bClassState = true;
        LocalCache.Add("IgnoredClassFieldMutation");
    }

    static void Unused(TargetRules Target)
    {
        Target.EnablePlugins.Add("UnusedPlugin");
    }
}
""",
                encoding="utf-8",
            )

            result = inspect_target_rules(target)

        self.assertEqual(
            result["schema_version"], "ue-itps.target-rule-relations.v1"
        )
        self.assertEqual(result["validation"]["status"], "ok")
        rules_class = result["rules_classes"][0]
        self.assertEqual(rules_class["name"], "FixtureTarget")
        self.assertEqual(
            list(rules_class),
            [
                "name",
                "inheritance",
                "declared_mutations",
                "unclassified_mutations",
                "unresolved_effect_calls",
            ],
        )
        self.assertEqual(
            rules_class["inheritance"],
            {"kind": "confirmed", "base_types": ["TargetRules"]},
        )
        mutations = rules_class["declared_mutations"]
        self.assertEqual(
            [(item["setting"], item["operation"]) for item in mutations],
            [
                ("Type", "set"),
                ("ExtraModuleNames", "add"),
                ("GlobalDefinitions", "add"),
                ("bUseLoggingInShipping", "set"),
                ("GlobalDefinitions", "remove"),
                ("DisablePlugins", "add"),
            ],
        )
        self.assertEqual(
            mutations[0]["operand"],
            {"kind": "symbol", "references": ["TargetType.Game"]},
        )
        self.assertEqual(
            mutations[1]["operand"],
            {
                "kind": "literal",
                "reference_kind": "module",
                "references": ["Fixture"],
            },
        )
        self.assertEqual(
            mutations[3]["operand"], {"kind": "literal", "values": [True]}
        )
        self.assertEqual(mutations[0]["source"]["method"], "FixtureTarget")
        self.assertEqual(mutations[2]["source"]["method"], "ApplyShared")
        branches = {
            mutation["applicability"]["controls"][0]["branch"]
            for mutation in mutations
            if mutation["setting"] == "GlobalDefinitions"
        }
        self.assertEqual(branches, {"then", "else"})
        self.assertTrue(
            all(
                mutation["applicability"]["controls"][0]["expression"]
                == "Target.bBuildEditor"
                for mutation in mutations
                if mutation["setting"] == "GlobalDefinitions"
            )
        )
        plugin_mutation = mutations[-1]
        self.assertEqual(
            plugin_mutation["applicability"]["controls"],
            [
                {
                    "kind": "foreach",
                    "expression": "string PluginName in PluginNames",
                },
                {
                    "kind": "if",
                    "expression": "PluginName != null",
                    "branch": "then",
                },
            ],
        )
        self.assertEqual(rules_class["unclassified_mutations"], [])
        self.assertEqual(
            rules_class["unresolved_effect_calls"],
            [
                {
                    "callee": "ApplyExternalRules",
                    "arguments": ["Target"],
                    "applicability": {
                        "kind": "conditional",
                        "controls": [
                            {
                                "kind": "if",
                                "expression": "Target.bBuildEditor",
                                "branch": "then",
                            }
                        ],
                    },
                    "source": {
                        "method": "ApplyShared",
                        "line": rules_class["unresolved_effect_calls"][0][
                            "source"
                        ]["line"],
                    },
                }
            ],
        )
        rendered = json.dumps(rules_class)
        self.assertNotIn("UnusedPlugin", rendered)
        self.assertNotIn("IgnoredLocalMutation", rendered)
        self.assertNotIn("IgnoredDeferredLocal", rendered)
        self.assertNotIn("IgnoredClassFieldMutation", rendered)
        self.assertNotIn('"conditions"', rendered)
        self.assertNotIn('"control_path"', rendered)
        self.assertNotIn('"related_symbols"', rendered)
        self.assertTrue(
            all(
                list(mutation["source"]) == ["method", "line"]
                for mutation in mutations
            )
        )

    def test_target_rules_report_filename_candidate_with_unresolved_base(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory) / "Derived.Target.cs"
            target.write_text(
                """
public class DerivedTarget : SharedTarget
{
    public DerivedTarget(TargetInfo Target) : base(Target)
    {
        CustomConfig = "EOS";
    }
}
""",
                encoding="utf-8",
            )

            result = inspect_target_rules(target)

        self.assertEqual(result["validation"]["status"], "warning")
        self.assertEqual(
            [problem["code"] for problem in result["validation"]["problems"]],
            ["target-rules-base-unresolved"],
        )
        rules_class = result["rules_classes"][0]
        self.assertEqual(rules_class["name"], "DerivedTarget")
        self.assertEqual(
            rules_class["inheritance"],
            {"kind": "unresolved", "base_types": ["SharedTarget"]},
        )
        self.assertEqual(
            rules_class["declared_mutations"],
            [
                {
                    "setting": "CustomConfig",
                    "operation": "set",
                    "operand": {"kind": "literal", "references": ["EOS"]},
                    "applicability": {"kind": "direct"},
                    "source": {
                        "method": "DerivedTarget",
                        "line": rules_class["declared_mutations"][0]["source"][
                            "line"
                        ],
                    },
                }
            ],
        )
        self.assertTrue(result["limits"]["boundaries"])

    def test_target_rules_emit_ordered_structured_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            target = Path(temporary_directory) / "Controls.Target.cs"
            target.write_text(
                """
public class ControlsTarget : TargetRules
{
    public ControlsTarget(TargetInfo Target) : base(Target)
    {
        ApplyControls(this);
    }

    static void ApplyControls(TargetRules Rules)
    {
#if WITH_TARGET_FEATURE
        foreach (string Name in Rules.ExtraModuleNames)
        {
            if (Rules.bBuildEditor)
                Rules.GlobalDefinitions.Add("EDITOR=1");
            else if (Rules.Type == TargetType.Server)
                Rules.GlobalDefinitions.Add("SERVER=1");
        }
#endif

        for (int Index = 0; Index < 2; ++Index)
        {
            while (Rules.bCompileAgainstEngine)
            {
                Rules.GlobalDefinitions.Add("LOOP=1");
                break;
            }
        }

        switch (Rules.Configuration)
        {
            case UnrealTargetConfiguration.Shipping:
                Rules.GlobalDefinitions.Add("CASE=1");
                break;
            default:
                Rules.GlobalDefinitions.Add("DEFAULT=1");
                break;
        }

        try
        {
        }
        catch (BuildException Error) when (Rules.bBuildEditor)
        {
            Rules.GlobalDefinitions.Add("CATCH=1");
        }

        if (Rules.bBuildEditor && (Rules.bUseLoggingInShipping = true))
        {
        }

        if (Rules.bBuildEditor
            ? (Rules.bAllowGeneratedIniWhenCooked = false)
            : false)
        {
        }
    }
}
""",
                encoding="utf-8",
            )

            result = inspect_target_rules(target)

        mutations = result["rules_classes"][0]["declared_mutations"]

        def definition(name: str) -> dict[str, object]:
            return next(
                item
                for item in mutations
                if item.get("operand", {}).get("references") == [name]
            )

        editor_controls = definition("EDITOR=1")["applicability"]["controls"]
        self.assertEqual(
            [item["kind"] for item in editor_controls],
            ["preprocessor", "foreach", "if"],
        )
        self.assertEqual(editor_controls[0]["expression"], "WITH_TARGET_FEATURE")
        self.assertEqual(
            editor_controls[1]["expression"],
            "string Name in Rules.ExtraModuleNames",
        )

        server_controls = definition("SERVER=1")["applicability"]["controls"]
        self.assertEqual(
            [(item["kind"], item.get("branch")) for item in server_controls],
            [
                ("preprocessor", "then"),
                ("foreach", None),
                ("if", "else"),
                ("if", "then"),
            ],
        )

        loop_controls = definition("LOOP=1")["applicability"]["controls"]
        self.assertEqual(
            [item["kind"] for item in loop_controls], ["for", "while"]
        )
        self.assertIn("Index < 2", loop_controls[0]["expression"])
        self.assertEqual(
            loop_controls[1]["expression"], "Rules.bCompileAgainstEngine"
        )

        case_controls = definition("CASE=1")["applicability"]["controls"]
        self.assertEqual(
            case_controls,
            [
                {"kind": "switch", "expression": "Rules.Configuration"},
                {
                    "kind": "case",
                    "expression": "UnrealTargetConfiguration.Shipping",
                },
            ],
        )
        self.assertEqual(
            definition("DEFAULT=1")["applicability"]["controls"],
            [
                {"kind": "switch", "expression": "Rules.Configuration"},
                {"kind": "case"},
            ],
        )
        self.assertEqual(
            definition("CATCH=1")["applicability"]["controls"],
            [{"kind": "catch", "expression": "Rules.bBuildEditor"}],
        )

        logging = next(
            item for item in mutations if item["setting"] == "bUseLoggingInShipping"
        )
        self.assertEqual(
            logging["applicability"]["controls"],
            [{"kind": "short_circuit", "expression": "Rules.bBuildEditor"}],
        )
        generated_ini = next(
            item
            for item in mutations
            if item["setting"] == "bAllowGeneratedIniWhenCooked"
        )
        self.assertEqual(
            generated_ini["applicability"]["controls"],
            [{"kind": "ternary", "expression": "Rules.bBuildEditor"}],
        )
        rendered = json.dumps(result)
        self.assertNotIn('"conditions"', rendered)
        self.assertNotIn('"control_path"', rendered)
        self.assertNotIn('"related_symbols"', rendered)

    def test_module_rules_emit_relevant_mutations_from_reachable_methods(self) -> None:
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
        SetupExternalSupport(Target);
    }

    void ConfigureEditor(ReadOnlyTargetRules Target)
    {
        if (Target.bBuildEditor)
            PrivateDependencyModuleNames.Add(EditorModuleName);
    }

    void Unused()
    {
        PublicDefinitions.Add("UNUSED=1");
    }
}
""",
                encoding="utf-8",
            )

            result = inspect_module_rules(rules)

        self.assertEqual(
            result["schema_version"], "ue-itps.module-rule-relations.v1"
        )
        rules_class = result["rules_classes"][0]
        self.assertEqual(
            list(rules_class),
            [
                "name",
                "declared_mutations",
                "unclassified_mutations",
                "unresolved_effect_calls",
            ],
        )
        mutations = rules_class["declared_mutations"]
        public_dependencies = next(
            mutation
            for mutation in mutations
            if mutation["setting"] == "PublicDependencyModuleNames"
        )
        self.assertEqual(
            public_dependencies["operand"],
            {
                "kind": "literal",
                "reference_kind": "module",
                "references": ["Core", "Engine"],
            },
        )
        self.assertEqual(public_dependencies["operation"], "add")
        private_dependencies = next(
            mutation
            for mutation in mutations
            if mutation["setting"] == "PrivateDependencyModuleNames"
        )
        self.assertEqual(
            private_dependencies["operand"],
            {"kind": "expression", "expression": "EditorModuleName"},
        )
        self.assertEqual(
            private_dependencies["applicability"],
            {
                "kind": "conditional",
                "control_path": ["if"],
                "related_symbols": ["Target.bBuildEditor"],
            },
        )
        pch = next(mutation for mutation in mutations if mutation["setting"] == "PCHUsage")
        self.assertEqual(pch["operation"], "set")
        self.assertEqual(
            pch["operand"],
            {
                "kind": "symbol",
                "references": ["PCHUsageMode.UseExplicitOrSharedPCHs"],
            },
        )
        iwyu = next(
            mutation for mutation in mutations if mutation["setting"] == "bEnforceIWYU"
        )
        self.assertEqual(iwyu["operand"], {"kind": "literal", "values": [True]})
        self.assertNotIn("UNUSED=1", json.dumps(result))
        self.assertEqual(
            rules_class["unresolved_effect_calls"],
            [
                {
                    "callee": "SetupExternalSupport",
                    "arguments": ["Target"],
                    "applicability": {"kind": "direct"},
                    "line": 10,
                }
            ],
        )
        self.assertIn(
            "Static declarations are not effective UBT build results.",
            result["limits"]["boundaries"],
        )
        serialized = json.dumps(result)
        for removed_field in ('"methods"', '"operations"', '"evaluation"', '"literal_values"'):
            self.assertNotIn(removed_field, serialized)

    def test_module_rules_fail_closed_for_empty_complex_and_unknown_mutations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            rules = Path(temporary_directory) / "Fixture.Build.cs"
            rules.write_text(
                """
public class Fixture : ModuleRules
{
    public Fixture(ReadOnlyTargetRules Target) : base(Target)
    {
        PublicIncludePaths.AddRange(new string[] { });
        DynamicallyLoadedModuleNames.AddRange(new string[] { });
        PublicIncludePaths.Add(Path.Combine(ModuleDirectory, "Private"));
        SomeNewSetting = FeatureValue;
        CustomEntries.Add("Value");
        SetupFeature(Target);
    }
}
""",
                encoding="utf-8",
            )

            result = inspect_module_rules(rules)

        rules_class = result["rules_classes"][0]
        self.assertEqual(len(rules_class["declared_mutations"]), 1)
        include_path = rules_class["declared_mutations"][0]
        self.assertEqual(include_path["setting"], "PublicIncludePaths")
        self.assertEqual(
            include_path["operand"],
            {
                "kind": "expression",
                "expression": 'Path.Combine(ModuleDirectory, "Private")',
            },
        )
        self.assertEqual(
            rules_class["unclassified_mutations"],
            [
                {
                    "target": "SomeNewSetting",
                    "operation": "set",
                    "expression": "FeatureValue",
                    "applicability": {"kind": "direct"},
                    "line": 9,
                },
                {
                    "target": "CustomEntries",
                    "operation": "add",
                    "expression": '"Value"',
                    "applicability": {"kind": "direct"},
                    "line": 10,
                },
            ],
        )
        self.assertEqual(
            rules_class["unresolved_effect_calls"],
            [
                {
                    "callee": "SetupFeature",
                    "arguments": ["Target"],
                    "applicability": {"kind": "direct"},
                    "line": 11,
                }
            ],
        )
        serialized = json.dumps(result)
        self.assertNotIn("DynamicallyLoadedModuleNames", serialized)
        self.assertNotIn("Path.Combine", json.dumps(rules_class["unresolved_effect_calls"]))

    def test_module_rules_flatten_nested_control_relevance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            rules = Path(temporary_directory) / "Fixture.Build.cs"
            rules.write_text(
                """
public class Fixture : ModuleRules
{
    public Fixture(ReadOnlyTargetRules Target) : base(Target)
    {
#if WITH_OPTIONAL_FEATURE
        foreach (string ModuleName in OptionalModules)
        {
            if (Target.bBuildEditor)
            {
                if (Target.Platform == UnrealTargetPlatform.Win64)
                {
                    switch (Target.Configuration)
                    {
                        case UnrealTargetConfiguration.Debug:
                            PublicDependencyModuleNames.Add(ModuleName);
                            break;
                    }
                }
            }
        }
#endif

        try
        {
            ConfigureExternal();
        }
        catch (BuildException)
        {
            PublicDefinitions.Add("WITH_FALLBACK=1");
        }

        if (Target.bBuildEditor)
            PublicDefinitions.Add("EDITOR=1");
        else if (Target.bCompileAgainstEngine)
            PublicDefinitions.Add("ENGINE=1");

        for (int Index = 0; Index < OptionalModules.Count; ++Index)
        {
            while (Target.bBuildEditor)
            {
                PrivateDefinitions.Add("LOOP=1");
                break;
            }
        }
    }
}
""",
                encoding="utf-8",
            )

            result = inspect_module_rules(rules)

        mutations = result["rules_classes"][0]["declared_mutations"]
        dependency = next(
            item for item in mutations if item["setting"] == "PublicDependencyModuleNames"
        )
        self.assertEqual(
            dependency["applicability"],
            {
                "kind": "conditional",
                "control_path": ["preprocessor", "foreach", "if", "if", "switch"],
                "related_symbols": [
                    "WITH_OPTIONAL_FEATURE",
                    "OptionalModules",
                    "Target.bBuildEditor",
                    "Target.Platform",
                    "UnrealTargetPlatform.Win64",
                    "Target.Configuration",
                ],
            },
        )

        fallback = next(
            item
            for item in mutations
            if item.get("operand", {}).get("references") == ["WITH_FALLBACK=1"]
        )
        self.assertEqual(
            fallback["applicability"],
            {"kind": "conditional", "control_path": ["catch"]},
        )

        engine = next(
            item
            for item in mutations
            if item.get("operand", {}).get("references") == ["ENGINE=1"]
        )
        self.assertEqual(
            engine["applicability"],
            {
                "kind": "conditional",
                "control_path": ["if"],
                "related_symbols": [
                    "Target.bBuildEditor",
                    "Target.bCompileAgainstEngine",
                ],
            },
        )

        loop = next(
            item
            for item in mutations
            if item.get("operand", {}).get("references") == ["LOOP=1"]
        )
        self.assertEqual(
            loop["applicability"],
            {
                "kind": "conditional",
                "control_path": ["for", "while"],
                "related_symbols": [
                    "OptionalModules.Count",
                    "Target.bBuildEditor",
                ],
            },
        )

    def test_module_rules_extract_mutations_from_control_expressions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            rules = Path(temporary_directory) / "Fixture.Build.cs"
            rules.write_text(
                """
public class Fixture : ModuleRules
{
    public Fixture(ReadOnlyTargetRules Target) : base(Target)
    {
        if ((PCHUsage = ResolvePCHUsage(Target)) == PCHUsageMode.NoPCHs)
        {
        }

        foreach (string ModuleName in OptionalModules)
        {
            if ((PCHUsage = ResolvePCHUsage(Target)) == PCHUsageMode.NoPCHs)
            {
            }
        }

        if (Target.bBuildEditor && (bEnforceIWYU = ResolveIWYU(Target)))
        {
        }

        if (Target.bBuildEditor)
        {
        }
        else if ((bEnforceIWYU = ResolveIWYU(Target)))
        {
        }

        for (PublicDefinitions.Add("INIT=1"); KeepGoing(Target); PublicDefinitions.Add("ITER=1"))
        {
        }

        while ((PCHUsage = ResolvePCHUsage(Target)) == PCHUsageMode.NoPCHs)
        {
            break;
        }

        if (Target.bCompileAgainstEngine
            ? (bLegacyPublicIncludePaths = UseLegacy(Target))
            : false)
        {
        }

        switch (PCHUsage = ResolvePCHUsage(Target))
        {
            default:
                break;
        }

        try
        {
        }
        catch (BuildException) when ((bLegacyPublicIncludePaths = UseLegacy(Target)))
        {
        }

        if (ConfigureRules(Target))
        {
        }

        if (++CustomCounter > 0)
        {
        }
    }

    bool ConfigureRules(ReadOnlyTargetRules Target)
    {
        PublicDefinitions.Add("HELPER=1");
        return true;
    }
}
""",
                encoding="utf-8",
            )

            result = inspect_module_rules(rules)

        rules_class = result["rules_classes"][0]
        mutations = rules_class["declared_mutations"]
        pch_mutations = [
            item for item in mutations if item["setting"] == "PCHUsage"
        ]
        self.assertEqual(len(pch_mutations), 4)
        self.assertEqual(
            [item["applicability"]["kind"] for item in pch_mutations],
            ["direct", "conditional", "direct", "direct"],
        )
        self.assertEqual(pch_mutations[0]["applicability"], {"kind": "direct"})
        self.assertEqual(
            pch_mutations[1]["applicability"]["control_path"], ["foreach"]
        )
        self.assertEqual(pch_mutations[2]["applicability"], {"kind": "direct"})
        self.assertEqual(pch_mutations[3]["applicability"], {"kind": "direct"})

        iwyu_mutations = [
            item for item in mutations if item["setting"] == "bEnforceIWYU"
        ]
        self.assertEqual(
            iwyu_mutations[0]["applicability"]["control_path"], ["short_circuit"]
        )
        self.assertEqual(
            iwyu_mutations[0]["applicability"]["related_symbols"],
            ["Target.bBuildEditor"],
        )
        self.assertEqual(iwyu_mutations[1]["applicability"]["control_path"], ["if"])
        self.assertEqual(
            iwyu_mutations[1]["applicability"]["related_symbols"],
            ["Target.bBuildEditor"],
        )

        initializer = next(
            item
            for item in mutations
            if item.get("operand", {}).get("references") == ["INIT=1"]
        )
        iterator = next(
            item
            for item in mutations
            if item.get("operand", {}).get("references") == ["ITER=1"]
        )
        self.assertEqual(initializer["applicability"], {"kind": "direct"})
        self.assertEqual(iterator["applicability"]["control_path"], ["for"])
        self.assertEqual(
            iterator["applicability"]["related_symbols"], ["KeepGoing", "Target"]
        )

        legacy_mutations = [
            item
            for item in mutations
            if item["setting"] == "bLegacyPublicIncludePaths"
        ]
        self.assertEqual(
            legacy_mutations[0]["applicability"]["control_path"], ["ternary"]
        )
        self.assertEqual(
            legacy_mutations[0]["applicability"]["related_symbols"],
            ["Target.bCompileAgainstEngine"],
        )
        self.assertEqual(
            legacy_mutations[1]["applicability"]["control_path"], ["catch"]
        )

        helper = next(
            item
            for item in mutations
            if item.get("operand", {}).get("references") == ["HELPER=1"]
        )
        self.assertEqual(helper["applicability"], {"kind": "direct"})
        self.assertEqual(
            rules_class["unresolved_effect_calls"],
            [
                {
                    "callee": "KeepGoing",
                    "arguments": ["Target"],
                    "applicability": {"kind": "direct"},
                    "line": 28,
                }
            ],
        )
        self.assertEqual(len(rules_class["unclassified_mutations"]), 1)
        counter = rules_class["unclassified_mutations"][0]
        self.assertEqual(counter["target"], "CustomCounter")
        self.assertEqual(counter["operation"], "increment")
        self.assertEqual(counter["expression"], "++CustomCounter")
        self.assertEqual(counter["applicability"], {"kind": "direct"})

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

    def test_module_entry_compresses_state_and_propagates_callback_conditions(self) -> None:
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
static FString GetPath()
{
    FString Path = TEXT("DefaultPath");
    if (HasOverride())
    {
        Path = TEXT("OverridePath");
    }
    return Path;
}

void FFixtureModule::StartupModule()
{
    if (!IsRunningGame())
    {
        BindEditorDelegates();
    }
}

void FFixtureModule::BindEditorDelegates()
{
    BeginPIEDelegate.BindRaw(this, &FFixtureModule::OnBeginPIE);
    PathDelegate.BindStatic(&GetPath);
}

void FFixtureModule::OnBeginPIE(bool bSimulating)
{
    ExperienceManager->OnPlayInEditorBegun();
}

void FFixtureModule::ShutdownModule()
{
    BeginPIEDelegate.Unbind();
    PathDelegate.Unbind();
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

        self.assertEqual(result["schema_version"], "ue-itps.module-entry-state.v7")
        self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(result["module"]["class"], "FFixtureModule")
        self.assertNotIn("module_classes", result)
        self.assertNotIn("source_files", result)
        delegate_model = next(
            model
            for model in result["state_models"]
            if model["subject"]["kind"] == "delegate_group"
        )
        self.assertEqual(delegate_model["summary"], ["default", "bound", "unbound"])
        self.assertEqual(delegate_model["closure"]["status"], "closed")
        self.assertEqual(
            {member["name"] for member in delegate_model["subject"]["members"]},
            {"BeginPIEDelegate", "PathDelegate"},
        )
        bound = next(
            transition
            for transition in delegate_model["transitions"]
            if transition["sets_state"] == "bound"
        )
        self.assertEqual(bound["via"], ["StartupModule", "BindEditorDelegates"])
        self.assertEqual(bound["when"], [["!IsRunningGame()"]])
        override = result["conditional_overrides"][0]
        self.assertEqual(override["summary"], ["default", "overridden"])
        self.assertEqual(
            override["when"],
            [["!IsRunningGame()", "HasOverride()"]],
        )
        encoded = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("DefaultPath", encoded)
        self.assertNotIn("OverridePath", encoded)
        self.assertNotIn("UnrelatedMethod", encoded)
        self.assertEqual(
            result["unresolved_effects"][0]["call"],
            "ExperienceManager->OnPlayInEditorBegun",
        )

    def test_module_entry_reports_conditional_cleanup_and_lifecycle_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            rules = root / "Fixture.Build.cs"
            rules.write_text("public class Fixture : ModuleRules {}", encoding="utf-8")
            (root / "FixtureModule.cpp").write_text(
                """
static void RegisterMenus()
{
    UToolMenus::Get()->ExtendMenu("Fixture.Menu");
}

class FFixtureModule : public IModuleInterface
{
public:
    virtual void StartupModule() override
    {
        FFixtureStyle::Initialize();
        if (FSlateApplication::IsInitialized())
        {
            MenuHandle = UToolMenus::RegisterStartupCallback(
                FSimpleMulticastDelegate::FDelegate::CreateStatic(&RegisterMenus));
        }
        AssetTools.RegisterAssetTypeActions(AssetAction);
    }

    virtual void ShutdownModule() override
    {
        if (UObjectInitialized() && MenuHandle.IsValid())
        {
            UToolMenus::UnRegisterStartupCallback(MenuHandle);
        }
        if (AssetToolsModule && AssetAction)
        {
            AssetToolsModule->Get().UnregisterAssetTypeActions(AssetAction.ToSharedRef());
        }
        FFixtureStyle::Shutdown();
    }
};

IMPLEMENT_MODULE(FFixtureModule, Fixture)
""",
                encoding="utf-8",
            )

            result = inspect_module_entry(rules)

        by_label = {
            model["subject"]["label"]: model for model in result["state_models"]
        }
        self.assertEqual(by_label["FFixtureStyle"]["closure"]["status"], "closed")
        self.assertEqual(by_label["Asset Type Actions"]["closure"]["status"], "conditional")
        self.assertEqual(
            by_label["UToolMenus startup callback"]["closure"]["status"],
            "conditional",
        )
        self.assertEqual(by_label["editor menu"]["closure"]["status"], "open")
        menu_transition = by_label["editor menu"]["transitions"][0]
        self.assertEqual(menu_transition["via"], ["RegisterMenus"])
        self.assertEqual(
            menu_transition["when"],
            [["FSlateApplication::IsInitialized()"]],
        )

    def test_module_entry_rejects_invalid_rules_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            missing = root / "Missing.Build.cs"
            wrong_suffix = root / "Fixture.cs"
            wrong_suffix.write_text("", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "is not a file"):
                inspect_module_entry(missing)
            with self.assertRaisesRegex(ValueError, "Expected a Module Build.cs file"):
                inspect_module_entry(wrong_suffix)


if __name__ == "__main__":
    unittest.main()
