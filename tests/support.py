from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
from typing import Any
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
SCHEMAS_ROOT = REPOSITORY_ROOT / "schemas"

if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))


PUBLIC_CLIS = {
    "ue_list_tools.py": "ue_list_tools",
    "ue_find_projects.py": "ue_find_projects",
    "ue_read_project_descriptor.py": "ue_read_project_descriptor",
    "ue_resolve_engine.py": "ue_resolve_engine",
    "ue_inspect_modules.py": "ue_inspect_modules",
    "ue_inspect_targets.py": "ue_inspect_targets",
    "ue_list_project_cxx_sources.py": "ue_list_project_cxx_sources",
    "ue_resolve_plugins.py": "ue_resolve_plugins",
    "ue_classify_project_paths.py": "ue_classify_project_paths",
    "ue_read_plugin_descriptor.py": "ue_read_plugin_descriptor",
    "ue_inspect_module_rules.py": "ue_inspect_module_rules",
    "ue_inspect_target_rules.py": "ue_inspect_target_rules",
    "ue_inspect_cs_function.py": "ue_inspect_cs_function",
    "ue_inspect_module_entry.py": "ue_inspect_module_entry",
    "ue_list_cxx_includes.py": "ue_list_cxx_includes",
    "ue_list_cxx_types.py": "ue_list_cxx_types",
    "ue_inspect_cxx_function.py": "ue_inspect_cxx_function",
    "ue_analyze_cxx_dependencies.py": "ue_analyze_cxx_dependencies",
    "ue_query_cxx_hierarchy.py": "ue_query_cxx_hierarchy",
    "ue_analyze_cxx_impact.py": "ue_analyze_cxx_impact",
    "ue_trace_cxx_function_flow.py": "ue_trace_cxx_function_flow",
}

REQUIRED_PATH_ARGUMENTS = {
    "ue_read_project_descriptor.py": "--project",
    "ue_resolve_engine.py": "--project",
    "ue_inspect_modules.py": "--project",
    "ue_inspect_targets.py": "--project",
    "ue_list_project_cxx_sources.py": "--project",
    "ue_resolve_plugins.py": "--project",
    "ue_classify_project_paths.py": "--project",
    "ue_read_plugin_descriptor.py": "--plugin",
    "ue_inspect_module_rules.py": "--rules",
    "ue_inspect_target_rules.py": "--target",
    "ue_inspect_cs_function.py": "--source",
    "ue_inspect_module_entry.py": "--rules",
    "ue_list_cxx_includes.py": "--source",
    "ue_list_cxx_types.py": "--source",
    "ue_inspect_cxx_function.py": "--source",
    "ue_analyze_cxx_dependencies.py": "--project",
    "ue_query_cxx_hierarchy.py": "--project",
    "ue_analyze_cxx_impact.py": "--project",
    "ue_trace_cxx_function_flow.py": "--source",
}


def write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return path


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


@dataclass(frozen=True)
class Fixture:
    root: Path
    engine_root: Path
    project_root: Path
    project: Path
    module_rules: Path
    game_target: Path
    editor_target: Path
    source_header: Path
    source_cpp: Path
    plugin: Path
    plugin_rules: Path
    plugin_source: Path


