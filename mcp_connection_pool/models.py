from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class ConnectionStatus(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    INCOMPATIBLE = "incompatible"
    AMBIGUOUS = "ambiguous"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class McpConnection:
    """A connection that is already owned and exposed by the host."""

    server_id: str
    display_name: str
    tool_names: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)
    healthy: bool = True

    def __post_init__(self) -> None:
        if not self.server_id.strip():
            raise ValueError("server_id must not be empty")
        if not self.display_name.strip():
            raise ValueError("display_name must not be empty")
        object.__setattr__(
            self,
            "tool_names",
            tuple(sorted(set(self.tool_names), key=str.casefold)),
        )
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "display_name": self.display_name,
            "healthy": self.healthy,
            "tool_names": list(self.tool_names),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ProviderRequirement:
    provider_id: str
    kind: str
    engine_major: int
    engine_minor: int
    required_capabilities: frozenset[str]
    require_read_only: bool = True
    project_file: str | None = None

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider_id must not be empty")
        if not self.kind.strip():
            raise ValueError("kind must not be empty")
        if self.engine_major < 0 or self.engine_minor < 0:
            raise ValueError("engine version must not be negative")

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "kind": self.kind,
            "engine_version": f"{self.engine_major}.{self.engine_minor}.*",
            "required_capabilities": sorted(self.required_capabilities),
            "require_read_only": self.require_read_only,
            "project_file": self.project_file,
        }


@dataclass(frozen=True)
class CandidateAssessment:
    connection: McpConnection
    compatible: bool
    problems: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = self.connection.to_dict()
        result["compatible"] = self.compatible
        result["problems"] = [dict(problem) for problem in self.problems]
        return result


_USER_ACTIONS: dict[ConnectionStatus, tuple[str, str]] = {
    ConnectionStatus.MISSING: (
        "ue58_mcp_not_connected",
        "未发现已连接的 UE 5.8 MCP。请启动并连接对应 MCP，然后继续当前任务。",
    ),
    ConnectionStatus.INCOMPATIBLE: (
        "ue58_mcp_incompatible",
        "发现了 UE MCP，但其版本、工程、权限或能力与当前要求不兼容。",
    ),
    ConnectionStatus.AMBIGUOUS: (
        "ue58_mcp_ambiguous",
        "发现多个兼容的 UE 5.8 MCP 连接，请明确选择目标连接。",
    ),
    ConnectionStatus.UNHEALTHY: (
        "ue58_mcp_unhealthy",
        "发现了匹配的 UE 5.8 MCP，但连接当前不可调用。请检查外部 MCP 后继续。",
    ),
}


@dataclass(frozen=True)
class LookupResult:
    requirement: ProviderRequirement
    status: ConnectionStatus
    connection: McpConnection | None
    candidates: tuple[CandidateAssessment, ...]
    problems: tuple[dict[str, str], ...] = ()

    @property
    def available(self) -> bool:
        return self.status is ConnectionStatus.AVAILABLE

    def to_dict(self) -> dict[str, Any]:
        action = _USER_ACTIONS.get(self.status)
        return {
            "schema_version": "ue-itps.mcp-connection-lookup",
            "provider": self.requirement.to_dict(),
            "status": self.status.value,
            "connection": (
                self.connection.to_dict() if self.connection is not None else None
            ),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "problems": [dict(problem) for problem in self.problems],
            "user_action": (
                {
                    "required": True,
                    "code": action[0],
                    "message": action[1],
                    "retryable": True,
                }
                if action is not None
                else None
            ),
        }
