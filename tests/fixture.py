from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from typing import Any
import unittest

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = REPOSITORY_ROOT / "tools"
SCHEMAS_ROOT = REPOSITORY_ROOT / "schemas"

if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))


CLI_SCHEMAS = {
    "ue_find_projects.py": "ue-itps.project-discovery.v1",
    "ue_read_project_descriptor.py": "ue-itps.project-descriptor.v1",
    "ue_resolve_engine.py": "ue-itps.engine-resolution.v1",
    "ue_inspect_modules.py": "ue-itps.project-modules.v1",
    "ue_inspect_targets.py": "ue-itps.project-targets.v1",
    "ue_list_project_cxx_sources.py": "ue-itps.project-cxx-sources.v1",
    "ue_resolve_plugins.py": "ue-itps.project-plugin-references.v1",
    "ue_classify_project_paths.py": "ue-itps.project-paths.v1",
    "ue_read_plugin_descriptor.py": "ue-itps.plugin-descriptor.v2",
    "ue_inspect_module_rules.py": "ue-itps.module-rule-relations.v1",
    "ue_inspect_target_rules.py": "ue-itps.target-rule-relations.v1",
    "ue_inspect_cs_function.py": "ue-itps.cs-function.v1",
    "ue_inspect_module_entry.py": "ue-itps.module-entry-state.v12",
    "ue_list_cxx_includes.py": "ue-itps.cxx-includes.v1",
    "ue_list_cxx_types.py": "ue-itps.cxx-types.v1",
    "ue_inspect_cxx_function.py": "ue-itps.cxx-function.v1",
}


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
def result_validator(script: str) -> Draft202012Validator:
    schema_path = SCHEMAS_ROOT / f"{Path(script).stem}.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, registry=schema_registry())


