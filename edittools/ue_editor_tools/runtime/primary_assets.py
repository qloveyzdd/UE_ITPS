from __future__ import annotations

import unreal

from .assets import _tag_value
from .blueprints import _content_roots


def inspect_primary_assets() -> dict[str, object]:
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.wait_for_completion()
    roots = _content_roots(registry)
    type_roots: dict[str, set[str]] = {}
    assets: list[dict[str, object]] = []
    for root in roots:
        for asset in registry.get_assets_by_path(root, True, False):
            type_name = _tag_value(asset, "PrimaryAssetType")
            if not type_name:
                continue
            name = _tag_value(asset, "PrimaryAssetName") or str(asset.asset_name)
            type_roots.setdefault(type_name, set()).add(root)
            package = str(asset.package_name)
            assets.append(
                {
                    "id": {"type": type_name, "name": name},
                    "object_path": f"{package}.{asset.asset_name}",
                    "rules": None,
                    "bundle_data": _tag_value(asset, "AssetBundleData") or None,
                }
            )
    type_rows = [
        {
            "primary_asset_type": type_name,
            "asset_base_class": None,
            "has_blueprint_classes": None,
            "is_editor_only": None,
            "directories": [
                {"path": root}
                for root in sorted(type_roots[type_name], key=str.casefold)
            ],
            "rules": None,
        }
        for type_name in sorted(type_roots, key=str.casefold)
    ]
    assets.sort(key=lambda item: str(item["id"]).casefold())
    return {"types": type_rows, "primary_assets": assets}
