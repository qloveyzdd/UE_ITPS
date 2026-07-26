from __future__ import annotations

from pathlib import Path
import tempfile

from tools.ue_project_tools.cs_source import inspect_cs_function

from tests.support import EnvelopeAssertions, create_fixture, write_text


class CsFunctionTests(EnvelopeAssertions):
    def test_target_function_reports_qualified_types_and_local_calls(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            result = inspect_cs_function(
                fixture.target_file,
                "FixtureGameTarget",
            )
            build_result = inspect_cs_function(
                fixture.game_rules,
                "FixtureGame",
            )

        self.assert_envelope(result)
        self.assertEqual(result["schema_version"], "ue-itps.cs-function.v1")
        self.assertEqual(result["selection"]["name"], "FixtureGameTarget")
        self.assertEqual(result["match_count"], 1)
        match = result["matches"][0]
        self.assertEqual(match["function"]["owner"], "FixtureGameTarget")
        self.assertEqual(match["function"]["kind"], "constructor")
        self.assertNotIn("operations", match)
        self.assertEqual(
            match["external_types"],
            ["TargetInfo", "TargetType"],
        )
        self.assertEqual(
            match["external_methods"],
            [
                'ExtraModuleNames.Add("FixtureGame")',
                "ApplySharedSettings(Target)",
            ],
        )
        self.assertEqual(build_result["match_count"], 1)
        self.assertEqual(
            build_result["matches"][0]["external_types"],
            ["ModuleRules", "ReadOnlyTargetRules"],
        )

    def test_plain_cs_function_reports_typed_and_unresolved_member_calls(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "Plain.cs"
            write_text(
                source,
                """
                public class Plain
                {
                    private ServiceClient Client;
                    private IgnoredClient UnusedClient;

                    public void Configure(bool Enabled)
                    {
                        ServiceClient Service = Client;
                        Worker Worker = new Worker();
                        Service.State = Enabled;
                        if (Enabled)
                        {
                            Service.Start();
                            Service.Children.Start();
                            Client.Stop();
                            Worker.Run();
                            Utility.Reset(Enabled);
                            Configure(Enabled);
                            this.Configure(Enabled);
                            Plain.Configure(Enabled);
                        }
                    }
                }
                """,
            )
            result = inspect_cs_function(source, "Configure")

        self.assert_envelope(result)
        self.assertEqual(result["match_count"], 1)
        match = result["matches"][0]
        self.assertEqual(
            match["external_types"],
            ["ServiceClient", "Worker"],
        )
        self.assertEqual(
            match["external_methods"],
            [
                "ServiceClient.Start()",
                "ServiceClient.Children.Start()",
                "ServiceClient.Stop()",
                "Worker.Run()",
                "Utility.Reset(Enabled)",
                "Configure(Enabled)",
                "this.Configure(Enabled)",
                "Plain.Configure(Enabled)",
            ],
        )

    def test_function_selection_returns_all_same_name_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "Overloads.cs"
            write_text(
                source,
                """
                public class Overloads
                {
                    public void Apply(int Value) {}
                    public void Apply(string Value) {}
                }
                """,
            )
            result = inspect_cs_function(source, "Apply")

        self.assertEqual(result["match_count"], 2)
        self.assertEqual(len(result["matches"]), 2)
        for match in result["matches"]:
            self.assertEqual(match["external_types"], [])
            self.assertEqual(match["external_methods"], [])
            self.assertNotIn("operations", match)

    def test_missing_function_is_a_structured_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "Plain.cs"
            write_text(source, "public class Plain {}")
            result = inspect_cs_function(source, "Missing")

        self.assertEqual(result["match_count"], 0)
        self.assertEqual(result["validation"]["status"], "error")
        self.assertTrue(
            any(
                problem["code"] == "function-not-found"
                for problem in result["validation"]["problems"]
            )
        )
