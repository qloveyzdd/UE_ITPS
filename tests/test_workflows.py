from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests.support import create_fixture, run_cli


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

            completed, dependencies = run_cli(
                "sourcetools/ue_analyze_cxx_dependencies.py",
                "--project",
                fixture.project,
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(dependencies["validation"]["status"], "ok")

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
            self.assertEqual(function["matches"][0]["function"]["name"], "BeginPlay")

            completed, flow = run_cli(
                "sourcetools/ue_trace_cxx_function_flow.py",
                "--source",
                fixture.source,
                "--function",
                "BeginPlay",
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(flow["matches"][0]["name"], "AWorker::BeginPlay")
            self.assertEqual(flow["matches"][0]["calls"][0]["callee"], "Helper")


if __name__ == "__main__":
    unittest.main()
