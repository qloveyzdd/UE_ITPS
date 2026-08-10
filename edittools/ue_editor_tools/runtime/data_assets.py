from __future__ import annotations

from typing import Any

import unreal

from ue_editor_tools.data_asset_values import (
    editor_properties,
    serialize_property_differences,
)


def _path(value: Any) -> str | None:
    if value is None or not hasattr(value, "get_path_name"):
        return None
    try:
        return str(value.get_path_name() or "") or None
    except Exception:
        return None


def _blueprint_parent_class(asset: Any) -> Any:
    try:
        parent = asset.get_editor_property("parent_class")
        if parent is not None:
            return parent
    except Exception:
        pass
    library = getattr(unreal, "BlueprintEditorLibrary", None)
    method = (
        getattr(library, "get_blueprint_parent_class", None)
        if library is not None
        else None
    )
    if method is None:
        return None
    try:
        return method(asset)
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
    baseline = None
    baseline_kind = "class_cdo"
    if not isinstance(source, unreal.DataAsset) and hasattr(asset, "generated_class"):
        generated_class = asset.generated_class()
        if generated_class is not None:
            source = unreal.get_default_object(generated_class)
            source_kind = "blueprint_cdo"
            baseline_kind = "parent_cdo"
            parent_class = _blueprint_parent_class(asset)
            if parent_class is not None:
                baseline = unreal.get_default_object(parent_class)
    if source is None or not isinstance(source, unreal.DataAsset):
        raise ValueError(
            f"Asset is not a DataAsset or DataAsset Blueprint: {asset_path}"
        )
    if source_kind == "data_asset":
        try:
            baseline = unreal.get_default_object(source.get_class())
        except Exception:
            baseline = None
    properties, missing = editor_properties(source, property_names)
    baseline_properties, _ = editor_properties(baseline, property_names)
    observed_rows, delta_rows = serialize_property_differences(
        properties,
        dict(baseline_properties),
        baseline_available=baseline is not None,
        max_depth=max_depth,
        max_items=max_items,
    )
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
    if baseline is None:
        problems.append(
            {
                "severity": "warning",
                "code": "data-asset-baseline-unavailable",
                "asset": package,
                "message": "Class or parent default object could not be resolved; no property deltas were emitted.",
            }
        )
    return (
        {
            "asset": package,
            "object_path": object_path,
            "source_kind": source_kind,
            "source_object_path": _path(source),
            "asset_class": _path(source.get_class()),
            "generated_class": _path(generated_class),
            "baseline_kind": baseline_kind,
            "baseline_object_path": _path(baseline),
            "baseline_class": _path(baseline.get_class())
            if baseline is not None
            else None,
            "observed_property_count": len(observed_rows),
            "observed_properties": observed_rows,
            "property_count": len(delta_rows),
            "properties": delta_rows,
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
