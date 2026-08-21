from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT / "tests", ROOT / "information_pool", ROOT / "sourcetools", ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from support import create_fixture  # noqa: E402
from ue_file_graph import build_file_graph  # noqa: E402


class FileGraphTests(unittest.TestCase):
    def test_builds_project_to_include_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            output = Path(directory) / "sample.sqlite3"
            summary = build_file_graph(fixture.project, output)

            self.assertTrue(output.is_file())
            self.assertGreater(summary["node_count"], 0)
            connection = sqlite3.connect(output)
            try:
                node_kinds = {
                    row[0]
                    for row in connection.execute("SELECT DISTINCT kind FROM nodes")
                }
                edge_kinds = {
                    row[0]
                    for row in connection.execute("SELECT DISTINCT kind FROM edges")
                }
                self.assertTrue(
                    {
                        "project_file",
                        "plugin_file",
                        "target_file",
                        "module_rules_file",
                        "source_file",
                    }.issubset(node_kinds)
                )
                self.assertTrue(
                    {
                        "DECLARES_TARGET",
                        "DECLARES_MODULE",
                        "ENABLES_PLUGIN",
                        "REFERENCES_MODULE",
                        "DEPENDS_ON_MODULE",
                        "CONTAINS_FILE",
                        "INCLUDES",
                    }.issubset(edge_kinds)
                )
                missing_evidence = connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM edges e
                    LEFT JOIN edge_evidence x ON x.edge_id = e.edge_id
                    WHERE x.evidence_id IS NULL
                    """
                ).fetchone()[0]
                self.assertEqual(missing_evidence, 0)
                self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
                plan = connection.execute(
                    "EXPLAIN QUERY PLAN SELECT * FROM edges WHERE source_id = ?",
                    ("node",),
                ).fetchall()
                self.assertTrue(any("idx_edges_source" in str(row) for row in plan))
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