def create_fixture(root: Path) -> Fixture:
    engine_root = root
    project_root = root / "SampleGame"
    project = project_root / "SampleGame.uproject"

    write_json(
        engine_root / "Engine" / "Build" / "Build.version",
        {
            "MajorVersion": 5,
            "MinorVersion": 6,
            "PatchVersion": 1,
            "Changelist": 12345,
            "CompatibleChangelist": 12000,
            "IsLicenseeVersion": 0,
            "IsPromotedBuild": 1,
            "BranchName": "++UE5+Release-5.6",
        },
    )
    write_text(
        engine_root / "Engine" / "Source" / "Runtime" / "Core" / "Core.Build.cs",
        """
        public class Core : ModuleRules
        {
            public Core(ReadOnlyTargetRules Target) : base(Target) {}
        }
        """,
    )
    write_text(
        engine_root
        / "Engine"
        / "Source"
        / "Runtime"
        / "Core"
        / "Public"
        / "CoreMinimal.h",
        "#pragma once",
    )
    write_text(
        engine_root
        / "Engine"
        / "Source"
        / "Runtime"
        / "GameplayTags"
        / "GameplayTags.Build.cs",
        """
        public class GameplayTags : ModuleRules
        {
            public GameplayTags(ReadOnlyTargetRules Target) : base(Target) {}
        }
        """,
    )
    write_text(
        engine_root
        / "Engine"
        / "Source"
        / "Runtime"
        / "GameplayTags"
        / "Classes"
        / "GameplayTagContainer.h",
        """
        #pragma once
        struct FGameplayTag {};
        """,
    )

    write_json(
        project,
        {
            "FileVersion": 3,
            "EngineAssociation": "",
            "Category": "Tests",
            "Description": "Deterministic test fixture",
            "Modules": [
                {
                    "Name": "SampleGame",
                    "Type": "Runtime",
                    "LoadingPhase": "Default",
                }
            ],
            "Plugins": [
                {"Name": "SamplePlugin", "Enabled": True},
                {"Name": "DisabledPlugin", "Enabled": False},
            ],
            "AdditionalRootDirectories": [],
            "AdditionalPluginDirectories": [],
            "Enterprise": False,
            "CustomFixtureField": {"kept": True},
        },
    )

    module_rules = write_text(
        project_root / "Source" / "SampleGame" / "SampleGame.Build.cs",
        """
        using UnrealBuildTool;

        public class SampleGame : ModuleRules
        {
            public SampleGame(ReadOnlyTargetRules Target) : base(Target)
            {
                PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
                PublicDependencyModuleNames.AddRange(
                    new string[] { "Core", "GameplayTags" }
                );
                ConfigureEditor(Target);
            }

            private void ConfigureEditor(ReadOnlyTargetRules Target)
            {
                if (Target.bBuildEditor)
                {
                    PrivateDependencyModuleNames.Add("UnrealEd");
                }
            }
        }
        """,
    )
    game_target = write_text(
        project_root / "Source" / "SampleGame.Target.cs",
        """
        using UnrealBuildTool;

        public class SampleGameTarget : TargetRules
        {
            private string Flavor = "Game";

            public SampleGameTarget(TargetInfo Target) : base(Target)
            {
                Type = TargetType.Game;
                DefaultBuildSettings = BuildSettingsVersion.V5;
                ExtraModuleNames.Add("SampleGame");
                Configure(Target);
            }

            private void Configure(TargetInfo Target)
            {
                LaunchModuleName = "SampleGame";
            }
        }
        """,
    )
    editor_target = write_text(
        project_root / "Source" / "SampleGameEditor.Target.cs",
        """
        using UnrealBuildTool;

        public class SampleGameEditorTarget : TargetRules
        {
            public SampleGameEditorTarget(TargetInfo Target) : base(Target)
            {
                Type = TargetType.Editor;
                ExtraModuleNames.Add("SampleGame");
            }
        }
        """,
    )

    source_header = write_text(
        project_root
        / "Source"
        / "SampleGame"
        / "Public"
        / "SampleActor.h",
        """
        #pragma once
        #include "CoreMinimal.h"
        #include "SampleActor.generated.h"

        namespace Gameplay
        {
        enum class ESampleState : uint8
        {
            Idle,
            Active
        };

        UCLASS()
        class ASampleActor : public AActor
        {
            GENERATED_BODY()

        public:
            UFUNCTION()
            void BeginPlay();

            void Helper();

            UPROPERTY()
            int32 Count;
        };

        extern int32 GSampleCount;
        void Utility();
        }
        """,
    )
    source_cpp = write_text(
        project_root
        / "Source"
        / "SampleGame"
        / "Private"
        / "SampleActor.cpp",
        """
        #include "SampleActor.h"
        #include "GameplayTagContainer.h"

        namespace Gameplay
        {
        int32 GSampleCount = 0;

        void Utility()
        {
            ++GSampleCount;
        }

        void ASampleActor::BeginPlay()
        {
            FGameplayTag Tag;
            Helper();
            Utility();
            ++GSampleCount;
        }

        void ASampleActor::Helper()
        {
            Count = 1;
        }
        }
        """,
    )
    write_text(
        project_root
        / "Source"
        / "SampleGame"
        / "Private"
        / "SampleGame.cpp",
        """
        #include "Modules/ModuleManager.h"
        IMPLEMENT_PRIMARY_GAME_MODULE(
            FDefaultGameModuleImpl,
            SampleGame,
            "SampleGame"
        );
        """,
    )

    plugin = write_json(
        project_root / "Plugins" / "SamplePlugin" / "SamplePlugin.uplugin",
        {
            "FileVersion": 3,
            "Version": 1,
            "VersionName": "1.0",
            "FriendlyName": "Sample Plugin",
            "Description": "Plugin fixture",
            "Category": "Tests",
            "CreatedBy": "UE ITPS",
            "CanContainContent": False,
            "IsBetaVersion": False,
            "Installed": False,
            "Modules": [
                {
                    "Name": "SamplePlugin",
                    "Type": "Runtime",
                    "LoadingPhase": "Default",
                }
            ],
            "Plugins": [{"Name": "GameplayAbilities", "Enabled": True}],
        },
    )
    plugin_rules = write_text(
        project_root
        / "Plugins"
        / "SamplePlugin"
        / "Source"
        / "SamplePlugin"
        / "SamplePlugin.Build.cs",
        """
        using UnrealBuildTool;

        public class SamplePlugin : ModuleRules
        {
            public SamplePlugin(ReadOnlyTargetRules Target) : base(Target)
            {
                PrivateDependencyModuleNames.Add("Core");
            }
        }
        """,
    )
    plugin_source = write_text(
        project_root
        / "Plugins"
        / "SamplePlugin"
        / "Source"
        / "SamplePlugin"
        / "Private"
        / "SamplePluginModule.cpp",
        """
        #include "CoreMinimal.h"
        #include "Modules/ModuleManager.h"

        class FSamplePluginModule : public IModuleInterface
        {
        public:
            virtual void StartupModule() override
            {
                FCoreDelegates::OnPostEngineInit.AddRaw(
                    this,
                    &FSamplePluginModule::HandlePostEngineInit
                );
            }

            virtual void ShutdownModule() override
            {
                FCoreDelegates::OnPostEngineInit.RemoveAll(this);
            }

            void HandlePostEngineInit()
            {
                bReady = true;
            }

        private:
            bool bReady = false;
        };

        IMPLEMENT_MODULE(FSamplePluginModule, SamplePlugin)
        """,
    )

    (project_root / "Config").mkdir(parents=True, exist_ok=True)
    (project_root / "Content").mkdir(parents=True, exist_ok=True)
    (project_root / "Reports").mkdir(parents=True, exist_ok=True)

    return Fixture(
        root=root,
        engine_root=engine_root,
        project_root=project_root,
        project=project,
        module_rules=module_rules,
        game_target=game_target,
        editor_target=editor_target,
        source_header=source_header,
        source_cpp=source_cpp,
        plugin=plugin,
        plugin_rules=plugin_rules,
        plugin_source=plugin_source,
    )


