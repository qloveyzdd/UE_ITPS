from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from tests.support import ROOT, run_cli


class PublicContractTests(unittest.TestCase):
    def test_tool_manifest_matches_entrypoints_and_schemas(self) -> None:
        completed, manifest = run_cli("sourcetools/ue_list_tools.py")
        self.assertEqual(completed.returncode, 0)
        entrypoints = {path.name for path in (ROOT / "sourcetools").glob("ue_*.py")}
        declared = {Path(item["entrypoint"]).name for item in manifest["items"]}
        schemas = {
            path.stem.removesuffix(".schema")
            for path in (ROOT / "schemas").glob("ue_*.schema.json")
        }
        self.assertEqual(declared, entrypoints)
        self.assertEqual(schemas, {path.removesuffix(".py") for path in entrypoints})
        self.assertEqual(manifest["tool_count"], len(entrypoints))

    def test_every_schema_is_valid_draft_2020_12(self) -> None:
        for path in sorted((ROOT / "schemas").glob("*.schema.json")):
            with self.subTest(schema=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
                Draft202012Validator.check_schema(schema)

    def test_every_cli_exposes_help(self) -> None:
        for path in sorted((ROOT / "sourcetools").glob("ue_*.py")):
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

    def test_manifest_output_validates_against_its_schema(self) -> None:
        _, manifest = run_cli("sourcetools/ue_list_tools.py")
        schema = json.loads(
            (ROOT / "schemas" / "ue_list_tools.schema.json").read_text(encoding="utf-8")
        )
        common = json.loads(
            (ROOT / "schemas" / "common.schema.json").read_text(encoding="utf-8")
        )
        registry = Registry().with_resource(
            common["$id"], Resource.from_contents(common)
        )
        Draft202012Validator(schema, registry=registry).validate(manifest)


if __name__ == "__main__":
    unittest.main()
