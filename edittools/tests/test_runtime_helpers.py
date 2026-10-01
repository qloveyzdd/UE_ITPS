from __future__ import annotations

import unittest

from ue_editor_tools.runtime.helpers import editor_property, object_path, scalar


class RuntimeHelperTests(unittest.TestCase):
    def test_object_path_handles_unreal_like_and_fallback_values(self) -> None:
        class UnrealObject:
            def get_path_name(self) -> str:
                return "/Game/Test.Asset"

        self.assertEqual(object_path(UnrealObject()), "/Game/Test.Asset")
        self.assertIsNone(object_path(object(), fallback_to_string=False))
        self.assertIsNone(object_path(None))

    def test_editor_property_returns_default_for_missing_fields(self) -> None:
        class Value:
            def get_editor_property(self, name: str) -> str:
                if name == "known":
                    return "value"
                raise AttributeError(name)

        self.assertEqual(editor_property(Value(), "known"), "value")
        self.assertEqual(editor_property(Value(), "missing", "default"), "default")

    def test_scalar_converts_vectors_and_nested_values(self) -> None:
        class Vector:
            x, y, z = 1, 2, 3

        self.assertEqual(scalar(Vector()), {"x": 1.0, "y": 2.0, "z": 3.0})
        self.assertEqual(scalar([1, (2, 3)]), [1, [2, 3]])


if __name__ == "__main__":
    unittest.main()
