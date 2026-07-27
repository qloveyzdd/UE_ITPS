from __future__ import annotations

import json
from pathlib import Path
import tempfile

from tests.fixture import (
    CLI_SCHEMAS,
    EnvelopeAssertions,
    SOURCE_CLIS,
    TOOLS_ROOT,
    run_cli,
    write_text,
)
from ue_project_tools.common import read_json, result_document, validation_result


class ContractSurfaceTests(EnvelopeAssertions):
    def test_public_cli_inventory_is_explicit_and_complete(self) -> None:
        declared = set(CLI_SCHEMAS)
        present = {path.name for path in TOOLS_ROOT.glob("ue_*.py") if path.is_file()}
        self.assertEqual(present, declared)
        self.assertEqual(len(declared), 15)
        self.assertEqual(len(set(CLI_SCHEMAS.values())), 15)

    def test_every_cli_help_is_bilingual_and_declares_exit_codes(self) -> None:
        for script in CLI_SCHEMAS:
            with self.subTest(script=script):
                completed = run_cli(script, "--help")
                self.assertEqual(completed.returncode, 0)
                self.assertEqual(completed.stderr, "")
                self.assertIn("用法 / usage:", completed.stdout)
                self.assertIn("输出契约 / Output contract:", completed.stdout)
                self.assertIn("退出码 / Exit codes:", completed.stdout)

    def test_missing_required_arguments_use_argparse_exit_two(self) -> None:
        scripts_with_required_arguments = set(CLI_SCHEMAS) - {"ue_find_projects.py"}
        for script in scripts_with_required_arguments:
            with self.subTest(script=script):
                completed = run_cli(script)
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stdout, "")
                self.assertIn("用法 / usage:", completed.stderr)

    def test_result_document_keeps_order_and_rejects_reserved_content(self) -> None:
        result = result_document(
            "example.v1",
            {"facts": [1]},
            [],
            responsibility="Return example facts.",
            boundaries=["Does not inspect Unreal."],
        )
        self.assert_envelope(result)
        self.assertEqual(
            list(result),
            ["schema_version", "facts", "validation", "limits"],
        )
        with self.assertRaisesRegex(ValueError, "reserved fields"):
            result_document(
                "example.v1",
                {"validation": {}},
                [],
                responsibility="Invalid example.",
                boundaries=[],
            )

    def test_validation_status_uses_highest_problem_severity(self) -> None:
        self.assertEqual(validation_result([])["status"], "ok")
        self.assertEqual(
            validation_result([{"severity": "warning"}])["status"],
            "warning",
        )
        result = validation_result([{"severity": "warning"}, {"severity": "error"}])
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["problem_count"], 2)

    def test_strict_json_reader_rejects_duplicates_and_constants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            duplicate = temporary_root / "duplicate.json"
            constant = temporary_root / "constant.json"
            write_text(duplicate, '{"Name": "first", "Name": "second"}')
            write_text(constant, '{"Value": NaN}')

            with self.assertRaisesRegex(ValueError, "Duplicate JSON object key"):
                read_json(duplicate)
            with self.assertRaisesRegex(ValueError, "Non-standard JSON constant"):
                read_json(constant)

    def test_source_clis_report_missing_files_as_schema_json(self) -> None:
        missing = str(TOOLS_ROOT / "does-not-exist.cpp")
        arguments = {
            "ue_inspect_cs_function.py": [
                "--source",
                missing,
                "--function",
                "Missing",
            ],
            "ue_list_cxx_includes.py": ["--source", missing],
            "ue_list_cxx_types.py": ["--source", missing],
            "ue_inspect_cxx_function.py": [
                "--source",
                missing,
                "--function",
                "Missing",
            ],
        }
        for script in SOURCE_CLIS:
            with self.subTest(script=script):
                completed = run_cli(script, *arguments[script])
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stderr, "")
                result = json.loads(completed.stdout)
                self.assertEqual(result["schema_version"], CLI_SCHEMAS[script])
                self.assertEqual(result["request"], {"status": "failed"})
                self.assertEqual(result["validation"]["status"], "error")
                self.assert_envelope(result)
