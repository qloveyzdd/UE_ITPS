from __future__ import annotations

from typing import Any

import unreal

from .blueprints import _content_roots


_DEPENDENCY_FLAGS = {
    "hard_package": "include_hard_package_references",
    "soft_package": "include_soft_package_references",
    "hard_manage": "include_hard_management_references",
    "soft_manage": "include_soft_management_references",
    "searchable_name": "include_searchable_names",
}
_REGISTRY_TAGS = (
    "GeneratedClass",
    "ParentClass",
    "NativeParentClass",
    "PrimaryAssetType",
    "PrimaryAssetName",
)


def _class_path(asset: Any) -> str:
    value = asset.asset_class_path
    return f"{value.package_name}.{value.asset_name}"


def _tag_value(asset: Any, name: str) -> str:
    try:
        return str(unreal.AssetRegistryHelpers.get_tag_value(asset, name) or "")
    except Exception:
        return ""


def list_asset_inventory(
    roots: list[str] | None = None,
    packages: list[str] | None = None,
    class_names: list[str] | None = None,
) -> dict[str, Any]:
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.wait_for_completion()
    selected_roots = sorted(set(roots or _content_roots(registry)), key=str.casefold)
    package_rows: dict[str, dict[str, Any]] = {}
    selected_classes = {value.casefold() for value in (class_names or [])}
    sources = (
        [
            (
                f"/{package.split('/', 2)[1]}" if package.startswith("/") else "",
                registry.get_assets_by_package_name(package, True),
            )
            for package in sorted(set(packages), key=str.casefold)
        ]
        if packages
        else [
            (root, registry.get_assets_by_path(root, True, False))
            for root in selected_roots
        ]
    )
    for root, assets in sources:
        for asset in assets:
            class_path = _class_path(asset)
            class_leaf = class_path.rsplit(".", 1)[-1]
            if selected_classes and not {
                class_path.casefold(),
                class_leaf.casefold(),
            }.intersection(selected_classes):
                continue
            package = str(asset.package_name)
            row = package_rows.setdefault(
                package,
                {"package": package, "root": root, "assets": []},
            )
            tags = {
                name: value
                for name in _REGISTRY_TAGS
                if (value := _tag_value(asset, name))
            }
            row["assets"].append(
                {
                    "asset_name": str(asset.asset_name),
                    "object_path": f"{package}.{asset.asset_name}",
                    "class": class_path,
                    "registry_tags": tags,
                }
            )
    rows = list(package_rows.values())
    for row in rows:
        row["assets"].sort(key=lambda item: str(item["object_path"]).casefold())
    rows.sort(key=lambda item: str(item["package"]).casefold())
    return {"roots": selected_roots, "packages": rows}


def _options(kind: str) -> Any:
    option = unreal.AssetRegistryDependencyOptions()
    for flag in _DEPENDENCY_FLAGS.values():
        option.set_editor_property(flag, False)
    option.set_editor_property(_DEPENDENCY_FLAGS[kind], True)
    return option


def scan_asset_dependencies_batch(
    package_names: list[str], dependency_kinds: list[str] | None = None
) -> dict[str, Any]:
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    registry.wait_for_completion()
    selected_kinds = dependency_kinds or list(_DEPENDENCY_FLAGS)
    unknown = sorted(set(selected_kinds) - set(_DEPENDENCY_FLAGS))
    if unknown:
        raise ValueError(f"Unknown dependency kinds: {', '.join(unknown)}")
    items: list[dict[str, Any]] = []
    for package in sorted(set(package_names), key=str.casefold):
        dependencies = {
            kind: sorted(
                {
                    str(value)
                    for value in registry.get_dependencies(package, _options(kind))
                },
                key=str.casefold,
            )
            for kind in selected_kinds
        }
        items.append({"package": package, "dependencies": dependencies})
    return {"items": items}