def assert_schema_valid(
    test_case: unittest.TestCase,
    script: str,
    result: dict[str, Any],
) -> None:
    errors = sorted(
        result_validator(script).iter_errors(result),
        key=lambda item: list(item.absolute_path),
    )
    test_case.assertEqual(
        errors,
        [],
        msg="\n".join(error.message for error in errors),
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


def parse_cli(
    test_case: unittest.TestCase,
    script: str,
    *arguments: str,
    expected_code: int = 0,
) -> dict[str, Any]:
    completed = run_cli(script, *arguments)
    test_case.assertEqual(
        completed.returncode,
        expected_code,
        msg=completed.stderr or completed.stdout,
    )
    test_case.assertEqual(completed.stderr, "")
    result = json.loads(completed.stdout)
    test_case.assertEqual(result["schema_version"], CLI_SCHEMAS[script])
    assert_schema_valid(test_case, script, result)
    return result


class EnvelopeAssertions(unittest.TestCase):
    def assert_envelope(self, result: dict[str, Any]) -> None:
        self.assertGreaterEqual(len(result), 3)
        self.assertEqual(next(iter(result)), "schema_version")
        self.assertEqual(list(result)[-2:], ["validation", "limits"])
        validation = result["validation"]
        self.assertIn(validation["status"], {"ok", "warning", "error"})
        self.assertEqual(
            validation["problem_count"],
            len(validation["problems"]),
        )
        self.assertIsInstance(result["limits"]["responsibility"], str)
        self.assertIsInstance(result["limits"]["boundaries"], list)

    def assert_success_envelope(self, result: dict[str, Any]) -> None:
        self.assert_envelope(result)
        self.assertNotEqual(result["validation"]["status"], "error")


class FixtureTestCase(EnvelopeAssertions):
    fixture: SimpleNamespace
    temporary_directory: tempfile.TemporaryDirectory[str]

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.fixture = create_fixture(Path(self.temporary_directory.name))

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def cli(
        self,
        script: str,
        *arguments: str,
        expected_code: int = 0,
    ) -> dict[str, Any]:
        result = parse_cli(
            self,
            script,
            *arguments,
            expected_code=expected_code,
        )
        self.assert_envelope(result)
        return result


def create_fixture(workspace: Path) -> SimpleNamespace:
    engine_root = workspace
    project_root = workspace / "CurrentGame"
    project_file = project_root / "CurrentGame.uproject"

    write_json(
        engine_root / "Engine" / "Build" / "Build.version",
        {
            "MajorVersion": 5,
            "MinorVersion": 6,
            "PatchVersion": 1,
            "Changelist": 101,
            "CompatibleChangelist": 101,
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
            "Description": "Current implementation fixture",
            "Modules": [
                {
                    "Name": "CurrentGame",
                    "Type": "Runtime",
                    "LoadingPhase": "Default",
                }
            ],
            "Plugins": [
                {"Name": "CurrentPlugin", "Enabled": True},
                {"Name": "DisabledPlugin", "Enabled": False},
            ],
            "CustomField": {"preserved": True},
        },
    )

    game_rules = project_root / "Source" / "CurrentGame" / "CurrentGame.Build.cs"
    write_text(
        game_rules,
        """
        public class CurrentGame : ModuleRules
        {
            public CurrentGame(ReadOnlyTargetRules Target) : base(Target)
            {
                PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;
                PublicDependencyModuleNames.AddRange(
                    new string[] { "Core", "GameplayTags" });
                if (Target.bBuildEditor)
                {
                    PrivateDependencyModuleNames.Add("UnrealEd");
                }
                AddRuntimeModules();
            }

            private void AddRuntimeModules()
            {
                DynamicallyLoadedModuleNames.Add("Projects");
            }
        }
        """,
    )
    game_entry = (
        project_root / "Source" / "CurrentGame" / "Private" / "CurrentGameModule.cpp"
    )
    write_text(
        game_entry,
        """
        #include "Modules/ModuleManager.h"
        IMPLEMENT_PRIMARY_GAME_MODULE(
            FDefaultGameModuleImpl, CurrentGame, "CurrentGame");
        """,
    )

    target_file = project_root / "Source" / "CurrentGame.Target.cs"
    write_text(
        target_file,
        """
        public class CurrentGameTarget : TargetRules
        {
            private static readonly string SharedDefinition = "CURRENT";

            public CurrentGameTarget(TargetInfo Target) : base(Target)
            {
                Type = TargetType.Game;
                ExtraModuleNames.Add("CurrentGame");
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

    plugin_root = project_root / "Plugins" / "CurrentPlugin"
    plugin_file = plugin_root / "CurrentPlugin.uplugin"
    write_json(
        plugin_file,
        {
            "FileVersion": 3,
            "Version": 2,
            "VersionName": "2.0",
            "FriendlyName": "Current Plugin",
            "Description": "Current implementation fixture plugin",
            "Category": "Tests",
            "CanContainContent": False,
            "Modules": [
                {
                    "Name": "CurrentPlugin",
                    "Type": "Runtime",
                    "LoadingPhase": "Default",
                }
            ],
            "Plugins": [{"Name": "GameplayTags", "Enabled": True}],
        },
    )
    plugin_rules = plugin_root / "Source" / "CurrentPlugin" / "CurrentPlugin.Build.cs"
    write_text(
        plugin_rules,
        """
        public class CurrentPlugin : ModuleRules
        {
            public CurrentPlugin(ReadOnlyTargetRules Target) : base(Target)
            {
                PublicDependencyModuleNames.Add("Core");
                PrivateDependencyModuleNames.Add("GameplayTags");
            }
        }
        """,
    )
    plugin_entry = (
        plugin_root / "Source" / "CurrentPlugin" / "Private" / "CurrentPluginModule.cpp"
    )
    write_text(
        plugin_entry,
        """
        #include "Modules/ModuleManager.h"

        class FCurrentPluginModule : public IModuleInterface
        {
        public:
            virtual void StartupModule() override
            {
                ReadyHandle = FCoreDelegates::OnPostEngineInit.AddRaw(
                    this, &FCurrentPluginModule::HandleReady);
            }

            virtual void ShutdownModule() override
            {
                FCoreDelegates::OnPostEngineInit.Remove(ReadyHandle);
            }

            void HandleReady() {}
            FDelegateHandle ReadyHandle;
        };

        IMPLEMENT_MODULE(FCurrentPluginModule, CurrentPlugin)
        """,
    )

    source_file = (
        project_root / "Source" / "CurrentGame" / "Private" / "CurrentFeature.cpp"
    )
    header_file = (
        project_root / "Source" / "CurrentGame" / "Public" / "CurrentFeature.h"
    )
    write_text(
        header_file,
        """
        #pragma once

        #include "CoreMinimal.h"
        #include "GameplayTagContainer.h"
        #include "CurrentFeature.generated.h"

        UENUM(BlueprintType)
        enum class ECurrentMode : uint8
        {
            Default,
            Active
        };

        USTRUCT(BlueprintType)
        struct FCurrentFeature
        {
            GENERATED_BODY()

            UPROPERTY(EditAnywhere)
            FGameplayTag Tag;
        };

        UCLASS()
        class UCurrentObject : public UObject
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
        #include "CurrentFeature.h"
        #include "CoreMinimal.h"

        void UCurrentObject::Execute(UObject* Context) const
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
        engine_root=engine_root,
        project_root=project_root,
        project_file=project_file,
        game_rules=game_rules,
        game_entry=game_entry,
        target_file=target_file,
        plugin_root=plugin_root,
        plugin_file=plugin_file,
        plugin_rules=plugin_rules,
        plugin_entry=plugin_entry,
        source_file=source_file,
        header_file=header_file,
    )
