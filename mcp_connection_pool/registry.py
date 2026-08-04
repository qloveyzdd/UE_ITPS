from __future__ import annotations

from .models import ProviderRequirement


UE58_PROVIDER_ID = "ue5.8-editor"

_UE58_CAPABILITIES = frozenset(
    {
        "unreal.asset_registry",
        "unreal.blueprint",
        "unreal.blueprint_graph",
    }
)


def list_provider_ids() -> tuple[str, ...]:
    """Return the only provider supported by the initial connection pool."""

    return (UE58_PROVIDER_ID,)


def get_provider_requirement(
    provider_id: str,
    *,
    project_file: str | None = None,
) -> ProviderRequirement:
    if provider_id != UE58_PROVIDER_ID:
        raise KeyError(f"Unsupported MCP provider: {provider_id}")
    return ProviderRequirement(
        provider_id=UE58_PROVIDER_ID,
        kind="unreal-editor",
        engine_major=5,
        engine_minor=8,
        required_capabilities=_UE58_CAPABILITIES,
        require_read_only=True,
        project_file=project_file,
    )
