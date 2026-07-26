from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"

if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))


CLI_SCRIPTS = (
    "ue_find_projects.py",
    "ue_read_project_descriptor.py",
    "ue_resolve_engine.py",
    "ue_inspect_modules.py",
    "ue_inspect_targets.py",
    "ue_resolve_plugins.py",
    "ue_classify_project_paths.py",
    "ue_read_plugin_descriptor.py",
    "ue_inspect_module_rules.py",
    "ue_inspect_target_rules.py",
    "ue_inspect_cs_function.py",
    "ue_inspect_module_entry.py",
    "ue_list_cxx_includes.py",
    "ue_list_cxx_types.py",
    "ue_inspect_cxx_function.py",
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.strip() + "\n", encoding="utf-8")


def run_cli(script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOLS_ROOT / script), *arguments],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


class EnvelopeAssertions(unittest.TestCase):
    def assert_envelope(self, result: dict[str, Any]) -> None:
        keys = list(result)
        self.assertEqual(keys[0], "schema_version")
        self.assertEqual(keys[-2:], ["validation", "limits"])
        self.assertIn(result["validation"]["status"], {"ok", "warning", "error"})
        self.assertEqual(
            result["validation"]["problem_count"],
            len(result["validation"]["problems"]),
        )
        self.assertIsInstance(result["limits"]["responsibility"], str)
        self.assertIsInstance(result["limits"]["boundaries"], list)


def create_fixture(workspace: Path) -> SimpleNamespace:
    project_root = workspace / "FixtureProject"
    project_file = project_root / "FixtureProject.uproject"
    engine_root = workspace
    build_version = engine_root / "Engine" / "Build" / "Build.version"

    write_json(
        build_version,
        {
            "MajorVersion": 5,
            "MinorVersion": 6,
            "PatchVersion": 1,
            "Changelist": 123,
            "CompatibleChangelist": 123,
            "IsLicenseeVersion": 0,
            "IsPromotedBuild": 0,
            "BranchName": "Fixture",
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
        "#pragma once\nstruct FGameplayTag {};",
    )

    write_json(
        project_file,
        {
            "FileVersion": 3,
            "EngineAssociation": "",
            "Category": "Tests",
            "Modules": [
                {
                    "Name": "FixtureGame",
                    "Type": "Runtime",
                    "LoadingPhase": "Default",
                }
            ],
            "Plugins": [
                {"Name": "FixturePlugin", "Enabled": True},
                {"Name": "DisabledPlugin", "Enabled": False},
            ],
        },
    )

    game_rules = project_root / "Source" / "FixtureGame" / "FixtureGame.Build.cs"
    write_text(
        game_rules,
        """
        public class FixtureGame : ModuleRules
        {
            public FixtureGame(ReadOnlyTargetRules Target) : base(Target)
            {
                PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;
                PublicDependencyModuleNames.AddRange(
                    new string[] { "Core", "GameplayTags" });
                if (Target.bBuildEditor)
                {
                    PrivateDependencyModuleNames.Add("UnrealEd");
                }
                AddOptionalModules();
            }

            private void AddOptionalModules()
            {
                DynamicallyLoadedModuleNames.Add("Projects");
            }
        }
        """,
    )
    write_text(
        project_root
        / "Source"
        / "FixtureGame"
        / "Private"
        / "FixtureGameModule.cpp",
        """
        #include "Modules/ModuleManager.h"
        IMPLEMENT_PRIMARY_GAME_MODULE(
            FDefaultGameModuleImpl, FixtureGame, "FixtureGame");
        """,
    )

    target_file = project_root / "Source" / "FixtureGame.Target.cs"
    write_text(
        target_file,
        """
        public class FixtureGameTarget : TargetRules
        {
            private static readonly string SharedDefinition = "FIXTURE";

            public FixtureGameTarget(TargetInfo Target) : base(Target)
            {
                Type = TargetType.Game;
                ExtraModuleNames.Add("FixtureGame");
                ApplySharedSettings(Target);
            }

            private static void ApplySharedSettings(TargetRules Target)
            {
                if (Target.Configuration == UnrealTargetConfiguration.Shipping)
                {
                    Target.bUseLoggingInShipping = true;
                }
            }
        }
        """,
    )

    plugin_root = project_root / "Plugins" / "FixturePlugin"
    plugin_file = plugin_root / "FixturePlugin.uplugin"
    write_json(
        plugin_file,
        {
            "FileVersion": 3,
            "Version": 1,
            "VersionName": "1.0",
            "FriendlyName": "Fixture Plugin",
            "Description": "Self-contained scanner fixture",
            "Category": "Tests",
            "CanContainContent": False,
            "Modules": [
                {
                    "Name": "FixturePlugin",
                    "Type": "Runtime",
                    "LoadingPhase": "Default",
                }
            ],
            "Plugins": [{"Name": "GameplayTags", "Enabled": True}],
        },
    )
    plugin_rules = (
        plugin_root / "Source" / "FixturePlugin" / "FixturePlugin.Build.cs"
    )
    write_text(
        plugin_rules,
        """
        public class FixturePlugin : ModuleRules
        {
            public FixturePlugin(ReadOnlyTargetRules Target) : base(Target)
            {
                PublicDependencyModuleNames.Add("Core");
                PrivateDependencyModuleNames.Add("GameplayTags");
            }
        }
        """,
    )
    plugin_entry = (
        plugin_root
        / "Source"
        / "FixturePlugin"
        / "Private"
        / "FixturePluginModule.cpp"
    )
    write_text(
        plugin_entry,
        """
        #include "Modules/ModuleManager.h"

        class FFixturePluginModule : public IModuleInterface
        {
        public:
            virtual void StartupModule() override
            {
                ReadyHandle = FCoreDelegates::OnPostEngineInit.AddRaw(
                    this, &FFixturePluginModule::HandleReady);
            }

            virtual void ShutdownModule() override
            {
                FCoreDelegates::OnPostEngineInit.Remove(ReadyHandle);
            }

            void HandleReady() {}
            FDelegateHandle ReadyHandle;
        };

        IMPLEMENT_MODULE(FFixturePluginModule, FixturePlugin)
        """,
    )

    source_file = (
        project_root / "Source" / "FixtureGame" / "Private" / "Feature.cpp"
    )
    header_file = (
        project_root / "Source" / "FixtureGame" / "Public" / "Feature.h"
    )
    write_text(
        header_file,
        """
        #pragma once

        #include "CoreMinimal.h"
        #include "GameplayTagContainer.h"
        #include "Feature.generated.h"

        USTRUCT(BlueprintType)
        struct FFixtureFeature
        {
            GENERATED_BODY()

            UPROPERTY(EditAnywhere)
            FGameplayTag Tag;
        };

        UCLASS()
        class UFixtureObject : public UObject
        {
            GENERATED_BODY()

        public:
            void Execute(UObject* Context) const;

        private:
            TObjectPtr<UObject> Helper;
        };
        """,
    )
    write_text(
        source_file,
        """
        #include "Feature.h"
        #include "CoreMinimal.h"

        void UFixtureObject::Execute(UObject* Context) const
        {
            if (Context)
            {
                Context->GetWorld();
                Helper->GetName();
            }
        }
        """,
    )

    return SimpleNamespace(
        workspace=workspace,
        project_root=project_root,
        project_file=project_file,
        engine_root=engine_root,
        build_version=build_version,
        game_rules=game_rules,
        target_file=target_file,
        plugin_root=plugin_root,
        plugin_file=plugin_file,
        plugin_rules=plugin_rules,
        plugin_entry=plugin_entry,
        source_file=source_file,
        header_file=header_file,
    )
