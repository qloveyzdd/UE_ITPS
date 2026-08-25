from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]
EDITOR_ROOT = ROOT / "edittools"


class EditorContractTests(unittest.TestCase):
    def test_entrypoints_and_schemas_are_one_to_one(self) -> None:
        entrypoints = {path.stem for path in EDITOR_ROOT.glob("ue_*.py")}
        schemas = {
            path.name.removesuffix(".schema.json")
            for path in (EDITOR_ROOT / "schemas").glob("ue_*.schema.json")
        }
        self.assertEqual(entrypoints, schemas)

    def test_every_schema_is_valid_draft_2020_12(self) -> None:
        for path in sorted((EDITOR_ROOT / "schemas").glob("*.schema.json")):
            with self.subTest(schema=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                Draft202012Validator.check_schema(schema)

    def test_every_entrypoint_exposes_help(self) -> None:
        for path in sorted(EDITOR_ROOT.glob("ue_*.py")):
            with self.subTest(cli=path.name):
                completed = subprocess.run(
                    [sys.executable, str(path), "--help"],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=15,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn("usage:", completed.stdout)

if __name__ == "__main__":
    unittest.main()
