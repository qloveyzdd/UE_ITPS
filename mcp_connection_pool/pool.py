from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import re
from typing import Any

from .models import (
    CandidateAssessment,
    ConnectionStatus,
    LookupResult,
    McpConnection,
    ProviderRequirement,
)


Discovery = Callable[[], Iterable[McpConnection]]

_CAPABILITY_TOOL_MARKERS: dict[str, tuple[str, ...]] = {
    "unreal.asset_registry": ("asset_registry", "assetregistry"),
    "unreal.blueprint": ("blueprint",),
    "unreal.blueprint_graph": (
        "blueprint_graph",
        "blueprintgraph",
        "k2node",
        "inspect_blueprint",
    ),
}


def _problem(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _metadata_capabilities(metadata: Mapping[str, Any]) -> set[str]:
    raw = metadata.get("capabilities", ())
    if isinstance(raw, str):
        return {item.strip() for item in raw.split(",") if item.strip()}
    if isinstance(raw, Iterable) and not isinstance(raw, (bytes, Mapping)):
        return {str(item).strip() for item in raw if str(item).strip()}
    return set()


def _observed_capabilities(connection: McpConnection) -> set[str]:
    capabilities = _metadata_capabilities(connection.metadata)
    lowered_tools = "\n".join(connection.tool_names).casefold()
    for capability, markers in _CAPABILITY_TOOL_MARKERS.items():
        if any(marker in lowered_tools for marker in markers):
            capabilities.add(capability)
    return capabilities


def _engine_version(metadata: Mapping[str, Any]) -> tuple[int, int] | None:
    raw = metadata.get("engine_version", metadata.get("ue_version"))
    if isinstance(raw, Mapping):
        try:
            return int(raw["major"]), int(raw["minor"])
        except (KeyError, TypeError, ValueError):
            return None
    match = re.search(r"(?<!\d)(\d+)\.(\d+)(?:\.\d+)?", str(raw or ""))
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _normalized_project(value: str) -> str:
    normalized = re.sub(r"/+", "/", value.replace("\\", "/")).rstrip("/")
    if re.match(r"^[A-Za-z]:/", normalized):
        return normalized.casefold()
    return normalized


def _declares_read_only(metadata: Mapping[str, Any]) -> bool:
    if metadata.get("read_only") is True:
        return True
    return str(metadata.get("access") or "").casefold() in {
        "read_only",
        "readonly",
        "read-only",
    }


def _is_ue_candidate(connection: McpConnection, requirement: ProviderRequirement) -> bool:
    metadata = connection.metadata
    if metadata.get("provider_id") == requirement.provider_id:
        return True
    kind = str(metadata.get("kind") or "").casefold().replace("_", "-")
    if kind == requirement.kind.casefold():
        return True
    identity = f"{connection.server_id}\n{connection.display_name}".casefold()
    return "unreal" in identity or "ue5" in identity


def _assess(
    connection: McpConnection,
    requirement: ProviderRequirement,
) -> CandidateAssessment:
    problems: list[dict[str, str]] = []
    if not connection.healthy:
        problems.append(_problem("connection-unhealthy", "连接当前不可调用。"))

    version = _engine_version(connection.metadata)
    expected = (requirement.engine_major, requirement.engine_minor)
    if version is None:
        problems.append(
            _problem("engine-version-not-declared", "连接未声明 Unreal Engine 版本。")
        )
    elif version != expected:
        problems.append(
            _problem(
                "engine-version-mismatch",
                f"连接使用 UE {version[0]}.{version[1]}，要求 UE {expected[0]}.{expected[1]}。",
            )
        )

    if requirement.require_read_only and not _declares_read_only(connection.metadata):
        problems.append(
            _problem("read-only-not-declared", "连接未声明只读访问属性。")
        )

    observed = _observed_capabilities(connection)
    missing = sorted(requirement.required_capabilities - observed)
    if missing:
        problems.append(
            _problem(
                "capabilities-missing",
                "连接缺少能力：" + ", ".join(missing),
            )
        )

    if requirement.project_file is not None:
        declared_project = connection.metadata.get("project_file")
        if not declared_project:
            problems.append(
                _problem("project-not-declared", "连接未声明当前绑定的 .uproject。")
            )
        elif _normalized_project(str(declared_project)) != _normalized_project(
            requirement.project_file
        ):
            problems.append(
                _problem("project-mismatch", "连接绑定的工程与目标 .uproject 不一致。")
            )

    return CandidateAssessment(
        connection=connection,
        compatible=not problems,
        problems=tuple(problems),
    )


class ExternalMcpConnectionPool:
    """A passive catalogue of MCP connections already exposed by the host.

    The pool deliberately has no start, reconnect, stop, process, or command API.
    Every resolve refreshes host inventory so a user can connect an MCP externally
    and continue the same task without restarting this pool.
    """

    def __init__(self, discover_connections: Discovery) -> None:
        self._discover_connections = discover_connections
        self._connections: tuple[McpConnection, ...] = ()

    def refresh(self) -> tuple[McpConnection, ...]:
        discovered = tuple(self._discover_connections())
        server_ids = [connection.server_id for connection in discovered]
        if len(server_ids) != len(set(server_ids)):
            raise ValueError("Host inventory returned duplicate MCP server ids")
        self._connections = tuple(
            sorted(discovered, key=lambda item: item.server_id.casefold())
        )
        return self._connections

    def snapshot(self) -> tuple[McpConnection, ...]:
        return self._connections

    def resolve(self, requirement: ProviderRequirement) -> LookupResult:
        connections = self.refresh()
        candidates = tuple(
            _assess(connection, requirement)
            for connection in connections
            if _is_ue_candidate(connection, requirement)
        )
        if not candidates:
            return LookupResult(
                requirement=requirement,
                status=ConnectionStatus.MISSING,
                connection=None,
                candidates=(),
            )

        compatible = tuple(candidate for candidate in candidates if candidate.compatible)
        if len(compatible) > 1:
            return LookupResult(
                requirement=requirement,
                status=ConnectionStatus.AMBIGUOUS,
                connection=None,
                candidates=candidates,
                problems=(
                    _problem(
                        "multiple-compatible-connections",
                        "存在多个满足要求的连接，不能静默选择。",
                    ),
                ),
            )
        if len(compatible) == 1:
            return LookupResult(
                requirement=requirement,
                status=ConnectionStatus.AVAILABLE,
                connection=compatible[0].connection,
                candidates=candidates,
            )

        all_problems = tuple(
            problem for candidate in candidates for problem in candidate.problems
        )
        status = (
            ConnectionStatus.UNHEALTHY
            if all(
                any(problem["code"] == "connection-unhealthy" for problem in item.problems)
                for item in candidates
            )
            else ConnectionStatus.INCOMPATIBLE
        )
        return LookupResult(
            requirement=requirement,
            status=status,
            connection=None,
            candidates=candidates,
            problems=all_problems,
        )
