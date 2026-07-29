from __future__ import annotations

from tests.cxx_support import CxxAnalysisTestCase
from tests.support import write_json, write_text


class CxxSourceUnitTests(CxxAnalysisTestCase):
    def test_cxx_tools_share_context_and_source_unit(self) -> None:
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

    def test_private_cpp_derives_public_header(self) -> None:
        result = self.source_result("ue_list_cxx_types.py")
        self.assertEqual(
            result["source_unit"]["header"]["path"],
            "Source/SampleGame/Public/SampleFeature.h",
        )

    def test_public_header_derives_private_cpp(self) -> None:
        for script, extra in (
            ("ue_list_cxx_includes.py", ()),
            ("ue_list_cxx_types.py", ()),
            ("ue_inspect_cxx_function.py", ("--function", "Execute")),
        ):
            with self.subTest(script=script):
                result = self.source_result(
                    script,
                    *extra,
                    source=self.fixture.header_file,
                )
                self.assertEqual(
                    result["source_unit"]["source"]["path"],
                    "Source/SampleGame/Private/SampleFeature.cpp",
                )
                self.assertEqual(
                    result["source_unit"]["header"]["path"],
                    "Source/SampleGame/Public/SampleFeature.h",
                )

    def test_cc_and_hpp_pair_bidirectionally(self) -> None:
        cc_file = (
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Private"
            / "AlternateFeature.cc"
        )
        hpp_file = (
            self.fixture.project_root
            / "Source"
            / "SampleGame"
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
            with self.subTest(selected=selected.suffix):
                result = self.source_result(
                    "ue_inspect_cxx_function.py",
                    "--function",
                    "Run",
                    source=selected,
                )
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

    def test_standalone_header_scans_without_source_companion(self) -> None:
        header = (
            self.fixture.project_root
            / "Source"
            / "SampleGame"
            / "Public"
            / "HeaderOnly.hpp"
        )
        write_text(
            header,
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
        includes = self.source_result("ue_list_cxx_includes.py", source=header)
        types = self.source_result("ue_list_cxx_types.py", source=header)
        function = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Run",
            source=header,
        )
        for result in (includes, types, function):
            self.assertIsNone(result["source_unit"]["source"])
            self.assertTrue(
                result["source_unit"]["header"]["path"].endswith("HeaderOnly.hpp")
            )
        self.assertEqual(types["classes"][0]["evidence"]["unit"], "header")
        self.assertEqual(function["match_count"], 1)

    def test_ambiguous_automatic_headers_are_warning(self) -> None:
        write_text(
            self.fixture.source_file.parent / "SampleFeature.h",
            "#pragma once",
        )
        result = self.source_result("ue_list_cxx_types.py")
        self.assertIsNone(result["source_unit"]["header"])
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertIn(
            "source-unit-header-ambiguous",
            {problem["code"] for problem in result["validation"]["problems"]},
        )

    def test_ambiguous_automatic_sources_are_warning(self) -> None:
        write_text(
            self.fixture.source_file.with_suffix(".cc"),
            '#include "SampleFeature.h"',
        )
        result = self.source_result(
            "ue_list_cxx_types.py",
            source=self.fixture.header_file,
        )
        self.assertIsNone(result["source_unit"]["source"])
        self.assertEqual(result["validation"]["status"], "warning")
        self.assertIn(
            "source-unit-source-ambiguous",
            {problem["code"] for problem in result["validation"]["problems"]},
        )

    def test_unsupported_cxx_suffix_is_input_failure(self) -> None:
        unsupported = self.fixture.source_file.with_suffix(".cxx")
        write_text(unsupported, "void Unsupported() {}")
        result = self.source_result(
            "ue_list_cxx_types.py",
            source=unsupported,
            expected_code=2,
        )
        self.assert_request_failure(result, kind="input")
        self.assertIn(
            ".cc, .cpp, .h, .hpp",
            result["validation"]["problems"][0]["message"],
        )

    def test_source_context_refuses_nearest_project_ambiguity(self) -> None:
        root = self.fixture.workspace / "Ambiguous"
        source = root / "Source" / "Feature.cpp"
        write_text(source, "void Run() {}")
        write_json(root / "A.uproject", {"FileVersion": 3})
        write_json(root / "B.uproject", {"FileVersion": 3})
        result = self.source_result(
            "ue_list_cxx_types.py",
            source=source,
            expected_code=2,
        )
        self.assert_request_failure(result, kind="input")
        self.assertIn(
            "Multiple .uproject",
            result["validation"]["problems"][0]["message"],
        )

    def test_include_facts_keep_unit_owner_and_generated_status(self) -> None:
        result = self.source_result("ue_list_cxx_includes.py")
        core = [
            item for item in result["includes"] if item["spelling"] == "CoreMinimal.h"
        ]
        self.assertEqual(
            [item["evidence"]["unit"] for item in core],
            ["cpp", "header"],
        )
        self.assertTrue(
            all(item["resolution"]["owner"]["kind"] == "engine_module" for item in core)
        )
        generated = next(
            item
            for item in result["includes"]
            if item["spelling"] == "SampleFeature.generated.h"
        )
        self.assertEqual(generated["resolution"]["status"], "generated_header")
        self.assertNotIn(
            "SampleFeature.h",
            {item["spelling"] for item in result["includes"]},
        )

    def test_include_scan_does_not_follow_nested_includes(self) -> None:
        core_header = (
            self.fixture.engine_root
            / "Engine"
            / "Source"
            / "Runtime"
            / "Core"
            / "Public"
            / "CoreMinimal.h"
        )
        write_text(core_header, '#pragma once\n#include "NestedMissing.h"')
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            #include "DirectMissing.h"
            """,
        )
        result = self.source_result("ue_list_cxx_includes.py")
        missing = {
            problem["include"]["spelling"]
            for problem in result["validation"]["problems"]
            if "include" in problem
        }
        self.assertIn("DirectMissing.h", missing)
        self.assertNotIn("NestedMissing.h", missing)

    def test_preprocessor_condition_stays_on_include(self) -> None:
        editor_header = (
            self.fixture.engine_root
            / "Engine"
            / "Source"
            / "Runtime"
            / "Core"
            / "Public"
            / "EditorOnly.h"
        )
        write_text(editor_header, "#pragma once")
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            #if WITH_EDITOR
            #include "EditorOnly.h"
            #endif
            """,
        )
        result = self.source_result("ue_list_cxx_includes.py")
        editor_only = next(
            item for item in result["includes"] if item["spelling"] == "EditorOnly.h"
        )
        self.assertEqual(
            editor_only["conditions"],
            [
                {
                    "kind": "preprocessor",
                    "expression": "WITH_EDITOR",
                    "branch": "then",
                    "start_line": 2,
                }
            ],
        )

