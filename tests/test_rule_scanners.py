from __future__ import annotations

from pathlib import Path
import tempfile

from tools.ue_project_tools.rule_source import (
    inspect_module_rules,
    inspect_target_rules,
)

from tests.support import EnvelopeAssertions, create_fixture, write_text


class RuleScannerTests(EnvelopeAssertions):
    def test_module_rules_follow_same_file_helpers_and_keep_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            result = inspect_module_rules(fixture.game_rules)

        self.assert_envelope(result)
        rules = result["rules_classes"][0]
        settings = [item["setting"] for item in rules["declared_mutations"]]
        self.assertIn("PCHUsage", settings)
        self.assertIn("PublicDependencyModuleNames", settings)
        self.assertIn("PrivateDependencyModuleNames", settings)
        self.assertIn("DynamicallyLoadedModuleNames", settings)
        private = next(
            item
            for item in rules["declared_mutations"]
            if item["setting"] == "PrivateDependencyModuleNames"
        )
        self.assertEqual(private["applicability"]["kind"], "conditional")
        self.assertEqual(private["applicability"]["control_path"], ["if"])

    def test_target_rules_project_reachable_mutations_and_source_methods(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            result = inspect_target_rules(fixture.target_file)

        self.assert_envelope(result)
        rules = result["rules_classes"][0]
        self.assertEqual(rules["inheritance"]["kind"], "confirmed")
        by_setting = {
            item["setting"]: item for item in rules["declared_mutations"]
        }
        self.assertEqual(by_setting["Type"]["operand"]["references"], ["TargetType.Game"])
        self.assertEqual(
            by_setting["bUseLoggingInShipping"]["source"]["method"],
            "ApplySharedSettings",
        )
        self.assertEqual(
            by_setting["bUseLoggingInShipping"]["applicability"]["controls"][0][
                "kind"
            ],
            "if",
        )

    def test_rule_scanners_fail_closed_for_wrong_base_type(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "Wrong.Build.cs"
            write_text(
                path,
                """
                public class Wrong : NotModuleRules
                {
                    public Wrong(ReadOnlyTargetRules Target) {}
                }
                """,
            )
            result = inspect_module_rules(path)

        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(result["rules_classes"], [])
