from __future__ import annotations

from typing import Any

from editor_toolset.toolsets.blueprint import BlueprintTools

from .blueprints import _load_blueprint, serialize_node
from ue_editor_tools.message_model import message_operation


def scan_blueprint_batch(asset_paths: list[str]) -> dict[str, Any]:
    operations: list[dict[str, Any]] = []
    problems: list[dict[str, Any]] = []
    scanned_assets: list[str] = []
    for asset_path in asset_paths:
        try:
            blueprint = _load_blueprint(asset_path)
            scanned_assets.append(asset_path)
            for graph_object in BlueprintTools.list_graphs(blueprint):
                graph = {
                    "name": graph_object.get_name(),
                    "object_path": graph_object.get_path_name(),
                }
                for node_object in BlueprintTools.find_nodes(graph_object):
                    node_class = node_object.get_class().get_name()
                    if not (
                        node_class == "K2Node_CallFunction"
                        or node_class.startswith(
                            "K2Node_AsyncAction_ListenForGameplayMessage"
                        )
                    ):
                        continue
                    node = serialize_node(node_object)
                    operation = message_operation(asset_path, graph, node)
                    if operation is not None:
                        operations.append(operation)
        except Exception as exc:
            problems.append(
                {
                    "severity": "warning",
                    "code": "blueprint-scan-failed",
                    "message": str(exc),
                    "asset": asset_path,
                }
            )
    operations.sort(
        key=lambda item: (
            item["asset"].casefold(),
            item["graph"].casefold(),
            item["node"].casefold(),
        )
    )
    return {
        "scanned_assets": scanned_assets,
        "operations": operations,
        "problems": problems,
    }
