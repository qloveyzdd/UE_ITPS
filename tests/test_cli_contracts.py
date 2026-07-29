from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from tests.support import (
    CliTestCase,
    PUBLIC_CLIS,
    REQUIRED_PATH_ARGUMENTS,
    SCHEMAS_ROOT,
    TOOLS_ROOT,
    run_cli,
    validator_for,
    write_text,
)
from ue_project_tools.common import result_document, validation_result


class CliContractTests(CliTestCase):
    def test_public_cli_inventory_matches_contract(self) -> None:
        actual = {path.name for path in TOOLS_ROOT.glob("ue_*.py")}
        self.assertEqual(actual, set(PUBLIC_CLIS))

    def test_every_public_cli_has_exactly_one_schema(self) -> None:
        actual = {
            path.name
            for path in SCHEMAS_ROOT.glob("ue_*.schema.json")
        }
        expected = {
            f"{Path(script).stem}.schema.json"
            for script in PUBLIC_CLIS
        }
        self.assertEqual(actual, expected)

    def test_all_schema_documents_are_valid_draft_2020_12(self) -> None:
        for path in sorted(SCHEMAS_ROOT.glob("*.schema.json")):
            with self.subTest(schema=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema)

    def test_all_public_clis_offer_bilingual_help(self) -> None:
        for script in PUBLIC_CLIS:
            with self.subTest(script=script):
                completed = run_cli(script, "--help")
                self.assertEqual(completed.returncode, 0)
                self.assertEqual(completed.stderr, "")
                self.assertIn("退出码", completed.stdout)
                self.assertIn("Exit codes", completed.stdout)
                self.assertIn("输出契约", completed.stdout)
                self.assertIn("Output contract", completed.stdout)

    def test_missing_required_arguments_use_argument_failure(self) -> None:
        for script in REQUIRED_PATH_ARGUMENTS:
            with self.subTest(script=script):
                result = self.cli(script, expected_code=2)
                self.assert_request_failure(result, kind="argument")

    def test_unknown_arguments_use_argument_failure(self) -> None:
        for script in PUBLIC_CLIS:
            with self.subTest(script=script):
                result = self.cli(
                    script,
                    "--not-a-real-option",
                    expected_code=2,
                )
                self.assert_request_failure(result, kind="argument")

    def test_missing_input_paths_use_input_failure(self) -> None:
        missing = self.fixture.root / "Missing.input"
        for script, argument in REQUIRED_PATH_ARGUMENTS.items():
            extra = (
                ("--function", "MissingFunction")
                if script
                in {"ue_inspect_cs_function.py", "ue_inspect_cxx_function.py"}
                else ()
            )
            with self.subTest(script=script):
                result = self.cli(
                    script,
                    argument,
                    str(missing),
                    *extra,
                    expected_code=2,
                )
                self.assert_request_failure(result, kind="input")

    def test_discovery_defaults_to_process_working_directory(self) -> None:
        result = self.cli(
            "ue_find_projects.py",
            cwd=self.fixture.project_root,
        )
        self.assertEqual(result["status"], "selected")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(
            result["candidates"],
            [self.fixture.project.as_posix()],
        )

    def test_success_and_error_documents_validate_for_every_cli(self) -> None:
        for script in PUBLIC_CLIS:
            with self.subTest(script=script):
                error_document = {
                    "schema_version": PUBLIC_CLIS[script],
                    "request": {"status": "failed", "kind": "input"},
                    "validation": {
                        "status": "error",
                        "problem_count": 1,
                        "problems": [
                            {
                                "severity": "error",
                                "code": "synthetic-input-failure",
                                "message": "Synthetic contract test.",
                            }
                        ],
                    },
                    "limits": {
                        "responsibility": "Contract test.",
                        "boundaries": [],
                    },
                }
                self.assertEqual(
                    list(validator_for(script).iter_errors(error_document)),
                    [],
                )

    def test_result_document_preserves_public_field_order(self) -> None:
        document = result_document(
            "ue-itps.example.v1",
            {"facts": [1, 2]},
            [],
            responsibility="Test result assembly.",
            boundaries=["Synthetic boundary."],
        )
        self.assertEqual(
            list(document),
            ["schema_version", "facts", "validation", "limits"],
        )

    def test_result_document_rejects_reserved_domain_fields(self) -> None:
        for field in ("schema_version", "validation", "limits"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    result_document(
                        "ue-itps.example.v1",
                        {field: "collision"},
                        [],
                        responsibility="Test reserved fields.",
                        boundaries=[],
                    )

    def test_validation_status_uses_highest_severity(self) -> None:
        warning = {
            "severity": "warning",
            "code": "warning",
            "message": "warning",
        }
        error = {
            "severity": "error",
            "code": "error",
            "message": "error",
        }
        self.assertEqual(validation_result([])["status"], "ok")
        self.assertEqual(validation_result([warning])["status"], "warning")
        self.assertEqual(
            validation_result([warning, error])["status"],
            "error",
        )

    def test_strict_json_rejects_duplicate_keys(self) -> None:
        from ue_project_tools.common import read_json

        path = write_text(
            self.fixture.root / "Duplicate.uproject",
            '{"FileVersion": 3, "FileVersion": 4}',
        )
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            read_json(path)

    def test_strict_json_rejects_nonstandard_constants(self) -> None:
        from ue_project_tools.common import read_json

        path = write_text(
            self.fixture.root / "NaN.uproject",
            '{"FileVersion": NaN}',
        )
        with self.assertRaises(ValueError):
            read_json(path)

    def test_strict_json_requires_object_root(self) -> None:
        from ue_project_tools.common import read_json

        path = write_text(self.fixture.root / "Array.uproject", "[]")
        with self.assertRaises(ValueError):
            read_json(path)
