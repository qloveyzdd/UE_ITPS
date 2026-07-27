from __future__ import annotations

from tests.fixture import FixtureTestCase, run_cli, write_json, write_text


class BoundaryCaseTests(FixtureTestCase):
    def test_project_discovery_skips_generated_directories(self) -> None:
        write_json(
            self.fixture.project_root / "Saved" / "Ghost.uproject",
            {"FileVersion": 3},
        )
        write_json(
            self.fixture.project_root / "Intermediate" / "Ghost.uproject",
            {"FileVersion": 3},
        )
        result = self.cli(
            "ue_find_projects.py",
            "--search-root",
            str(self.fixture.project_root),
        )
        self.assertEqual(result["candidate_count"], 1)
        self.assertTrue(result["candidates"][0].endswith("CurrentGame.uproject"))

    def test_project_descriptor_rejects_nonstandard_json(self) -> None:
        write_text(
            self.fixture.project_file,
            """
            {
              // Unreal descriptor comments are accepted.
              "FileVersion": 3,
              "EngineAssociation": "",
              "Modules": [
                {
                  "Name": "CurrentGame",
                  "Type": "Runtime",
                },
              ],
            }
            """,
        )
        completed = run_cli(
            "ue_read_project_descriptor.py",
            "--project",
            str(self.fixture.project_file),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn(
            "Expecting property name enclosed in double quotes",
            completed.stderr,
        )

    def test_plugin_resolution_keeps_alternate_descriptors(self) -> None:
        alternate = (
            self.fixture.engine_root
            / "Engine"
            / "Plugins"
            / "Runtime"
            / "CurrentPlugin"
            / "CurrentPlugin.uplugin"
        )
        write_json(alternate, {"FileVersion": 3})
        result = self.cli(
            "ue_resolve_plugins.py",
            "--project",
            str(self.fixture.project_file),
            "--engine-root",
            str(self.fixture.engine_root),
            "--plugin-name",
            "CurrentPlugin",
        )
        plugin = result["items"][0]
        self.assertEqual(plugin["origin"], "project")
        self.assertEqual(
            plugin["alternate_descriptors"],
            [
                {
                    "origin": "engine",
                    "path": (
                        "Engine/Plugins/Runtime/CurrentPlugin/CurrentPlugin.uplugin"
                    ),
                }
            ],
        )

    def test_unbalanced_module_source_keeps_partial_registration(self) -> None:
        write_text(
            self.fixture.plugin_entry,
            """
            #include "Modules/ModuleManager.h"
            class FBrokenModule : public IModuleInterface
            {
            public:
                virtual void StartupModule() override
                {
            IMPLEMENT_MODULE(FBrokenModule, CurrentPlugin)
            """,
        )
        result = self.cli(
            "ue_inspect_module_entry.py",
            "--rules",
            str(self.fixture.plugin_rules),
            expected_code=1,
        )
        self.assertEqual(result["validation"]["status"], "error")
        self.assertEqual(
            result["registration"]["module_class"],
            "FBrokenModule",
        )
        self.assertGreater(result["validation"]["problem_count"], 0)

    def test_source_context_refuses_same_level_project_ambiguity(self) -> None:
        source_root = self.fixture.workspace / "Ambiguous"
        source = source_root / "Source" / "Feature.cpp"
        write_text(source, "void Run() {}")
        write_json(source_root / "A.uproject", {"FileVersion": 3})
        write_json(source_root / "B.uproject", {"FileVersion": 3})
        result = self.cli(
            "ue_list_cxx_types.py",
            "--source",
            str(source),
            expected_code=2,
        )
        self.assertEqual(result["request"], {"status": "failed"})
        self.assertEqual(result["validation"]["status"], "error")
        self.assertIn(
            "Multiple .uproject",
            result["validation"]["problems"][0]["message"],
        )

    def test_csharp_function_selection_returns_all_overloads(self) -> None:
        source = self.fixture.workspace / "Plain.cs"
        write_text(
            source,
            """
            public class Plain
            {
                public void Run(int Count) {}
                public void Run(string Name) {}
            }
            """,
        )
        result = self.cli(
            "ue_inspect_cs_function.py",
            "--source",
            str(source),
            "--function",
            "Run",
        )
        self.assertEqual(result["match_count"], 2)
        signatures = [item["function"]["signature"] for item in result["matches"]]
        self.assertEqual(len(signatures), len(set(signatures)))

    def test_default_module_registration_does_not_invent_local_state(self) -> None:
        write_text(
            self.fixture.plugin_entry,
            """
            #include "Modules/ModuleManager.h"
            IMPLEMENT_MODULE(FDefaultModuleImpl, CurrentPlugin)
            """,
        )
        result = self.cli(
            "ue_inspect_module_entry.py",
            "--rules",
            str(self.fixture.plugin_rules),
        )
        self.assertEqual(
            result["registration"]["module_class"],
            "FDefaultModuleImpl",
        )
        self.assertIsNone(result["module"]["class"])
        self.assertEqual(result["callback_bindings"], [])
        self.assertEqual(result["state_models"], [])