def run_cli(
    script: str,
    *arguments: str,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, str(TOOLS_ROOT / script), *arguments],
        cwd=cwd or REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        check=False,
    )


@lru_cache(maxsize=1)
def schema_registry() -> Registry:
    registry = Registry()
    for path in sorted(SCHEMAS_ROOT.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(
            schema["$id"],
            Resource.from_contents(schema),
        )
    return registry


@lru_cache(maxsize=None)
def validator_for(script: str) -> Draft202012Validator:
    schema_path = SCHEMAS_ROOT / f"{Path(script).stem}.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=schema_registry())


class CliTestCase(unittest.TestCase):
    fixture: Fixture
    _temporary_directory: tempfile.TemporaryDirectory[str]

    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.fixture = create_fixture(Path(self._temporary_directory.name))

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def cli(
        self,
        script: str,
        *arguments: str,
        expected_code: int = 0,
        cwd: Path | None = None,
    ) -> dict[str, Any]:
        completed = run_cli(script, *arguments, cwd=cwd)
        self.assertEqual(
            completed.returncode,
            expected_code,
            msg=completed.stderr or completed.stdout,
        )
        self.assertEqual(completed.stderr, "")
        result = json.loads(completed.stdout)
        self.assertEqual(result["schema_version"], PUBLIC_CLIS[script])
        errors = sorted(
            validator_for(script).iter_errors(result),
            key=lambda error: list(error.absolute_path),
        )
        self.assertEqual(
            errors,
            [],
            msg="\n".join(error.message for error in errors),
        )
        self.assert_result_contract(result)
        return result

    def assert_result_contract(self, result: dict[str, Any]) -> None:
        self.assertEqual(next(iter(result)), "schema_version")
        self.assertEqual(list(result)[-2:], ["validation", "limits"])
        validation = result["validation"]
        self.assertIn(validation["status"], {"ok", "warning", "error"})
        self.assertEqual(validation["problem_count"], len(validation["problems"]))
        self.assertTrue(result["limits"]["responsibility"])
        self.assertIsInstance(result["limits"]["boundaries"], list)

    def assert_request_failure(
        self,
        result: dict[str, Any],
        *,
        kind: str,
    ) -> None:
        self.assertEqual(result["request"], {"status": "failed", "kind": kind})
        self.assertEqual(result["validation"]["status"], "error")
        self.assertGreater(result["validation"]["problem_count"], 0)
