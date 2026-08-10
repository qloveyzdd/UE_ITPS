from __future__ import annotations

from typing import Any

from .remote_client import EditorSession


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
    rows = list(inventory.get("packages", []))
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
            dependencies[str(item["package"])] = dict(item.get("dependencies", {}))
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
