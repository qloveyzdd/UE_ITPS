from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from mcp_connection_pool import (
    ConnectionStatus,
    ExternalMcpConnectionPool,
    McpConnection,
    UE58_PROVIDER_ID,
    connections_from_tool_inventory,
    get_provider_requirement,
    list_provider_ids,
)


CAPABILITIES = [
    "unreal.asset_registry",
    "unreal.blueprint",
    "unreal.blueprint_graph",
]


def ue_connection(
    server_id: str = "ue58",
    *,
    version: str = "5.8.1",
    project_file: str = "E:/Games/Sample/Sample.uproject",
    healthy: bool = True,
) -> McpConnection:
    return McpConnection(
        server_id=server_id,
        display_name="UE 5.8 Editor MCP",
        tool_names=(
            f"mcp__{server_id}__get_asset_registry",
            f"mcp__{server_id}__list_blueprints",
            f"mcp__{server_id}__inspect_blueprint_graph",
        ),
        metadata={
            "provider_id": UE58_PROVIDER_ID,
            "kind": "unreal-editor",
            "engine_version": version,
            "project_file": project_file,
            "access": "read_only",
            "capabilities": CAPABILITIES,
        },
        healthy=healthy,
    )


class SequenceDiscovery:
    def __init__(self, *snapshots: tuple[McpConnection, ...]) -> None:
        self.snapshots = list(snapshots)
        self.calls = 0

    def __call__(self):
        index = min(self.calls, len(self.snapshots) - 1)
        self.calls += 1
        return self.snapshots[index]


class PassiveConnectionPoolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.requirement = get_provider_requirement(
            UE58_PROVIDER_ID,
            project_file="e:\\games\\sample\\Sample.uproject",
        )

    def test_registry_contains_only_ue58(self) -> None:
        self.assertEqual(list_provider_ids(), (UE58_PROVIDER_ID,))

    def test_missing_connection_requires_user_action(self) -> None:
        result = ExternalMcpConnectionPool(lambda: ()).resolve(self.requirement)
        self.assertEqual(result.status, ConnectionStatus.MISSING)
        document = result.to_dict()
        self.assertEqual(document["user_action"]["code"], "ue58_mcp_not_connected")
        self.assertTrue(document["user_action"]["retryable"])

    def test_unique_compatible_connection_is_available(self) -> None:
        connection = ue_connection()
        result = ExternalMcpConnectionPool(lambda: (connection,)).resolve(
            self.requirement
        )
        self.assertTrue(result.available)
        self.assertIs(result.connection, connection)
        self.assertIsNone(result.to_dict()["user_action"])

    def test_pool_refreshes_after_user_connects_externally(self) -> None:
        connection = ue_connection()
        discovery = SequenceDiscovery((), (connection,))
        pool = ExternalMcpConnectionPool(discovery)
        self.assertEqual(pool.resolve(self.requirement).status, ConnectionStatus.MISSING)
        self.assertEqual(pool.resolve(self.requirement).status, ConnectionStatus.AVAILABLE)
        self.assertEqual(discovery.calls, 2)

    def test_pool_never_starts_an_external_process(self) -> None:
        with patch.object(
            subprocess,
            "Popen",
            side_effect=AssertionError("connection pool must not launch a process"),
        ), patch.object(
            subprocess,
            "run",
            side_effect=AssertionError("connection pool must not run a command"),
        ):
            result = ExternalMcpConnectionPool(lambda: ()).resolve(self.requirement)
        self.assertEqual(result.status, ConnectionStatus.MISSING)

    def test_wrong_engine_version_is_incompatible(self) -> None:
        result = ExternalMcpConnectionPool(
            lambda: (ue_connection(version="5.7.4"),)
        ).resolve(self.requirement)
        self.assertEqual(result.status, ConnectionStatus.INCOMPATIBLE)
        self.assertIn(
            "engine-version-mismatch",
            {problem["code"] for problem in result.problems},
        )

    def test_wrong_project_is_incompatible(self) -> None:
        result = ExternalMcpConnectionPool(
            lambda: (ue_connection(project_file="E:/Games/Other/Other.uproject"),)
        ).resolve(self.requirement)
        self.assertEqual(result.status, ConnectionStatus.INCOMPATIBLE)
        self.assertIn(
            "project-mismatch",
            {problem["code"] for problem in result.problems},
        )

    def test_multiple_compatible_connections_are_ambiguous(self) -> None:
        result = ExternalMcpConnectionPool(
            lambda: (ue_connection("ue58_a"), ue_connection("ue58_b"))
        ).resolve(self.requirement)
        self.assertEqual(result.status, ConnectionStatus.AMBIGUOUS)
        self.assertIsNone(result.connection)

    def test_unhealthy_matching_connection_is_reported(self) -> None:
        result = ExternalMcpConnectionPool(
            lambda: (ue_connection(healthy=False),)
        ).resolve(self.requirement)
        self.assertEqual(result.status, ConnectionStatus.UNHEALTHY)

    def test_inventory_adapter_groups_only_host_visible_mcp_tools(self) -> None:
        connections = connections_from_tool_inventory(
            [
                "shell_command",
                "mcp__ue58__get_asset_registry",
                "mcp__ue58__inspect_blueprint_graph",
                "mcp__github__read_issue",
            ],
            metadata_by_server={
                "ue58": {
                    "display_name": "UE 5.8",
                    "engine_version": "5.8.0",
                }
            },
        )
        self.assertEqual([item.server_id for item in connections], ["github", "ue58"])
        ue58 = connections[1]
        self.assertEqual(ue58.display_name, "UE 5.8")
        self.assertEqual(len(ue58.tool_names), 2)


if __name__ == "__main__":
    unittest.main()
