from __future__ import annotations

from pathlib import Path
import sys
import unittest

from tree_sitter import Language, Parser
import tree_sitter_ue_cpp

from tests.support import ROOT

sys.path.insert(0, str(ROOT / "sourcetools"))

from ue_project_tools.cpp_frontend import load_cpp_unit
from ue_project_tools.source_function_references import inspect_source_function
from ue_project_tools.source_type_facts import list_source_types
from ue_project_tools.source_type_details import inspect_source_type


class LyraTreeSitterBaselineTests(unittest.TestCase):
    def test_lyra_delegate_creation_execution_and_removal(self) -> None:
        root = ROOT / "LyraStarterGame" / "Source" / "LyraGame"

        def scan(relative, function):
            paths = [root / f"{relative}.cpp", root / f"{relative}.h"]
            result = inspect_source_function(paths, function)
            self.assertEqual(result["validation"]["status"], "ok")
            self.assertEqual(result["delegate_contract_revision"], 2)
            return result["matches"][0]["delegate_operations"]

        operations = scan("AbilitySystem/Phases/LyraGamePhaseSubsystem",
                          "ULyraGamePhaseSubsystem::K2_StartPhase")
        self.assertEqual([o["operation"] for o in operations], ["create", "execute"])
        self.assertTrue(all(o["resolution"]["status"] == "identified" for o in operations))
        self.assertEqual(operations[0]["subject"]["qualified_name"], "FLyraGamePhaseDelegate")
        self.assertEqual(operations[0]["callback"]["kind"], "lambda")
        self.assertEqual(operations[1]["execution_scope"]["kind"], "lambda")
        self.assertIsNone(operations[1]["subject"]["qualified_name"])
        operations = scan("AbilitySystem/Phases/LyraGamePhaseSubsystem",
                          "ULyraGamePhaseSubsystem::StartPhase")
        execute = next(o for o in operations if o["api"] == "ExecuteIfBound")
        self.assertEqual(execute["subject"]["kind"], "parameter")
        self.assertIsNone(execute["subject"]["qualified_name"])
        operations = scan("Weapons/LyraGameplayAbility_RangedWeapon",
                          "ULyraGameplayAbility_RangedWeapon::EndAbility")
        removal = next(o for o in operations if o["api"] == "Remove")
        self.assertEqual(removal["operation"], "remove")
        self.assertEqual(removal["arguments"][0]["expression"], "OnTargetDataReadyCallbackDelegateHandle")
        self.assertEqual(removal["resolution"]["status"], "candidate")

    def test_lyra_tool_symbol_and_member_projections(self) -> None:
        root = ROOT / "LyraStarterGame" / "Source" / "LyraGame"

        def pair(relative: str) -> list[Path]:
            return [root / f"{relative}.cpp", root / f"{relative}.h"]

        health = inspect_source_function(
            pair("Character/LyraHealthComponent"),
            "ULyraHealthComponent::InitializeWithAbilitySystem",
        )
        symbols = health["matches"][0]["external_symbols"]
        self.assertTrue(any(
            item["kind"] == "type" and item["spelling"] == "ULyraHealthSet"
            and item["evidence"]["line"] == 70 for item in symbols
        ))
        self.assertEqual(
            [item["spelling"] for item in symbols
             if item["kind"] == "macro" and item["evidence"]["line"] == 59],
            ["UE_LOG()", "TEXT()"],
        )

        experience = pair("GameModes/LyraExperienceManagerComponent")
        result = inspect_source_function(
            experience, "ULyraExperienceManagerComponent::OnExperienceFullLoadCompleted"
        )
        self.assertEqual(result["validation"]["status"], "ok")
        self.assertIn(
            ("free_function", "LyraConsoleVariables::GetExperienceLoadDelayDuration"),
            {(s["kind"], s["spelling"]) for s in result["matches"][0]["external_symbols"]},
        )
        result = inspect_source_function(
            experience, "ULyraExperienceManagerComponent::CallOrRegister_OnExperienceLoaded"
        )
        self.assertIn(
            "FOnLyraExperienceLoaded::FDelegate",
            {s.get("owner_type") for s in result["matches"][0]["external_symbols"]},
        )
        result = inspect_source_function(
            pair("Weapons/LyraGameplayAbility_RangedWeapon"),
            "ULyraGameplayAbility_RangedWeapon::ActivateAbility",
        )
        operation = result["matches"][0]["delegate_operations"][0]
        self.assertIn("AbilityTargetDataSetDelegate", operation["subject"]["expression"])
        self.assertIsNone(operation["subject"]["qualified_name"])
        self.assertEqual(operation["resolution"]["status"], "candidate")
        result = inspect_source_type(pair("System/GameplayTagStack"), "FGameplayTagStackContainer")
        container = result["matches"][0]
        self.assertTrue(
            {"GetStackCount", "ContainsTag", "NetDeltaSerialize"}
            <= {m["name"] for m in container["member_anchors"]}
        )
        hero = pair("Character/LyraHeroComponent")
        result = list_source_types(hero)
        self.assertIn("ULyraHeroComponent::NAME_ActorFeatureName",
                      {v["qualified_name"] for v in result["global_variables"]})
        result = inspect_source_function(hero, "ULyraHeroComponent::GetFeatureName")
        self.assertEqual(result["matches"][0]["external_symbols"][0]["spelling"],
                         "ULyraHeroComponent::NAME_ActorFeatureName")

    def test_full_lyra_source_tree_matches_baseline(self) -> None:
        project_root = ROOT / "LyraStarterGame"
        files = sorted(
            path
            for path in (*project_root.rglob("*.h"), *project_root.rglob("*.cpp"))
            if "Source" in path.relative_to(project_root).parts
            and not {"Intermediate", "Binaries"}.intersection(
                path.relative_to(project_root).parts
            )
        )

        self.assertEqual(len(files), 707)

        parser = Parser(Language(tree_sitter_ue_cpp.language()))
        syntax_counts = {
            "ue_slate_arguments_declaration": 0,
            "ue_test_class_declaration": 0,
            "ue_test_spec_declaration": 0,
        }
        for path in files:
            tree = parser.parse(path.read_bytes())
            self.assertFalse(tree.root_node.has_error, path.as_posix())
            stack = [tree.root_node]
            while stack:
                node = stack.pop()
                if node.type in syntax_counts:
                    syntax_counts[node.type] += 1
                stack.extend(reversed(node.named_children))

        self.assertEqual(syntax_counts["ue_slate_arguments_declaration"], 8)
        self.assertEqual(syntax_counts["ue_test_class_declaration"], 4)
        self.assertEqual(syntax_counts["ue_test_spec_declaration"], 1)

        model = load_cpp_unit(files[0], files, project_root)

        self.assertEqual(model["diagnostic_error_count"], 0)
        self.assertEqual(len(model["types"]), 2010)
        # Nested type bodies must not create spurious outer-class function declarations.
        self.assertEqual(len(model["functions"]), 6037)
        self.assertEqual(len(model["variables"]), 302)
        self.assertEqual(len(model["includes"]), 3254)
        self.assertEqual(len(model["macros"]), 3016)

        definitions = [item for item in model["types"] if item["role"] == "definition"]
        self.assertEqual(sum(len(item.get("fields", [])) for item in definitions), 1842)
        # Include inline definitions, constructors and template member declarations.
        self.assertEqual(sum(len(item.get("methods", [])) for item in definitions), 3318)
        self.assertEqual(
            sum(len(item.get("enumerators", [])) for item in definitions), 234
        )
        self.assertEqual(
            sum(
                any(
                    str(macro).startswith("UPROPERTY(")
                    for macro in field.get("macros", [])
                )
                for item in definitions
                for field in item.get("fields", [])
            ),
            1130,
        )


if __name__ == "__main__":
    unittest.main()
