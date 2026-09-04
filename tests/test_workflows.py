from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests.support import create_fixture, run_cli, write_text


class ProjectWorkflowTests(unittest.TestCase):
    def test_project_navigation_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))

            completed, discovery = run_cli(
                "sourcetools/ue_find_projects.py", "--search-root", fixture.root
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(discovery["status"], "selected")
            self.assertEqual(
                Path(discovery["candidates"][0]),
                fixture.project,
            )

            completed, descriptor = run_cli(
                "sourcetools/ue_read_project_descriptor.py",
                "--project",
                fixture.project,
                "--engine-build-version",
                fixture.build_version,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(descriptor["declared_modules"], ["Sample"])
            self.assertEqual(descriptor["validation"]["status"], "ok")

            completed, targets = run_cli(
                "sourcetools/ue_inspect_targets.py", "--project", fixture.project
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(targets["items"][0]["name"], "SampleTarget")

    def test_selected_build_and_source_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))

            completed, rules = run_cli(
                "sourcetools/ue_inspect_module_rules.py", "--rules", fixture.module_rules
            )
            self.assertEqual(completed.returncode, 0)
            dependencies = rules["rules_classes"][0]["dependencies"]
            self.assertEqual(dependencies["public_dependency_modules"], ["Core", "Engine"])

            completed, types = run_cli(
                "sourcetools/ue_list_cxx_types.py",
                "--source",
                fixture.source,
                fixture.header,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertIn("AWorker", {item["name"] for item in types["classes"]})

            completed, function = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                fixture.source,
                fixture.header,
                "--function",
                "BeginPlay",
            )
            self.assertEqual(completed.returncode, 0)
            self.assertIn("AWorker|BeginPlay", function["matches"][0]["function_id"])

    def test_gameplay_tag_macros_are_reported_as_definitions_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                namespace SampleTags
                {
                    SAMPLE_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(SharedTag);
                    UE_DECLARE_GAMEPLAY_TAG_EXTERN(HeaderOnlyTag);
                }
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                namespace SampleTags
                {
                    UE_DEFINE_GAMEPLAY_TAG(SharedTag, "Sample.Shared");
                    UE_DEFINE_GAMEPLAY_TAG_COMMENT(CommentedTag, "Sample.Commented", "Comment");
                    UE_DEFINE_GAMEPLAY_TAG_STATIC(LocalTag, "Sample.Local");
                    int32 OrdinaryGlobal = 0;
                }
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_list_cxx_types.py",
                "--source",
                source,
                header,
            )

            self.assertEqual(completed.returncode, 0)
            globals_by_name = {
                item["qualified_name"]: item for item in result["global_variables"]
            }
            self.assertEqual(
                set(globals_by_name),
                {
                    "SampleTags::SharedTag",
                    "SampleTags::CommentedTag",
                    "SampleTags::LocalTag",
                    "SampleTags::OrdinaryGlobal",
                },
            )
            self.assertEqual(
                globals_by_name["SampleTags::SharedTag"]["type_expression"],
                "FNativeGameplayTag",
            )
            self.assertEqual(
                globals_by_name["SampleTags::LocalTag"]["linkage"], "internal"
            )
            self.assertEqual(
                globals_by_name["SampleTags::OrdinaryGlobal"]["macros"], []
            )


if __name__ == "__main__":
    unittest.main()
