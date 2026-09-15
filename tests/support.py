from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LYRA_PROJECT = Path(os.environ.get(
    "UE_ITPS_LYRA_PROJECT", str(ROOT / "LyraStarterGame/LyraStarterGame.uproject")
)).expanduser().resolve()


def write_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).strip() + "\n", encoding="utf-8")
    return path


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


@dataclass(frozen=True)
class Fixture:
    root: Path
    project: Path
    build_version: Path
    module_rules: Path
    target_rules: Path
    header: Path
    source: Path


def create_fixture(root: Path) -> Fixture:
    project_root = root / "Sample"
    project = write_json(
        project_root / "Sample.uproject",
        {
            "FileVersion": 3,
            "EngineAssociation": "",
            "Modules": [
                {"Name": "Sample", "Type": "Runtime", "LoadingPhase": "Default"}
            ],
            "Plugins": [],
        },
    )
    build_version = write_json(
        root / "Engine" / "Build" / "Build.version",
        {
            "MajorVersion": 5,
            "MinorVersion": 8,
            "PatchVersion": 2,
            "Changelist": 1,
            "CompatibleChangelist": 1,
            "IsLicenseeVersion": 0,
            "IsPromotedBuild": 0,
            "BranchName": "++UE5+Release-5.8",
        },
    )
    module_rules = write_text(
        project_root / "Source" / "Sample" / "Sample.Build.cs",
        """
        using UnrealBuildTool;
        public class Sample : ModuleRules
        {
            public Sample(ReadOnlyTargetRules Target) : base(Target)
            {
                PublicDependencyModuleNames.AddRange(new string[] { "Core", "Engine" });
            }
        }
        """,
    )
    target_rules = write_text(
        project_root / "Source" / "Sample.Target.cs",
        """
        using UnrealBuildTool;
        public class SampleTarget : TargetRules
        {
            public SampleTarget(TargetInfo Target) : base(Target)
            {
                Type = TargetType.Game;
                ExtraModuleNames.Add("Sample");
            }
        }
        """,
    )
    write_text(
        project_root / "Source" / "Sample" / "Private" / "Sample.cpp",
        """
        #include "Modules/ModuleManager.h"
        IMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, Sample, "Sample");
        """,
    )
    header = write_text(
        project_root / "Source" / "Sample" / "Public" / "Worker.h",
        """
        #pragma once
        class AWorker
        {
        public:
            void BeginPlay();
            void Helper();
        };
        """,
    )
    source = write_text(
        project_root / "Source" / "Sample" / "Private" / "Worker.cpp",
        """
        #include "Worker.h"
        void AWorker::BeginPlay() { Helper(); }
        void AWorker::Helper() {}
        """,
    )
    return Fixture(root, project, build_version, module_rules, target_rules, header, source)


def run_cli(relative: str, *arguments: object) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    completed = subprocess.run(
        [sys.executable, str(ROOT / relative), *(str(item) for item in arguments)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(
            f"{relative} did not emit JSON (exit {completed.returncode}):\n"
            f"stdout={completed.stdout}\nstderr={completed.stderr}"
        ) from error
    if relative in {"sourcetools/ue_inspect_cxx_function.py", "sourcetools/ue_list_cxx_functions.py"}:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        schema = json.loads((ROOT / "schemas" / (Path(relative).stem + ".schema.json")).read_text(encoding="utf-8"))
        common = json.loads((ROOT / "schemas/common.schema.json").read_text(encoding="utf-8"))
        registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
        Draft202012Validator(schema, registry=registry).validate(document)
    return completed, document


def raw_call_owner(node):
    """Independent ancestor check for calls in executable definition regions."""
    from ue_project_tools.cpp_expression_facts import BUILTIN_TYPE_NAMES

    callee = node.child_by_field_name("function")
    if callee is not None:
        if callee.type in {"primitive_type", "sized_type_specifier"}:
            return None
        if callee.type == "identifier" and callee.text.decode("utf-8") in BUILTIN_TYPE_NAMES:
            return None
        name = callee.child_by_field_name("name")
        if callee.type == "template_function" and name is not None and name.text.decode("utf-8") in {
            "const_cast", "static_cast", "reinterpret_cast", "dynamic_cast",
        }:
            return None
    branch, parent = node, node.parent
    while parent is not None:
        if parent.type in {"class_specifier", "struct_specifier", "union_specifier", "enum_specifier",
                           "function_declarator", "abstract_function_declarator"}:
            return None
        if parent.type == "function_definition":
            return parent if branch.type in {"compound_statement", "field_initializer_list", "try_statement"} else None
        branch, parent = parent, parent.parent
    return None
