from __future__ import annotations

from typing import Any, Callable

from .blueprints import inspect_blueprint, list_blueprint_assets
from .gameplay_messages import scan_blueprint_batch
from .gameplay_tags import (
    find_tag_referencers,
    find_tag_referencers_batch,
    list_gameplay_tags,
)
from .state import editor_state


OPERATIONS: dict[str, Callable[..., Any]] = {
    "editor_state": editor_state,
    "list_gameplay_tags": list_gameplay_tags,
    "find_tag_referencers": find_tag_referencers,
    "find_tag_referencers_batch": find_tag_referencers_batch,
    "inspect_blueprint": inspect_blueprint,
    "list_blueprint_assets": list_blueprint_assets,
    "scan_blueprint_batch": scan_blueprint_batch,
}


def invoke(operation: str, arguments: dict[str, Any]) -> Any:
    function = OPERATIONS.get(operation)
    if function is None:
        raise ValueError(f"Unknown editor operation: {operation}")
    return function(**arguments)
