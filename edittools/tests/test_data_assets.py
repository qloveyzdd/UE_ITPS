from __future__ import annotations

import unittest

from ue_editor_tools.content_scanner import scan_data_assets
from ue_editor_tools.data_asset_values import (
    editor_properties,
    references_from_serialized,
    serialize_value,
)


class FakeObject:
    def __init__(self, path: str, class_path: str) -> None:
        self.path = path
        self.class_path = class_path

    def get_path_name(self) -> str:
        return self.path

    def get_class(self):
        return FakeObject(self.class_path, "/Script/CoreUObject.Class")


class FakeStruct:
    def __init__(self, **values) -> None:
        self.values = values
        for name, value in values.items():
            setattr(self, name, value)

    def get_editor_property(self, name: str):
        if name not in self.values:
            raise AttributeError(name)
        return self.values[name]


class FakeSession:
    def invoke(self, operation: str, arguments: dict | None = None):
        arguments = arguments or {}
        if operation == "editor_state":
            return {"dirty_packages": []}
        if operation == "scan_data_assets_batch":
            return {
                "items": [
                    {
                        "asset": asset,
                        "object_path": f"{asset}.{asset.rsplit('/', 1)[-1]}",
                        "source_kind": "data_asset",
                        "source_object_path": f"{asset}.{asset.rsplit('/', 1)[-1]}",
                        "asset_class": "/Script/Game.Data",
                        "generated_class": None,
                        "property_count": 0,
                        "properties": [],
                    }
                    for asset in arguments["asset_paths"]
                ],
                "problems": [],
            }
        raise AssertionError(operation)


class DataAssetTests(unittest.TestCase):
    def test_serializes_nested_values_and_extracts_asset_references(self) -> None:
        value = FakeStruct(
            pawn=FakeObject("/Game/Pawns/DA_Pawn.DA_Pawn", "/Script/Game.LyraPawnData"),
            weights=[1, 2],
        )
        serialized = serialize_value(value, max_depth=3, max_items=20)
        self.assertEqual(serialized["kind"], "struct")
        references = references_from_serialized(serialized)
        self.assertIn(
            ("asset", "/Game/Pawns/DA_Pawn.DA_Pawn"),
            {(item["kind"], item["target"]) for item in references},
        )
        self.assertIn(
            ("class", "/Script/Game.LyraPawnData"),
            {(item["kind"], item["target"]) for item in references},
        )

    def test_preserves_instanced_subobjects_as_object_references(self) -> None:
        serialized = serialize_value(
            FakeObject(
                "/Game/DA_Experience.DA_Experience:Action_0",
                "/Script/GameFeatures.GameFeatureAction",
            ),
            max_depth=2,
            max_items=10,
        )
        references = references_from_serialized(serialized)
        self.assertIn(
            ("object", "/Game/DA_Experience.DA_Experience:Action_0"),
            {(item["kind"], item["target"]) for item in references},
        )
        self.assertNotIn(
            ("asset", "/Game/DA_Experience.DA_Experience:Action_0"),
            {(item["kind"], item["target"]) for item in references},
        )

    def test_explicit_property_selection_reports_missing_names(self) -> None:
        properties, missing = editor_properties(
            FakeStruct(alpha=1), ["missing", "alpha"]
        )
        self.assertEqual(properties, [("alpha", 1)])
        self.assertEqual(missing, ["missing"])

    def test_scanner_requires_explicit_assets_and_forwards_limits(self) -> None:
        with self.assertRaises(ValueError):
            scan_data_assets(FakeSession(), assets=[], property_names=["value"])
        with self.assertRaises(ValueError):
            scan_data_assets(FakeSession(), assets=["/Game/A"], property_names=[])
        result = scan_data_assets(
            FakeSession(),
            assets=["/Game/B", "/Game/A", "/Game/A"],
            property_names=["pawn_data"],
            max_depth=2,
            max_items=10,
            batch_size=1,
        )
        self.assertEqual(result["requested_asset_count"], 2)
        self.assertEqual(result["scanned_asset_count"], 2)
        self.assertEqual(
            [item["asset"] for item in result["data_assets"]],
            ["/Game/A", "/Game/B"],
        )
        self.assertEqual(result["requested_properties"], ["pawn_data"])


if __name__ == "__main__":
    unittest.main()
