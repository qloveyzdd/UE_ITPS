from __future__ import annotations

from tests.fixture import write_text
from tests.source_layer_case import SourceLayerTestCase


class SourceUnitTests(SourceLayerTestCase):
    def test_three_cxx_tools_share_context_and_source_unit(self) -> None:
        includes = self.source_result("ue_list_cxx_includes.py")
        types = self.source_result("ue_list_cxx_types.py")
        function = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Execute",
        )
        for result in (includes, types, function):
            self.assertEqual(result["validation"]["status"], "ok")
        self.assertEqual(includes["path_roots"], types["path_roots"])
        self.assertEqual(types["path_roots"], function["path_roots"])
        self.assertEqual(includes["context"], types["context"])
        self.assertEqual(types["context"], function["context"])
        self.assertEqual(includes["source_unit"], types["source_unit"])
        self.assertEqual(types["source_unit"], function["source_unit"])

    def test_header_is_derived_from_private_to_public(self) -> None:
        result = self.source_result("ue_list_cxx_types.py")
        self.assertEqual(
            result["source_unit"]["header"]["path"],
            "Source/CurrentGame/Public/CurrentFeature.h",
        )

    def test_header_entry_derives_source_from_public_to_private(self) -> None:
        includes = self.selected_source_result(
            "ue_list_cxx_includes.py",
            self.fixture.header_file,
        )
        types = self.selected_source_result(
            "ue_list_cxx_types.py",
            self.fixture.header_file,
        )
        function = self.selected_source_result(
            "ue_inspect_cxx_function.py",
            self.fixture.header_file,
            "--function",
            "Execute",
        )
        for result in (includes, types, function):
            self.assertEqual(result["validation"]["status"], "ok")
            self.assertEqual(
                result["source_unit"]["source"]["path"],
                "Source/CurrentGame/Private/CurrentFeature.cpp",
            )
            self.assertEqual(
                result["source_unit"]["header"]["path"],
                "Source/CurrentGame/Public/CurrentFeature.h",
            )
        self.assertEqual(function["match_count"], 1)

    def test_cc_and_hpp_are_paired_bidirectionally(self) -> None:
        cc_file = (
            self.fixture.project_root
            / "Source"
            / "CurrentGame"
            / "Private"
            / "AlternateFeature.cc"
        )
        hpp_file = (
            self.fixture.project_root
            / "Source"
            / "CurrentGame"
            / "Public"
            / "AlternateFeature.hpp"
        )
        write_text(
            hpp_file,
            """
            #pragma once
            class FAlternateFeature
            {
            public:
                void Run();
            };
            """,
        )
        write_text(
            cc_file,
            """
            #include "AlternateFeature.hpp"
            void FAlternateFeature::Run() {}
            """,
        )

        for selected in (cc_file, hpp_file):
            result = self.selected_source_result(
                "ue_inspect_cxx_function.py",
                selected,
                "--function",
                "Run",
            )
            self.assertEqual(result["validation"]["status"], "ok")
            self.assertEqual(result["match_count"], 1)
            self.assertTrue(
                result["source_unit"]["source"]["path"].endswith(
                    "AlternateFeature.cc"
                )
            )
            self.assertTrue(
                result["source_unit"]["header"]["path"].endswith(
                    "AlternateFeature.hpp"
                )
            )

    def test_standalone_header_is_scanned_without_a_source_companion(self) -> None:
        header_only = (
            self.fixture.project_root
            / "Source"
            / "CurrentGame"
            / "Public"
            / "HeaderOnly.hpp"
        )
        write_text(
            header_only,
            """
            #pragma once
            #include "CoreMinimal.h"

            class FHeaderOnly
            {
            public:
                void Run() {}
            };
            """,
        )

        includes = self.selected_source_result(
            "ue_list_cxx_includes.py",
            header_only,
        )
        types = self.selected_source_result(
            "ue_list_cxx_types.py",
            header_only,
        )
        function = self.selected_source_result(
            "ue_inspect_cxx_function.py",
            header_only,
            "--function",
            "Run",
        )
        for result in (includes, types, function):
            self.assertEqual(result["validation"]["status"], "ok")
            self.assertIsNone(result["source_unit"]["source"])
            self.assertTrue(
                result["source_unit"]["header"]["path"].endswith(
                    "HeaderOnly.hpp"
                )
            )
        self.assertEqual(
            types["classes"][0]["evidence"]["unit"],
            "header",
        )
        self.assertEqual(function["match_count"], 1)

    def test_ambiguous_automatic_headers_are_reported(self) -> None:
        write_text(
            self.fixture.source_file.parent / "CurrentFeature.h",
            "#pragma once",
        )
        result = self.source_result("ue_list_cxx_types.py")
        self.assertIsNone(result["source_unit"]["header"])
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertIn(
            "source-unit-header-ambiguous",
            {problem["code"] for problem in result["validation"]["problems"]},
        )

    def test_ambiguous_automatic_sources_are_reported(self) -> None:
        write_text(
            self.fixture.source_file.with_suffix(".cc"),
            '#include "CurrentFeature.h"',
        )
        result = self.selected_source_result(
            "ue_list_cxx_types.py",
            self.fixture.header_file,
        )
        self.assertIsNone(result["source_unit"]["source"])
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertIn(
            "source-unit-source-ambiguous",
            {problem["code"] for problem in result["validation"]["problems"]},
        )

    def test_unsupported_cxx_suffix_is_rejected(self) -> None:
        unsupported = self.fixture.source_file.with_suffix(".cxx")
        write_text(unsupported, "void Unsupported() {}")
        result = self.selected_source_result(
            "ue_list_cxx_types.py",
            unsupported,
            expected_code=2,
        )
        self.assertEqual(result["validation"]["status"], "error")
        self.assertIn(
            ".cc, .cpp, .h, .hpp",
            result["validation"]["problems"][0]["message"],
        )
