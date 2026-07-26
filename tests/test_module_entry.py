from __future__ import annotations

from pathlib import Path
import tempfile

from tools.ue_project_tools.module_entry import inspect_module_entry

from tests.support import EnvelopeAssertions, create_fixture, write_text


class ModuleEntryTests(EnvelopeAssertions):
    def test_module_entry_reports_registration_binding_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            result = inspect_module_entry(fixture.plugin_rules)

        self.assert_envelope(result)
        self.assertEqual(result["registration"]["macro"], "IMPLEMENT_MODULE")
        self.assertEqual(
            result["registration"]["module_class"],
            "FFixturePluginModule",
        )
        self.assertEqual(len(result["callback_bindings"]), 1)
        binding = result["callback_bindings"][0]
        self.assertEqual(binding["callback"]["kind"], "function")
        self.assertTrue(binding["unbind"])
        self.assertEqual(result["unmatched_cleanups"], [])

    def test_default_module_registration_does_not_invent_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            write_text(
                fixture.plugin_entry,
                """
                #include "Modules/ModuleManager.h"
                IMPLEMENT_MODULE(FDefaultModuleImpl, FixturePlugin)
                """,
            )
            result = inspect_module_entry(fixture.plugin_rules)

        self.assertEqual(
            result["registration"]["module_class"],
            "FDefaultModuleImpl",
        )
        self.assertIsNone(result["module"]["class"])
        self.assertEqual(result["state_models"], [])

    def test_unbalanced_delimiters_are_blocking_but_keep_partial_facts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            write_text(
                fixture.plugin_entry,
                """
                class FFixturePluginModule : public IModuleInterface
                {
                public:
                    virtual void StartupModule() override
                    {
                        FCoreDelegates::OnPostEngineInit.AddRaw(
                            this, &FFixturePluginModule::HandleReady;
                    }
                };
                IMPLEMENT_MODULE(FFixturePluginModule, FixturePlugin)
                """,
            )
            result = inspect_module_entry(fixture.plugin_rules)

        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(result["registration"]["module_class"], "FFixturePluginModule")
        self.assertTrue(
            any(
                "delimiter" in problem["code"]
                for problem in result["validation"]["problems"]
            )
        )
