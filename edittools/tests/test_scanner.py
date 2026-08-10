from __future__ import annotations

import unittest

from ue_editor_tools.content_scanner import scan_asset_graph
from ue_editor_tools.scanner import scan_gameplay_messages


class FakeSession:
    def invoke(self, operation: str, arguments: dict | None = None):
        arguments = arguments or {}
        if operation == "editor_state":
            return {"dirty_packages": [], "capabilities": {}}
        if operation == "list_blueprint_assets":
            return {
                "roots": ["/Game"],
                "assets": [
                    {"package": "/Game/A"},
                    {"package": "/Game/B"},
                ],
            }
        if operation == "scan_blueprint_batch":
            assets = arguments["asset_paths"]
            return {
                "scanned_assets": assets,
                "operations": [
                    {
                        "asset": assets[0],
                        "graph": "EventGraph",
                        "node": assets[0] + ".Node",
                        "channel": {"status": "static", "tag": "Game.Message"},
                    }
                ],
                "problems": [],
            }
        if operation == "find_tag_referencers_batch":
            return {
                "items": [
                    {"tag": tag, "referencers": ["/Game/A"]}
                    for tag in arguments["tags"]
                ]
            }
        raise AssertionError(operation)


class ScannerTests(unittest.TestCase):
    def test_asset_graph_excludes_world_partition_external_packages(self) -> None:
        class AssetGraphSession:
            def invoke(self, operation: str, arguments: dict | None = None):
                if operation == "editor_state":
                    return {"dirty_packages": []}
                if operation == "list_asset_inventory":
                    return {
                        "roots": ["/Game"],
                        "packages": [
                            {"package": "/Game/Main", "assets": []},
                            {
                                "package": "/Game/__ExternalActors__/Map/A",
                                "assets": [],
                            },
                            {
                                "package": "/Game/__ExternalObjects__/Map/B",
                                "assets": [],
                            },
                        ],
                    }
                if operation == "scan_asset_dependencies_batch":
                    return {
                        "items": [
                            {
                                "package": "/Game/Main",
                                "dependencies": {
                                    "hard_package": [
                                        "/Game/Shared",
                                        "/Game/__ExternalActors__/Map/A",
                                    ]
                                },
                            }
                        ]
                    }
                raise AssertionError(operation)

        result = scan_asset_graph(AssetGraphSession())
        self.assertEqual(result["package_count"], 1)
        self.assertEqual(result["packages"][0]["package"], "/Game/Main")
        self.assertEqual(
            result["packages"][0]["dependencies"]["hard_package"],
            ["/Game/Shared"],
        )

    def test_scanner_aggregates_batches_and_referencers(self) -> None:
        result = scan_gameplay_messages(
            FakeSession(), batch_size=1, tags=["Code.Only.Message"]
        )
        self.assertEqual(result["requested_asset_count"], 2)
        self.assertEqual(result["scanned_asset_count"], 2)
        self.assertEqual(result["message_operation_count"], 2)
        self.assertEqual(result["static_channel_count"], 1)
        self.assertEqual(
            {item["tag"] for item in result["tag_referencers"]},
            {"Game.Message", "Code.Only.Message"},
        )
        self.assertEqual(result["referencer_query_tag_count"], 2)
        self.assertEqual(result["requested_tags"], ["Code.Only.Message"])

    def test_invalid_batch_size_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            scan_gameplay_messages(FakeSession(), batch_size=0)


if __name__ == "__main__":
    unittest.main()
