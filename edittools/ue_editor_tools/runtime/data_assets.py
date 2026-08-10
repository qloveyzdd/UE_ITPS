from __future__ import annotations

from typing import Any

import unreal

from ue_editor_tools.data_asset_values import (
    editor_properties,
    references_from_serialized,
    serialize_value,
)


def _path(value: Any) -> str | None:
    if value is None or not hasattr(value, "get_path_name"):
        return None
    try:
        return str(value.get_path_name() or "") or None
    except Exception:
        return None


def inspect_data_asset(
    asset_path: str,
    property_names: list[str],
    max_depth: int = 3,
    max_items: int = 200,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    asset = unreal.load_asset(asset_path)
    if asset is None:
        raise ValueError(f"DataAsset does not exist: {asset_path}")
    object_path = str(asset.get_path_name())
    package = object_path.split(".", 1)[0]
    source = asset
    source_kind = "data_asset"
    generated_class = None
    if not isinstance(source, unreal.DataAsset) and hasattr(asset, "generated_class"):
        generated_class = asset.generated_class()
        if generated_class is not None:
            source = unreal.get_default_object(generated_class)
            source_kind = "blueprint_cdo"
    if source is None or not isinstance(source, unreal.DataAsset):
        raise ValueError(
            f"Asset is not a DataAsset or DataAsset Blueprint: {asset_path}"
        )
    properties, missing = editor_properties(source, property_names)
    rows: list[dict[str, Any]] = []
    for name, value in properties:
        serialized = serialize_value(value, max_depth=max_depth, max_items=max_items)
        rows.append(
            {
                "name": name,
                "path": name,
                "value_kind": str(serialized.get("kind", "unknown")),
                "value": serialized,
                "references": references_from_serialized(serialized),
            }
        )
    rows.sort(key=lambda item: str(item["path"]).casefold())
    problems = [
        {
            "severity": "warning",
            "code": "data-asset-property-not-found",
            "asset": package,
            "property": name,
            "message": f"Editor-visible property was not found: {name}",
        }
        for name in missing
    ]
    return (
        {
            "asset": package,
            "object_path": object_path,
            "source_kind": source_kind,
            "source_object_path": _path(source),
            "asset_class": _path(source.get_class()),
            "generated_class": _path(generated_class),
            "property_count": len(rows),
            "properties": rows,
        },
        problems,
    )


def scan_data_assets_batch(
    asset_paths: list[str],
    property_names: list[str],
    max_depth: int = 3,
    max_items: int = 200,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for asset_path in asset_paths:
        try:
            item, item_problems = inspect_data_asset(
                asset_path,
                property_names=property_names,
                max_depth=max_depth,
                max_items=max_items,
            )
            items.append(item)
            problems.extend(item_problems)
        except Exception as exc:
            problems.append(
                {
                    "severity": "warning",
                    "code": "data-asset-scan-failed",
                    "asset": asset_path,
                    "message": str(exc),
                }
            )
    items.sort(key=lambda item: str(item["asset"]).casefold())
    return {"items": items, "problems": problems}
