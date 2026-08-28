from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests.support import create_fixture, run_cli, write_text


class CxxFunctionSemanticsTests(unittest.TestCase):
    def test_same_type_get_accessor_resolves_chained_member_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                class AWorker
                {
                public:
                    void ShowNotification();
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                void AWorker::ShowNotification()
                {
                    FNotificationInfo Info;
                    FSlateNotificationManager::Get().AddNotification(Info);
                    FSlateApplication::Get().GetPlatformApplication();
                    FContainer Container;
                    Container.Get().DoWork();
                }
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "ShowNotification",
            )

            self.assertEqual(completed.returncode, 0)
            symbols = result["matches"][0]["external_symbols"]
            notification_call = next(
                item for item in symbols if item["spelling"].endswith("AddNotification()")
            )
            self.assertEqual(notification_call["kind"], "member_call")
            self.assertEqual(
                notification_call["spelling"],
                "FSlateNotificationManager->AddNotification()",
            )
            self.assertEqual(
                notification_call["owner_type"], "FSlateNotificationManager"
            )
            application_call = next(
                item
                for item in symbols
                if item["spelling"].endswith("GetPlatformApplication()")
            )
            self.assertEqual(application_call["kind"], "member_call")
            self.assertEqual(
                application_call["spelling"],
                "FSlateApplication->GetPlatformApplication()",
            )
            self.assertEqual(application_call["owner_type"], "FSlateApplication")
            object_get_call = next(
                item for item in symbols if item["spelling"].endswith("DoWork()")
            )
            self.assertEqual(object_get_call["kind"], "unknown")
            self.assertEqual(result["matches"][0]["delegate_operations"], [])

    def test_known_ue_function_like_macros_use_macro_kind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                class AWorker
                {
                public:
                    void BuildText();
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                void AWorker::BuildText()
                {
                    LOCTEXT("Key", "Value");
                    NSLOCTEXT("Namespace", "Key", "Value");
                    INVTEXT("Value");
                    UNKNOWN_MACRO_STYLE();
                }
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "BuildText",
            )

            self.assertEqual(completed.returncode, 0)
            symbols = {
                item["spelling"]: item["kind"]
                for item in result["matches"][0]["external_symbols"]
            }
            self.assertEqual(symbols["LOCTEXT()"], "macro")
            self.assertEqual(symbols["NSLOCTEXT()"], "macro")
            self.assertEqual(symbols["INVTEXT()"], "macro")
            self.assertEqual(symbols["UNKNOWN_MACRO_STYLE()"], "unknown")

    def test_member_call_receiver_uses_current_class_field_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                class AWorker
                {
                public:
                    void CheckExperience() const;

                private:
                    FPrimaryAssetId ExperienceOverride;
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                void AWorker::CheckExperience() const
                {
                    ExperienceOverride.IsValid();
                }
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "CheckExperience",
            )

            self.assertEqual(completed.returncode, 0)
            symbol = next(
                item
                for item in result["matches"][0]["external_symbols"]
                if item["spelling"].endswith("IsValid()")
            )
            self.assertEqual(symbol["kind"], "member_call")
            self.assertEqual(symbol["spelling"], "FPrimaryAssetId->IsValid()")
            self.assertEqual(symbol["owner_type"], "FPrimaryAssetId")
            self.assertEqual(symbol["evidence"], {"unit": "cpp", "line": 4})

    def test_function_inside_preprocessor_condition_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                class AWorker
                {
                public:
                #if WITH_EDITOR
                    void OnPlayInEditorStarted() const;
                #endif
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                #if WITH_EDITOR
                void AWorker::OnPlayInEditorStarted() const
                {
                }
                #endif
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "OnPlayInEditorStarted",
            )

            self.assertEqual(completed.returncode, 0)
            self.assertEqual(result["match_count"], 1)
            self.assertNotIn("selection", result)
            self.assertNotIn("function", result["matches"][0])
            self.assertNotIn("relation", result["matches"][0])

            completed, missing = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "MissingFunction",
            )
            self.assertEqual(completed.returncode, 1)
            self.assertNotIn("selection", missing)
            self.assertTrue(
                all("selection" not in item for item in missing["validation"]["problems"])
            )

    def test_function_id_and_external_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                class AWorker
                {
                public:
                    void Normalize(TArray<int>& Values) const;
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                int32 GCounter = 0;

                void AWorker::Normalize(TArray< int >& Values) const
                {
                    ++GCounter;
                }
                """,
            )

            completed, normalized = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "Normalize",
            )
            self.assertEqual(completed.returncode, 0)
            match = normalized["matches"][0]
            self.assertIn("AWorker|Normalize", match["function_id"])
            self.assertTrue(match["function_id"].endswith(" const"))
            global_symbol = next(
                item
                for item in match["external_symbols"]
                if item["kind"] == "global_variable"
            )
            self.assertEqual(global_symbol["spelling"], "GCounter")
            self.assertEqual(global_symbol["evidence"], {"unit": "cpp", "line": 6})

    def test_delegate_projection_ignores_non_delegate_register_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                class AWorker
                {
                public:
                    void Activate();
                    void OnFinished();
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                void AWorker::Activate()
                {
                    FRouter Router;
                    Router.RegisterListenerInternal();
                    OnFinishedEvent.AddUObject(this, &AWorker::OnFinished);
                    OnFinished.Broadcast();
                }
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "Activate",
            )
            self.assertEqual(completed.returncode, 0)
            operations = result["matches"][0]["delegate_operations"]
            self.assertEqual(len(operations), 2)
            self.assertEqual(operations[0]["operation"], "subscribe")
            self.assertEqual(operations[0]["api"], "AddUObject")
            self.assertEqual(
                operations[0]["callback"]["qualified_name"],
                "AWorker::OnFinished",
            )
            self.assertEqual(operations[1]["operation"], "publish")
            self.assertEqual(operations[1]["api"], "Broadcast")
            self.assertEqual(
                operations[1]["event"]["qualified_name"],
                "AWorker::OnFinished",
            )


if __name__ == "__main__":
    unittest.main()
