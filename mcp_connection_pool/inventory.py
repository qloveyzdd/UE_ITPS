from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from .models import McpConnection


def _split_mcp_tool_name(value: str) -> tuple[str, str] | None:
    parts = value.split("__", 2)
    if len(parts) != 3 or parts[0] != "mcp" or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def connections_from_tool_inventory(
    tool_names: Iterable[str],
    *,
    metadata_by_server: Mapping[str, Mapping[str, Any]] | None = None,
    unhealthy_servers: Iterable[str] = (),
) -> tuple[McpConnection, ...]:
    """Project host-visible MCP tools into passive connection records.

    This function never starts, reconnects, probes, or stops an MCP server.
    """

    grouped: dict[str, set[str]] = defaultdict(set)
    for value in tool_names:
        parsed = _split_mcp_tool_name(value)
        if parsed is None:
            continue
        server_id, _tool_name = parsed
        grouped[server_id].add(value)

    metadata_index = metadata_by_server or {}
    unhealthy = set(unhealthy_servers)
    connections = []
    for server_id in sorted(grouped, key=str.casefold):
        metadata = dict(metadata_index.get(server_id, {}))
        connections.append(
            McpConnection(
                server_id=server_id,
                display_name=str(metadata.get("display_name") or server_id),
                tool_names=tuple(grouped[server_id]),
                metadata=metadata,
                healthy=server_id not in unhealthy,
            )
        )
    return tuple(connections)
