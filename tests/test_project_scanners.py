from __future__ import annotations

from pathlib import Path
import tempfile

from tools.ue_project_tools.code_inventory import inspect_modules, inspect_targets
from tools.ue_project_tools.descriptor import (
    descriptor_result,
    resolve_internal_directories,
)
from tools.ue_project_tools.discovery import discovery_result
from tools.ue_project_tools.engine import resolve_engine
from tools.ue_project_tools.plugins import resolve_project_plugins
from tools.ue_project_tools.structure import classify_project_paths

from tests.support import EnvelopeAssertions, create_fixture, write_json


class ProjectScannerTests(EnvelopeAssertions):
    def test_project_discovery_selects_one_and_refuses_ambiguity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = root / "A" / "A.uproject"
            write_json(first, {"FileVersion": 3})

            selected = discovery_result(root)
            self.assert_envelope(selected)
            self.assertEqual(selected["status"], "selected")
            self.assertEqual(selected["candidate_count"], 1)

            write_json(root / "B" / "B.uproject", {"FileVersion": 3})
            ambiguous = discovery_result(root)

        self.assertEqual(ambiguous["status"], "ambiguous")
        self.assertEqual(ambiguous["candidate_count"], 2)
        self.assertEqual(ambiguous["validation"]["status"], "error")

    def test_descriptor_compacts_modules_plugins_and_unmodeled_fields(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            raw = fixture.project_file.read_text(encoding="utf-8")
            descriptor = __import__("json").loads(raw)
            descriptor["CustomField"] = {"kept": True}
            write_json(fixture.project_file, descriptor)

            _, result = descriptor_result(fixture.project_file)

        self.assert_envelope(result)
        self.assertEqual(result["declared_modules"], ["FixtureGame"])
        self.assertEqual(
            result["plugin_declarations"]["enabled"],
            ["FixturePlugin"],
        )
        self.assertEqual(
            result["plugin_declarations"]["disabled"],
            ["DisabledPlugin"],
        )
        self.assertEqual(result["unmodeled_top_level_fields"], {"CustomField": {"kept": True}})

    def test_engine_module_and_target_scanners_reconcile_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            descriptor, _ = descriptor_result(fixture.project_file)
            engine = resolve_engine(
                fixture.project_file,
                descriptor["EngineAssociation"],
            )
            additional_roots, _ = resolve_internal_directories(
                fixture.project_file,
                descriptor,
                "AdditionalRootDirectories",
            )
            modules = inspect_modules(
                fixture.project_root,
                descriptor["Modules"],
                additional_roots,
            )
            targets = inspect_targets(fixture.project_root)

        self.assertEqual(engine["status"], "resolved")
        self.assertEqual(engine["version"], "5.6.1")
        self.assertEqual(modules["reconciled_module_count"], 1)
        self.assertEqual(modules["items"][0]["name"], "FixtureGame")
        self.assertEqual(
            modules["items"][0]["actual"]["module_entrypoint_candidates"][0][
                "macro"
            ],
            "IMPLEMENT_PRIMARY_GAME_MODULE",
        )
        self.assertEqual(targets["classification"], "native-project")
        self.assertEqual([item["name"] for item in targets["items"]], ["FixtureGame"])

    def test_plugin_resolution_preserves_profile_and_sparse_origins(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            descriptor, _ = descriptor_result(fixture.project_file)
            result = resolve_project_plugins(
                fixture.project_file,
                fixture.project_root,
                fixture.engine_root,
                descriptor["Plugins"],
                [],
                "scan",
                "Win64",
                "Editor",
            )

        self.assert_envelope(result)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["declared_enabled_count"], 1)
        self.assertEqual(result["declared_disabled_count"], 1)
        enabled = next(item for item in result["items"] if item["name"] == "FixturePlugin")
        self.assertEqual(enabled["origin"], "project")
        self.assertEqual(
            enabled["descriptor"],
            "Plugins/FixturePlugin/FixturePlugin.uplugin",
        )

    def test_path_classifier_reports_facts_without_claiming_deletion_safety(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = create_fixture(Path(temporary_directory))
            descriptor, _ = descriptor_result(fixture.project_file)
            result = classify_project_paths(fixture.project_file, descriptor)

        self.assert_envelope(result)
        source = next(
            item for item in result["project_directories"] if item["role"] == "source"
        )
        self.assertEqual(source["actual_type"], "directory")
        self.assertNotIn("deletion_safe", source)
        self.assertTrue(
            any(
                "deletion safety" in boundary
                for boundary in result["limits"]["boundaries"]
            )
        )
