"""Lyra regressions exercised only through the SourceTools public commands."""
from pathlib import Path
import unittest

from tests.support import ROOT, run_cli


class LyraSourceToolsRegressionTests(unittest.TestCase):
    def source(self, relative):
        return ROOT / "LyraStarterGame" / relative

    def inspect(self, paths, selector):
        completed, result = run_cli("sourcetools/ue_inspect_cxx_function.py", "--source",
                                    *(self.source(p) for p in paths), "--function", selector,
                                    "--include-syntax-flow")
        self.assertEqual(completed.returncode, 0, result)
        return result["matches"]

    def test_macro_display_text(self):
        path = self.source("Plugins/CommonLoadingScreen/Source/CommonLoadingScreen/Private/CommonLoadingScreenSettings.h")
        completed, result = run_cli("sourcetools/ue_list_cxx_types.py", "--source", path)
        self.assertEqual(completed.returncode, 0, result)
        self.assertTrue(any('DisplayName="Common Loading Screen"' in macro
                            for item in result["classes"] for macro in item["macros"]))

    def test_constructor_initializer_and_delegate(self):
        matches = self.inspect([
            "Plugins/AsyncMixin/Source/Private/AsyncMixin.cpp",
            "Plugins/AsyncMixin/Source/Public/AsyncMixin.h",
        ], "FAsyncCondition::FAsyncCondition")
        constructor = next(m for m in matches if "TFunction<" in m["function_id"])
        self.assertEqual([c["callee"] for c in constructor["syntax_flow"]["calls"]],
                         ["FAsyncConditionDelegate::CreateLambda", "MoveTemp", "UserFunction"])
        self.assertEqual(constructor["delegate_operations"][0]["resolution"]["status"], "identified")
        self.assertEqual(constructor["delegate_operations"][0]["callback"]["kind"], "lambda")
        self.assertEqual(constructor["delegate_operations"][0]["result"],
                         {"expression": "UserCondition", "kind": "delegate"})

    def test_this_and_global_receivers(self):
        matches = self.inspect([
            "Plugins/GameSettings/Source/Private/Widgets/GameSettingScreen.cpp",
            "Plugins/GameSettings/Source/Public/Widgets/GameSettingScreen.h",
        ], "UGameSettingScreen::GetOrCreateRegistry")
        self.assertIn("UGameSettingScreen->CreateRegistry()",
                      [s["spelling"] for s in matches[0]["external_symbols"] if s["kind"] == "member_call"])
        matches = self.inspect(["Source/LyraGame/Settings/LyraSettingsLocal.cpp",
                                "Source/LyraGame/Settings/LyraSettingsLocal.h"],
                               "ULyraSettingsLocal::GetDefaultMobileFrameRate")
        self.assertIn("TAutoConsoleVariable<int32>->GetValueOnGameThread()",
                      [s["spelling"] for s in matches[0]["external_symbols"] if s["kind"] == "member_call"])

    def test_injected_name_navigation_preserves_source_spelling(self):
        paths = [self.source("Source/LyraGame/System/LyraGameData" + suffix) for suffix in (".cpp", ".h")]
        completed, inventory = run_cli("sourcetools/ue_list_cxx_functions.py", "--source", *paths)
        self.assertEqual(completed.returncode, 0, inventory)
        entry = next(f for f in inventory["functions"] if f["qualified_name"] == "ULyraGameData::Get")
        self.assertEqual(entry["source_qualified_name"], "ULyraGameData::ULyraGameData::Get")
        completed, details = run_cli("sourcetools/ue_inspect_cxx_function.py", "--source", *paths,
                                     "--function", entry["qualified_name"])
        self.assertEqual(completed.returncode, 0, details)
        self.assertEqual(entry["function_id"], details["matches"][0]["function_id"])
