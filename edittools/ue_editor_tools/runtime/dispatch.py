from __future__ import annotations

from typing import Any, Callable

from .blueprints import inspect_blueprint, list_blueprint_assets
from .assets import list_asset_inventory, scan_asset_dependencies_batch
from .blueprint_structure import scan_blueprint_structure_batch
from .data_tables import scan_data_tables_batch
from .data_assets import scan_data_assets_batch
from .gameplay_messages import scan_blueprint_batch
from .gameplay_tags import (
    find_tag_referencers,
    find_tag_referencers_batch,
    list_gameplay_tags,
)
from .state import editor_state
from .primary_assets import inspect_primary_assets


OPERATIONS: dict[str, Callable[..., Any]] = {
    "editor_state": editor_state,
    "list_gameplay_tags": list_gameplay_tags,
    "find_tag_referencers": find_tag_referencers,
    "find_tag_referencers_batch": find_tag_referencers_batch,
    "inspect_blueprint": inspect_blueprint,
    "list_blueprint_assets": list_blueprint_assets,
    "scan_blueprint_batch": scan_blueprint_batch,
    "list_asset_inventory": list_asset_inventory,
    "scan_asset_dependencies_batch": scan_asset_dependencies_batch,
    "scan_blueprint_structure_batch": scan_blueprint_structure_batch,
    "scan_data_tables_batch": scan_data_tables_batch,
    "scan_data_assets_batch": scan_data_assets_batch,
    "inspect_primary_assets": inspect_primary_assets,
}


def invoke(operation: str, arguments: dict[str, Any]) -> Any:
    function = OPERATIONS.get(operation)
    if function is None:
        raise ValueError(f"Unknown editor operation: {operation}")
    return function(**arguments)
