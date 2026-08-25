from __future__ import annotations

import unittest

from mcp_connection_pool import (
    ConnectionStatus,
    ExternalMcpConnectionPool,
    McpConnection,
    get_provider_requirement,
)


def connection(server_id: str, *, version: str = "5.8.2", project: str = "D:/Sample/Sample.uproject") -> McpConnection:
    return McpConnection(
        server_id=server_id,
        display_name=server_id,
        healthy=True,
        tool_names=("asset_registry", "blueprint", "blueprint_graph"),
        metadata={
            "kind": "unreal-editor",
            "engine_version": version,
            "read_only": True,
            "project_file": project,
        },
    )


class ConnectionPoolTests(unittest.TestCase):
    def test_missing_connection_requires_external_action(self) -> None:
        result = ExternalMcpConnectionPool(lambda: ()).resolve(get_provider_requirement("ue5.8-editor"))
        self.assertEqual(result.status, ConnectionStatus.MISSING)
        self.assertIsNone(result.connection)

    def test_unique_compatible_connection_is_selected(self) -> None:
        expected = connection("ue-editor")
        result = ExternalMcpConnectionPool(lambda: (expected,)).resolve(
            get_provider_requirement("ue5.8-editor", project_file="D:/Sample/Sample.uproject")
        )
        self.assertEqual(result.status, ConnectionStatus.AVAILABLE)
        self.assertEqual(result.connection, expected)

    def test_wrong_engine_version_is_incompatible(self) -> None:
        result = ExternalMcpConnectionPool(lambda: (connection("ue-editor", version="5.7.0"),)).resolve(
            get_provider_requirement("ue5.8-editor")
        )
        self.assertEqual(result.status, ConnectionStatus.INCOMPATIBLE)
        self.assertIn("engine-version-mismatch", {item["code"] for item in result.problems})

    def test_multiple_compatible_connections_are_ambiguous(self) -> None:
        result = ExternalMcpConnectionPool(lambda: (connection("a"), connection("b"))).resolve(
            get_provider_requirement("ue5.8-editor")
        )
        self.assertEqual(result.status, ConnectionStatus.AMBIGUOUS)
        self.assertIsNone(result.connection)


if __name__ == "__main__":
    unittest.main()
