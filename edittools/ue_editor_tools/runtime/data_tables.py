from __future__ import annotations

import json
from typing import Any

import unreal

from ue_editor_tools.value_refs import unique_references


def _path(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "get_path_name"):
        return str(value.get_path_name())
    return str(value)


def _row_struct(table: Any) -> str | None:
    try:
        return _path(table.get_editor_property("row_struct"))
    except Exception:
        return None


def inspect_data_table(asset_path: str, include_values: bool = False) -> dict[str, Any]:
    table = unreal.load_asset(asset_path)
    if table is None:
        raise ValueError(f"DataTable asset does not exist: {asset_path}")
    if not isinstance(table, unreal.DataTable):
        raise ValueError(f"Asset is not a DataTable: {asset_path}")
    exported = unreal.DataTableFunctionLibrary.export_data_table_to_json_string(table)
    raw = exported[-1] if isinstance(exported, tuple) else exported
    value = json.loads(str(raw) or "[]")
    rows = value if isinstance(value, list) else []
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        name = str(row.get("Name") or row.get("RowName") or index)
        payload = {key: row[key] for key in row if key not in {"Name", "RowName"}}
        item: dict[str, Any] = {
            "name": name,
            "references": unique_references(payload),
        }
        if include_values:
            item["values"] = payload
        items.append(item)
    items.sort(key=lambda item: str(item["name"]).casefold())
    return {
        "asset": asset_path,
        "object_path": table.get_path_name(),
        "row_struct": _row_struct(table),
        "row_count": len(items),
        "rows": items,
    }


def scan_data_tables_batch(
    asset_paths: list[str], include_values: bool = False
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    for asset_path in asset_paths:
        try:
            items.append(inspect_data_table(asset_path, include_values))
        except Exception as exc:
            problems.append(
                {
                    "severity": "warning",
                    "code": "data-table-scan-failed",
                    "asset": asset_path,
                    "message": str(exc),
                }
            )
    items.sort(key=lambda item: str(item["asset"]).casefold())
    return {"items": items, "problems": problems}
