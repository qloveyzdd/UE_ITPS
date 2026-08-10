from __future__ import annotations

from pathlib import Path
import json
from types import SimpleNamespace
import unittest

from ue_editor_tools.project_context import ProjectContext
from ue_editor_tools.remote_client import (
    EditorConnectionError,
    _ProcessLock,
    _receive_complete_message,
    select_session,
)


class _ChunkedSocket:
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = list(chunks)

    def recv(self, _size: int) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""


class _RemoteMessage:
    def __init__(self, _type: object, _source: object) -> None:
        self.type_ = ""
        self.dest = ""
        self.data: dict[str, object] = {}

    def from_json_bytes(self, value: bytes) -> bool:
        document = json.loads(value.decode("utf-8"))
        self.type_ = str(document["type"])
        self.dest = str(document["dest"])
        self.data = dict(document["data"])
        return True

    def passes_receive_filter(self, node_id: str) -> bool:
        return self.dest == node_id


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

    def test_receives_json_across_short_tcp_chunks(self) -> None:
        payload = json.dumps(
            {
                "type": "command_result",
                "source": "editor",
                "dest": "client",
                "data": {"success": True, "output": ["large-result"]},
            },
            separators=(",", ":"),
        ).encode("utf-8")
        connection = SimpleNamespace(
            _command_channel_socket=_ChunkedSocket(
                [payload[:17], payload[17:41], payload[41:]]
            ),
            _node_id="client",
        )

        message = _receive_complete_message(
            connection, "command_result", _RemoteMessage
        )

        self.assertEqual(message.data["output"], ["large-result"])


if __name__ == "__main__":
    unittest.main()
