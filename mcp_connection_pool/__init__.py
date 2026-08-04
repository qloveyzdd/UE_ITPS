"""Passive discovery of externally owned MCP connections."""

from .inventory import connections_from_tool_inventory
from .models import (
    ConnectionStatus,
    LookupResult,
    McpConnection,
    ProviderRequirement,
)
from .pool import ExternalMcpConnectionPool
from .registry import (
    UE58_PROVIDER_ID,
    get_provider_requirement,
    list_provider_ids,
)

__all__ = [
    "ConnectionStatus",
    "ExternalMcpConnectionPool",
    "LookupResult",
    "McpConnection",
    "ProviderRequirement",
    "UE58_PROVIDER_ID",
    "connections_from_tool_inventory",
    "get_provider_requirement",
    "list_provider_ids",
]
