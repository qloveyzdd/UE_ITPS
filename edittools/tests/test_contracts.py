from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"


class ContractTests(unittest.TestCase):
    def test_each_cli_has_one_schema(self) -> None:
        scripts = {path.stem for path in ROOT.glob("ue_*.py")}
        schemas = {
            path.name.removesuffix(".schema.json")
            for path in SCHEMAS.glob("ue_*.schema.json")
        }
        self.assertEqual(scripts, schemas)

    def test_schemas_are_valid_draft_2020_12(self) -> None:
        for path in sorted(SCHEMAS.glob("*.schema.json")):
            with self.subTest(schema=path.name):
                Draft202012Validator.check_schema(
                    json.loads(path.read_text(encoding="utf-8"))
                )

    def test_all_clis_have_bilingual_help(self) -> None:
        for script in sorted(ROOT.glob("ue_*.py")):
            with self.subTest(script=script.name):
                completed = subprocess.run(
                    [sys.executable, str(script), "--help"],
                    cwd=ROOT,
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0)
                self.assertEqual(completed.stderr, "")
                self.assertIn("输出契约", completed.stdout)
                self.assertIn("Output contract", completed.stdout)

    def test_argument_errors_return_json(self) -> None:
        for script in sorted(ROOT.glob("ue_*.py")):
            with self.subTest(script=script.name):
                completed = subprocess.run(
                    [sys.executable, str(script)],
                    cwd=ROOT,
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stderr, "")
                document = json.loads(completed.stdout)
                self.assertEqual(document["request"]["kind"], "argument")
                self.assertEqual(document["validation"]["status"], "error")

    def test_live_editor_clis_use_node_id_connection_contract(self) -> None:
        live_scripts = sorted(
            path
            for path in ROOT.glob("ue_editor_*.py")
            if path.name
            not in {"ue_editor_list_sessions.py", "ue_editor_export_message_graph.py"}
        )
        for script in live_scripts:
            with self.subTest(script=script.name):
                completed = subprocess.run(
                    [sys.executable, str(script), "--help"],
                    cwd=ROOT,
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                    check=False,
                )
                self.assertIn("--node-id", completed.stdout)
                self.assertNotIn("--project", completed.stdout)
                self.assertNotIn("--engine-root", completed.stdout)


if __name__ == "__main__":
    unittest.main()
