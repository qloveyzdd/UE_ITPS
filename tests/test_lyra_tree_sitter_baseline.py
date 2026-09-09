from __future__ import annotations

from pathlib import Path
import sys
import unittest

from tree_sitter import Language, Parser
import tree_sitter_ue_cpp

from tests.support import ROOT

sys.path.insert(0, str(ROOT / "sourcetools"))

from ue_project_tools.cpp_frontend import load_cpp_unit
from ue_project_tools.cpp_expression_facts import BUILTIN_TYPE_NAMES
from ue_project_tools.source_function_references import inspect_source_function
from ue_project_tools.source_type_facts import list_source_types
from ue_project_tools.source_type_details import inspect_source_type


def _raw_call_owner(node):
    """Independent ancestor check for calls in executable definition regions."""
    callee = node.child_by_field_name("function")
    if callee is not None:
        if callee.type in {"primitive_type", "sized_type_specifier"}:
            return None
        if callee.type == "identifier" and callee.text.decode("utf-8") in BUILTIN_TYPE_NAMES:
            return None
        name = callee.child_by_field_name("name")
        if callee.type == "template_function" and name is not None and name.text.decode("utf-8") in {
            "const_cast", "static_cast", "reinterpret_cast", "dynamic_cast",
        }:
            return None
    branch, parent = node, node.parent
    while parent is not None:
        if parent.type in {"class_specifier", "struct_specifier", "union_specifier", "enum_specifier",
                           "function_declarator", "abstract_function_declarator"}:
            return None
        if parent.type == "function_definition":
            return parent if branch.type in {"compound_statement", "field_initializer_list", "try_statement"} else None
        branch, parent = parent, parent.parent
    return None


class LyraTreeSitterBaselineTests(unittest.TestCase):
    def test_raw_call_owner_contract_on_synthetic_source(self) -> None:
        tree = Parser(Language(tree_sitter_ue_cpp.language())).parse(b'''
            struct A { A(int X = Default()) noexcept(Check())
                : Value(Factory([] { Inner(); })) { Consume(int(Value)); } int Value; };
        ''')
        stack, calls = [tree.root_node], []
        while stack:
            node = stack.pop()
            if node.type == "call_expression" and _raw_call_owner(node) is not None:
                calls.append(node.child_by_field_name("function").text.decode("utf-8"))
            stack.extend(reversed(node.named_children))
        self.assertEqual(calls, ["Factory", "Inner", "Consume"])

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
        raw_definitions = set()
        raw_type_definitions = set()
        raw_body_calls = {}
        macro_end_lines = {}
        type_nodes = {"class_specifier", "struct_specifier", "union_specifier", "enum_specifier",
                      "ue_test_class_declaration", "ue_test_spec_declaration"}
        for path in files:
            source = path.read_bytes()
            file_key = path.resolve().as_posix().casefold()
            tree = parser.parse(source)
            self.assertFalse(tree.root_node.has_error, path.as_posix())
            stack = [tree.root_node]
            while stack:
                node = stack.pop()
                if node.type in syntax_counts:
                    syntax_counts[node.type] += 1
                if node.type == "function_definition":
                    raw_definitions.add((file_key, node.start_byte))
                if node.type in type_nodes and (
                    node.type.startswith("ue_test_")
                    or (node.child_by_field_name("name") is not None
                        and node.child_by_field_name("body") is not None)
                ):
                    raw_type_definitions.add((file_key, node.start_byte))
                if node.type == "call_expression":
                    owner = _raw_call_owner(node)
                    if owner is not None:
                        raw_body_calls.setdefault((file_key, owner.start_byte), set()).add(node.start_byte)
                if node.type in {"preproc_def", "preproc_function_def"}:
                    # Strip the directive's final newline, keeping continuation lines.
                    directive = source[node.start_byte:node.end_byte].rstrip(b"\r\n")
                    macro_end_lines[(file_key, node.start_point.row + 1)] = (
                        node.start_point.row + 1 + directive.count(b"\n")
                    )
                stack.extend(reversed(node.named_children))

        self.assertEqual(syntax_counts["ue_slate_arguments_declaration"], 8)
        self.assertEqual(syntax_counts["ue_test_class_declaration"], 4)
        self.assertEqual(syntax_counts["ue_test_spec_declaration"], 1)

        model = load_cpp_unit(files[0], files, project_root)

        self.assertEqual(model["diagnostic_error_count"], 0)
        self.assertEqual(len(model["types"]), 2022)
        # Nested type bodies must not create spurious outer-class function declarations.
        self.assertEqual(len(model["functions"]), 6069)
        self.assertEqual(len(model["variables"]), 302)
        self.assertEqual(len(model["includes"]), 3254)
        self.assertEqual(len(model["macros"]), 3016)

        definitions = [item for item in model["types"] if item["role"] == "definition"]
        self.assertEqual({(t["file"], t["start_offset"]) for t in definitions}, raw_type_definitions)
        functions = [f for f in model["functions"] if f["role"] == "definition"]
        self.assertEqual(len(functions), len(raw_definitions))
        self.assertEqual({(f["file"], f["start_offset"]) for f in functions}, raw_definitions)
        self.assertEqual(len(model["references"]), len(functions))
        for function in functions:
            location = (function["file"], function["start_offset"])
            references = model["references"][function["occurrence_id"]]
            self.assertEqual({c["start_offset"] for c in references["call_details"]},
                             raw_body_calls.get(location, set()), location)
        for macro in model["macro_definitions"]:
            location = (macro["file"], macro["line"])
            self.assertEqual(macro["end_line"], macro_end_lines[location], location)
        self.assertEqual(sum(len(item.get("fields", [])) for item in definitions), 1850)
        # Include inline definitions, constructors and template member declarations.
        self.assertEqual(sum(len(item.get("methods", [])) for item in definitions), 3348)
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
