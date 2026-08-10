from __future__ import annotations

from pathlib import Path
import unittest

from ue_editor_tools.project_context import ProjectContext
from ue_editor_tools.remote_client import (
    EditorConnectionError,
    _ProcessLock,
    select_session,
)


class RemoteSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = ProjectContext(
            project_file=Path("D:/Game/Game.uproject"),
            project_root=Path("D:/Game"),
            project_name="Game",
            engine_root=Path("D:/UE"),
            engine_version="5.8.2",
        )

    def test_selects_exact_project(self) -> None:
        node = {"project_root": "D:/Game/", "project_name": "Game", "node_id": "A"}
        self.assertEqual(select_session([node], self.context), node)

    def test_rejects_other_project(self) -> None:
        node = {"project_root": "D:/Other/", "project_name": "Other", "node_id": "A"}
        with self.assertRaises(EditorConnectionError):
            select_session([node], self.context)

    def test_multiple_sessions_require_node_id(self) -> None:
        nodes = [
            {"project_root": "D:/Game/", "project_name": "Game", "node_id": "A"},
            {"project_root": "D:/Game/", "project_name": "Game", "node_id": "B"},
        ]
        with self.assertRaises(EditorConnectionError):
            select_session(nodes, self.context)
        self.assertEqual(select_session(nodes, self.context, "B")["node_id"], "B")

    def test_process_lock_path_is_deterministic(self) -> None:
        self.assertEqual(
            _ProcessLock("D:/UE", 1).path,
            _ProcessLock("d:/ue", 1).path,
        )


if __name__ == "__main__":
    unittest.main()
