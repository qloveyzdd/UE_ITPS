from __future__ import annotations

import json
from pathlib import Path
import tempfile

from tools.ue_project_tools.common import read_json, result_document

from tests.support import CLI_SCRIPTS, EnvelopeAssertions, run_cli


class CliContractTests(EnvelopeAssertions):
    def test_all_cli_help_is_bilingual_and_declares_exit_codes(self) -> None:
        for script in CLI_SCRIPTS:
            with self.subTest(script=script):
                completed = run_cli(script, "--help")
                self.assertEqual(completed.returncode, 0)
                self.assertEqual(completed.stderr, "")
                self.assertIn("用法 / usage", completed.stdout)
                self.assertIn("选项 / Options", completed.stdout)
                self.assertIn("输出契约", completed.stdout)
                self.assertIn("Output contract", completed.stdout)
                self.assertIn("退出码", completed.stdout)
                self.assertIn("Exit codes", completed.stdout)

    def test_result_document_has_stable_envelope_and_reserved_fields(self) -> None:
        result = result_document(
            "ue-itps.fixture.v1",
            {"facts": ["one"]},
            [{"severity": "warning", "code": "fixture-warning"}],
            responsibility="Exercise the public result envelope.",
            boundaries=["Fixture only."],
        )

        self.assert_envelope(result)
        self.assertEqual(result["validation"]["status"], "warning")
        with self.assertRaisesRegex(ValueError, "reserved fields"):
            result_document(
                "ue-itps.fixture.v1",
                {"validation": {}},
                [],
                responsibility="Invalid fixture.",
                boundaries=[],
            )

    def test_json_reader_rejects_duplicate_keys_and_nonstandard_constants(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "Fixture.uproject"
            path.write_text('{"FileVersion": 3, "FileVersion": 2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate JSON object key"):
                read_json(path)

            path.write_text('{"FileVersion": NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Non-standard JSON constant"):
                read_json(path)

    def test_target_cli_rejects_missing_project_before_scanning_parent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "Source"
            source.mkdir()
            (source / "Game.Target.cs").write_text("", encoding="utf-8")

            completed = run_cli(
                "ue_inspect_targets.py",
                "--project",
                str(root / "Missing.uproject"),
            )

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("Missing.uproject", completed.stderr)

    def test_source_clis_return_schema_json_for_missing_input(self) -> None:
        cases = {
            "ue_list_source_includes.py": "ue-itps.source-includes.v1",
            "ue_list_source_types.py": "ue-itps.source-types.v1",
            "ue_inspect_source_function.py": "ue-itps.source-function.v1",
            "ue_inspect_cs_function.py": "ue-itps.cs-function.v1",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            for script, schema in cases.items():
                suffix = ".cs" if script == "ue_inspect_cs_function.py" else ".cpp"
                missing = Path(temporary_directory) / f"Missing{suffix}"
                arguments = ["--source", str(missing)]
                if script in {
                    "ue_inspect_source_function.py",
                    "ue_inspect_cs_function.py",
                }:
                    arguments.extend(["--function", "Missing"])
                with self.subTest(script=script):
                    completed = run_cli(script, *arguments)
                    self.assertEqual(completed.returncode, 2)
                    self.assertEqual(completed.stderr, "")
                    result = json.loads(completed.stdout)
                    self.assert_envelope(result)
                    self.assertEqual(result["schema_version"], schema)
                    self.assertEqual(result["request"]["status"], "failed")
                    self.assertEqual(result["validation"]["status"], "error")
