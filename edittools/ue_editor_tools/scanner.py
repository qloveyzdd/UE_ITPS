from __future__ import annotations

from typing import Any

from .remote_client import EditorSession


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def scan_gameplay_messages(
    session: EditorSession,
    *,
    roots: list[str] | None = None,
    assets: list[str] | None = None,
    tags: list[str] | None = None,
    batch_size: int = 20,
    include_referencers: bool = True,
) -> dict[str, Any]:
    if batch_size < 1 or batch_size > 100:
        raise ValueError("batch_size must be between 1 and 100")
    state = session.invoke("editor_state")
    if assets:
        selected_assets = sorted(set(assets), key=str.casefold)
        selected_roots = sorted(set(roots or []), key=str.casefold)
    else:
        inventory = session.invoke("list_blueprint_assets", {"roots": roots or None})
        selected_roots = list(inventory["roots"])
        selected_assets = [str(item["package"]) for item in inventory["assets"]]

    scanned_assets: list[str] = []
    operations: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for batch in _chunks(selected_assets, batch_size):
        result = session.invoke("scan_blueprint_batch", {"asset_paths": batch})
        scanned_assets.extend(str(item) for item in result.get("scanned_assets", []))
        operations.extend(result.get("operations", []))
        problems.extend(result.get("problems", []))

    operations.sort(
        key=lambda item: (
            item["asset"].casefold(),
            item["graph"].casefold(),
            item["node"].casefold(),
        )
    )
    discovered_channels = {
        str(item["channel"]["tag"])
        for item in operations
        if item.get("channel", {}).get("status") == "static"
        and item["channel"].get("tag")
    }
    requested_tags = sorted(set(tags or []), key=str.casefold)
    channels = sorted(discovered_channels.union(requested_tags), key=str.casefold)
    referencers: list[dict[str, Any]] = []
    if include_referencers:
        for batch in _chunks(channels, 50):
            result = session.invoke("find_tag_referencers_batch", {"tags": batch})
            referencers.extend(result.get("items", []))
        referencers.sort(key=lambda item: str(item["tag"]).casefold())

    return {
        "editor_state": state,
        "roots": selected_roots,
        "requested_asset_count": len(selected_assets),
        "scanned_asset_count": len(set(scanned_assets)),
        "message_operation_count": len(operations),
        "static_channel_count": len(discovered_channels),
        "requested_tags": requested_tags,
        "referencer_query_tag_count": len(channels) if include_referencers else 0,
        "operations": operations,
        "tag_referencers": referencers,
        "problems": problems,
    }
