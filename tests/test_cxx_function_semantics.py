from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests.support import create_fixture, run_cli, write_text


class CxxFunctionSemanticsTests(unittest.TestCase):
    def test_ast_driven_function_identity_and_qualifiers(self) -> None:
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
                    void ConstParameter(const UObject* Value);
                    void MacroParameter(UPARAM(ref) int32& Value, OUT TArray<int>& Values);
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

                void AWorker::ConstParameter(const UObject* Value)
                {
                }

                void AWorker::MacroParameter(UPARAM(ref) int32& Value, OUT TArray<int>& Values)
                {
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
            self.assertEqual(match["relation"]["status"], "matched")
            self.assertEqual(match["function"]["qualifiers"], ["const"])
            global_symbol = next(
                item
                for item in match["external_symbols"]
                if item["kind"] == "global_variable"
            )
            self.assertEqual(global_symbol["spelling"], "GCounter")
            self.assertEqual(global_symbol["evidence"], {"unit": "cpp", "line": 6})

            completed, const_parameter = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "ConstParameter",
            )
            self.assertEqual(completed.returncode, 0)
            match = const_parameter["matches"][0]
            self.assertEqual(match["relation"]["status"], "matched")
            self.assertEqual(match["function"]["qualifiers"], [])

            completed, macro_parameter = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "MacroParameter",
            )
            self.assertEqual(completed.returncode, 0)
            match = macro_parameter["matches"][0]
            self.assertEqual(match["relation"]["status"], "matched")
            self.assertEqual(
                match["function"]["parameters"],
                "int32& Value, TArray<int>& Values",
            )
            self.assertEqual(macro_parameter["validation"]["status"], "ok")

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
