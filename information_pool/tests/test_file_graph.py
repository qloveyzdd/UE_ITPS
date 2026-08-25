from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT / "information_pool", ROOT / "sourcetools", ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ue_file_graph import build_file_graph  # noqa: E402


class FileGraphTests(unittest.TestCase):
    def test_builds_a_queryable_sqlite_graph_with_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "Sample.uproject"
            project.write_text(
                json.dumps(
                    {
                        "FileVersion": 3,
                        "Modules": [{"Name": "Sample", "Type": "Runtime"}],
                        "Plugins": [],
                    }
                ),
                encoding="utf-8",
            )
            module = root / "Source" / "Sample"
            module.mkdir(parents=True)
            (module / "Sample.Build.cs").write_text(
                "public class Sample : ModuleRules { public Sample(ReadOnlyTargetRules Target) : base(Target) {} }",
                encoding="utf-8",
            )
            (root / "Source" / "Sample.Target.cs").write_text(
                "public class SampleTarget : TargetRules { public SampleTarget(TargetInfo Target) : base(Target) { Type = TargetType.Game; ExtraModuleNames.Add(\"Sample\"); } }",
                encoding="utf-8",
            )
            private = module / "Private"
            public = module / "Public"
            private.mkdir()
            public.mkdir()
            (private / "Worker.cpp").write_text('#include "Worker.h"\n', encoding="utf-8")
            (public / "Worker.h").write_text("#pragma once\n", encoding="utf-8")
            output = root / "graph.sqlite3"

            summary = build_file_graph(project, output)
            self.assertEqual(summary["schema_version"], "ue-itps.file-graph.v1")
            self.assertGreater(summary["node_count"], 0)

            connection = sqlite3.connect(output)
            try:
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
                kinds = {row[0] for row in connection.execute("SELECT kind FROM edges")}
                self.assertIn("DECLARES_MODULE", kinds)
                self.assertIn("INCLUDES", kinds)
                missing_evidence = connection.execute(
                    "SELECT COUNT(*) FROM edges e LEFT JOIN edge_evidence x ON x.edge_id=e.edge_id WHERE x.evidence_id IS NULL"
                ).fetchone()[0]
                self.assertEqual(missing_evidence, 0)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
