from __future__ import annotations

from typing import Any

from .remote_client import EditorSession


def is_logical_asset_package(package: str) -> bool:
    normalized = package.replace("\\", "/").casefold()
    return not any(
        marker in normalized
        for marker in ("/__externalactors__/", "/__externalobjects__/")
    )


def _logical_dependencies(
    dependencies: dict[str, list[str]],
) -> dict[str, list[str]]:
    return {
        str(kind): [
            str(target) for target in targets if is_logical_asset_package(str(target))
        ]
        for kind, targets in dependencies.items()
    }


def chunks(values: list[str], size: int) -> list[list[str]]:
    if size < 1 or size > 200:
        raise ValueError("batch_size must be between 1 and 200")
    return [values[index : index + size] for index in range(0, len(values), size)]


def scan_asset_graph(
    session: EditorSession,
    *,
    roots: list[str] | None = None,
    assets: list[str] | None = None,
    dependency_kinds: list[str] | None = None,
    class_names: list[str] | None = None,
    batch_size: int = 50,
) -> dict[str, Any]:
    state = session.invoke("editor_state")
    inventory = session.invoke(
        "list_asset_inventory",
        {
            "roots": roots or None,
            "packages": assets or None,
            "class_names": class_names or None,
        },
    )
    rows = [
        row
        for row in inventory.get("packages", [])
        if is_logical_asset_package(str(row.get("package", "")))
    ]
    if assets:
        selected = set(assets)
        rows = [row for row in rows if str(row.get("package")) in selected]
    packages = [str(row["package"]) for row in rows]
    dependencies: dict[str, dict[str, list[str]]] = {}
    for batch in chunks(packages, batch_size):
        result = session.invoke(
            "scan_asset_dependencies_batch",
            {"package_names": batch, "dependency_kinds": dependency_kinds or None},
        )
        for item in result.get("items", []):
            dependencies[str(item["package"])] = _logical_dependencies(
                dict(item.get("dependencies", {}))
            )
    for row in rows:
        row["dependencies"] = dependencies.get(str(row["package"]), {})
    return {
        "editor_state": state,
        "roots": list(inventory.get("roots", [])),
        "package_count": len(rows),
        "packages": rows,
    }


def scan_blueprint_structures(
    session: EditorSession,
    *,
    roots: list[str] | None = None,
    assets: list[str] | None = None,
    batch_size: int = 20,
) -> dict[str, Any]:
    state = session.invoke("editor_state")
    if assets:
        selected = sorted(set(assets), key=str.casefold)
        selected_roots = sorted(set(roots or []), key=str.casefold)
    else:
        inventory = session.invoke("list_blueprint_assets", {"roots": roots or None})
        selected_roots = list(inventory.get("roots", []))
        selected = [str(item["package"]) for item in inventory.get("assets", [])]
    items: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for batch in chunks(selected, batch_size):
        result = session.invoke(
            "scan_blueprint_structure_batch", {"asset_paths": batch}
        )
        items.extend(result.get("items", []))
        problems.extend(result.get("problems", []))
    items.sort(key=lambda item: str(item["asset"]).casefold())
    return {
        "editor_state": state,
        "roots": selected_roots,
        "requested_asset_count": len(selected),
        "scanned_asset_count": len(items),
        "blueprints": items,
        "problems": problems,
    }


def scan_data_tables(
    session: EditorSession,
    *,
    roots: list[str] | None = None,
    assets: list[str] | None = None,
    include_values: bool = False,
    batch_size: int = 20,
) -> dict[str, Any]:
    state = session.invoke("editor_state")
    if assets:
        selected = sorted(set(assets), key=str.casefold)
        selected_roots = sorted(set(roots or []), key=str.casefold)
    else:
        inventory = session.invoke(
            "list_asset_inventory",
            {
                "roots": roots or None,
                "packages": None,
                "class_names": ["DataTable"],
            },
        )
        selected_roots = list(inventory.get("roots", []))
        selected = sorted(
            {
                str(row["package"])
                for row in inventory.get("packages", [])
                if any(
                    str(asset.get("class", "")).rsplit(".", 1)[-1] == "DataTable"
                    for asset in row.get("assets", [])
                )
            },
            key=str.casefold,
        )
    items: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for batch in chunks(selected, batch_size):
        result = session.invoke(
            "scan_data_tables_batch",
            {"asset_paths": batch, "include_values": include_values},
        )
        items.extend(result.get("items", []))
        problems.extend(result.get("problems", []))
    items.sort(key=lambda item: str(item["asset"]).casefold())
    return {
        "editor_state": state,
        "roots": selected_roots,
        "requested_asset_count": len(selected),
        "scanned_asset_count": len(items),
        "data_tables": items,
        "problems": problems,
    }


def scan_data_assets(
    session: EditorSession,
    *,
    assets: list[str],
    property_names: list[str],
    max_depth: int = 3,
    max_items: int = 200,
    batch_size: int = 10,
) -> dict[str, Any]:
    if not assets:
        raise ValueError("At least one DataAsset path is required")
    if not property_names:
        raise ValueError("At least one DataAsset property is required")
    if max_depth < 0 or max_depth > 8:
        raise ValueError("max_depth must be between 0 and 8")
    if max_items < 1 or max_items > 1000:
        raise ValueError("max_items must be between 1 and 1000")
    state = session.invoke("editor_state")
    selected = sorted(set(assets), key=str.casefold)
    items: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for batch in chunks(selected, batch_size):
        result = session.invoke(
            "scan_data_assets_batch",
            {
                "asset_paths": batch,
                "property_names": property_names,
                "max_depth": max_depth,
                "max_items": max_items,
            },
        )
        items.extend(result.get("items", []))
        problems.extend(result.get("problems", []))
    items.sort(key=lambda item: str(item["asset"]).casefold())
    return {
        "editor_state": state,
        "requested_asset_count": len(selected),
        "scanned_asset_count": len(items),
        "requested_properties": sorted(set(property_names), key=str.casefold),
        "max_depth": max_depth,
        "max_items": max_items,
        "data_assets": items,
        "problems": problems,
    }
