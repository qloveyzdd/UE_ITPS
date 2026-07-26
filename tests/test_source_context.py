from __future__ import annotations

from pathlib import Path
import tempfile

from tools.ue_project_tools.discovery import find_nearest_uproject
from tools.ue_project_tools.source_unit import (
    inspect_source_function,
    list_source_includes,
    list_source_types,
)

from tests.support import EnvelopeAssertions, create_fixture, write_json, write_text


class SourceContextTests(EnvelopeAssertions):
    def test_three_source_tools_share_the_same_context_and_source_unit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            includes = list_source_includes(fixture.source_file)
            types = list_source_types(fixture.source_file)
            function = inspect_source_function(fixture.source_file, "Execute")

        for result in (includes, types, function):
            self.assert_envelope(result)
            self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(includes["path_roots"], types["path_roots"])
        self.assertEqual(types["path_roots"], function["path_roots"])
        self.assertEqual(includes["context"], types["context"])
        self.assertEqual(types["context"], function["context"])
        self.assertEqual(includes["source_unit"], types["source_unit"])
        self.assertEqual(types["source_unit"], function["source_unit"])

    def test_header_is_derived_from_private_to_public_without_manual_input(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            result = list_source_types(fixture.source_file)

        self.assertEqual(
            result["source_unit"]["header"]["path"],
            "Source/FixtureGame/Public/Feature.h",
        )

    def test_multiple_automatic_headers_are_reported_as_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            write_text(fixture.source_file.parent / "Feature.h", "#pragma once")
            result = list_source_types(fixture.source_file)

        self.assertIsNone(result["source_unit"]["header"])
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertTrue(
            any(
                problem["code"] == "source-unit-header-ambiguous"
                for problem in result["validation"]["problems"]
            )
        )

    def test_nearest_project_discovery_rejects_same_level_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "Source" / "Feature.cpp"
            write_text(source, "void Run() {}")
            write_json(root / "A.uproject", {"FileVersion": 3})
            write_json(root / "B.uproject", {"FileVersion": 3})

            with self.assertRaisesRegex(ValueError, "Multiple .uproject"):
                find_nearest_uproject(source)
