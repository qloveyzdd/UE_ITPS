from __future__ import annotations

import json
from pathlib import Path
import tempfile

from jsonschema import Draft202012Validator

from tests.support import (
    PATH_ARGUMENTS,
    PUBLIC_CLIS,
    REPOSITORY_ROOT,
    SCHEMAS_ROOT,
    TOOLS_ROOT,
    ContractAssertions,
    assert_schema_valid,
    parse_cli,
    run_cli,
)
from ue_project_tools.common import read_json, result_document, validation_result


class PublicContractTests(ContractAssertions):
    def test_public_cli_inventory_matches_declared_contract(self) -> None:
        actual = {path.name for path in TOOLS_ROOT.glob("ue_*.py")}
        self.assertEqual(actual, set(PUBLIC_CLIS))

    def test_every_public_cli_has_one_formal_schema(self) -> None:
        expected = {"common.schema.json"} | {
            f"{Path(script).stem}.schema.json" for script in PUBLIC_CLIS
        }
        actual = {path.name for path in SCHEMAS_ROOT.glob("*.schema.json")}
        self.assertEqual(actual, expected)

    def test_every_schema_is_valid_draft_2020_12(self) -> None:
        for path in sorted(SCHEMAS_ROOT.glob("*.schema.json")):
            with self.subTest(schema=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)
                self.assertTrue(schema["$id"].startswith("urn:ue-itps:schema:"))

    def test_every_cli_help_is_bilingual(self) -> None:
        for script in PUBLIC_CLIS:
            with self.subTest(script=script):
                completed = run_cli(script, "--help")
                self.assertEqual(completed.returncode, 0)
                self.assertEqual(completed.stderr, "")
                self.assertIn("用法 / usage:", completed.stdout)
                self.assertIn("Output contract", completed.stdout)

    def test_every_cli_help_documents_all_exit_codes(self) -> None:
        for script in PUBLIC_CLIS:
            with self.subTest(script=script):
                output = run_cli(script, "--help").stdout
                self.assertIn("0  扫描完成", output)
                self.assertIn("1  扫描完成但发现阻断问题", output)
                self.assertIn("2  参数、输入或读取失败", output)

    def test_missing_required_arguments_use_json_exit_two(self) -> None:
        required_argument_clis = set(PUBLIC_CLIS) - {"ue_find_projects.py"}
        for script in required_argument_clis:
            with self.subTest(script=script):
                result = parse_cli(self, script, expected_code=2)
                self.assert_request_failure(result, kind="argument")
                self.assertEqual(
                    result["validation"]["problems"][0]["code"],
                    "argument-error",
                )

    def test_project_discovery_defaults_to_current_directory(self) -> None:
        completed = run_cli("ue_find_projects.py")
        self.assertIn(completed.returncode, {0, 1})
        self.assertEqual(completed.stderr, "")
        result = json.loads(completed.stdout)
        self.assertNotIn("request", result)
        self.assertEqual(result["search_root"], REPOSITORY_ROOT.as_posix())
        assert_schema_valid(self, "ue_find_projects.py", result)

    def test_unknown_arguments_use_json_exit_two(self) -> None:
        for script in PUBLIC_CLIS:
            with self.subTest(script=script):
                result = parse_cli(
                    self,
                    script,
                    "--definitely-unknown",
                    expected_code=2,
                )
                self.assert_request_failure(result, kind="argument")

    def test_missing_paths_use_input_failure_envelope(self) -> None:
        missing = REPOSITORY_ROOT / "does-not-exist" / "missing.file"
        for script, option in PATH_ARGUMENTS.items():
            arguments = [option, str(missing)]
            if script in {"ue_inspect_cs_function.py", "ue_inspect_cxx_function.py"}:
                arguments.extend(["--function", "Missing"])
            with self.subTest(script=script):
                result = parse_cli(
                    self,
                    script,
                    *arguments,
                    expected_code=2,
                )
                self.assert_request_failure(result, kind="input")

    def test_result_document_preserves_envelope_order(self) -> None:
        result = result_document(
            "sample.v1",
            {"facts": [1, 2]},
            [],
            responsibility="Test result assembly.",
            boundaries=["No runtime claim."],
        )
        self.assertEqual(
            list(result),
            ["schema_version", "facts", "validation", "limits"],
        )
        self.assert_result_contract(result)

    def test_result_document_rejects_reserved_fields(self) -> None:
        for field in {"schema_version", "validation", "limits"}:
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    result_document(
                        "sample.v1",
                        {field: "collision"},
                        [],
                        responsibility="Test.",
                        boundaries=[],
                    )

    def test_validation_uses_highest_problem_severity(self) -> None:
        warning = {"severity": "warning", "code": "w", "message": "warning"}
        error = {"severity": "error", "code": "e", "message": "error"}
        self.assertEqual(validation_result([])["status"], "ok")
        self.assertEqual(validation_result([warning])["status"], "warning")
        self.assertEqual(validation_result([error, warning])["status"], "error")

    def test_strict_json_reader_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"Name": "A", "Name": "B"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate JSON object key"):
                read_json(path)

    def test_strict_json_reader_rejects_nonstandard_constants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nan.json"
            path.write_text('{"Value": NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Non-standard JSON constant"):
                read_json(path)

    def test_strict_json_reader_requires_object_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "array.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Expected a JSON object"):
                read_json(path)

    def test_error_documents_validate_against_each_cli_schema(self) -> None:
        for script in PUBLIC_CLIS:
            with self.subTest(script=script):
                completed = run_cli(script)
                result = json.loads(completed.stdout)
                assert_schema_valid(self, script, result)


if __name__ == "__main__":
    import unittest

    unittest.main()
