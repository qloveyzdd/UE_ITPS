from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .common import normalized, read_json, result_document


def engine_version_at(root: Path) -> str | None:
    build_file = root / "Engine" / "Build" / "Build.version"
    if not build_file.is_file():
        return None
    try:
        build = read_json(build_file)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    parts = (
        build.get("MajorVersion"),
        build.get("MinorVersion"),
        build.get("PatchVersion"),
    )
    if all(isinstance(value, int) for value in parts):
        return ".".join(str(value) for value in parts)
    return None


def registry_engine_candidates(association: str) -> list[dict[str, str]]:
    if os.name != "nt" or not association:
        return []
    try:
        import winreg  # type: ignore
    except ImportError:
        return []

    candidates: list[dict[str, str]] = []
    exact_lookups: list[tuple[int, str, str]] = [
        (
            winreg.HKEY_CURRENT_USER,
            r"Software\Epic Games\Unreal Engine\Builds",
            association,
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            rf"SOFTWARE\EpicGames\Unreal Engine\{association}",
            "InstalledDirectory",
        ),
        (
            winreg.HKEY_LOCAL_MACHINE,
            rf"SOFTWARE\WOW6432Node\EpicGames\Unreal Engine\{association}",
            "InstalledDirectory",
        ),
    ]
    for hive, key_name, value_name in exact_lookups:
        try:
            with winreg.OpenKey(hive, key_name) as key:
                raw_value, _ = winreg.QueryValueEx(key, value_name)
            candidate = Path(str(raw_value)).expanduser().resolve()
            if candidate.exists():
                candidates.append(
                    {
                        "root": normalized(candidate),
                        "source": f"windows-registry:{key_name}:{value_name}",
                    }
                )
        except OSError:
            continue

    try:
        key_name = r"Software\Epic Games\Unreal Engine\Builds"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_name) as key:
            value_count = winreg.QueryInfoKey(key)[1]
            for index in range(value_count):
                value_name, raw_value, _ = winreg.EnumValue(key, index)
                candidate = Path(str(raw_value)).expanduser().resolve()
                actual = engine_version_at(candidate)
                if actual and (
                    actual == association or actual.startswith(f"{association}.")
                ):
                    candidates.append(
                        {
                            "root": normalized(candidate),
                            "source": (
                                "windows-registry-version-match:"
                                f"{key_name}:{value_name}"
                            ),
                        }
                    )
    except OSError:
        pass

    unique: dict[str, dict[str, str]] = {}
    for item in candidates:
        unique.setdefault(item["root"].casefold(), item)
    return list(unique.values())


def ancestor_engine_root(project_file: Path) -> Path | None:
    for parent in [project_file.parent, *project_file.parents]:
        candidate = parent / "Engine" / "Build" / "Build.version"
        if candidate.is_file():
            return parent.resolve()
    return None


def resolve_engine(
    project_file: Path, association: str, override: Path | None = None
) -> dict[str, Any]:
    root: Path | None = None
    source: str | None = None
    candidates: list[dict[str, str]] = []

    if override:
        root = override.expanduser().resolve()
        source = "cli-override"
    elif association and ("/" in association or "\\" in association):
        raw_path = Path(association).expanduser()
        root = (
            raw_path if raw_path.is_absolute() else project_file.parent / raw_path
        ).resolve()
        source = "association-relative-or-absolute-path"
    else:
        candidates = registry_engine_candidates(association)
        if len(candidates) == 1:
            root = Path(candidates[0]["root"])
            source = candidates[0]["source"]
        elif not candidates:
            root = ancestor_engine_root(project_file)
            source = "ancestor-engine" if root else None

    build_file = root / "Engine" / "Build" / "Build.version" if root else None
    build = read_json(build_file) if build_file and build_file.is_file() else None
    version = None
    if build:
        parts = (
            build.get("MajorVersion"),
            build.get("MinorVersion"),
            build.get("PatchVersion"),
        )
        if all(isinstance(value, int) for value in parts):
            version = ".".join(str(value) for value in parts)

    status = (
        "resolved"
        if root and build
        else ("ambiguous" if len(candidates) > 1 else "unresolved")
    )
    problems: list[dict[str, str]] = []
    if status != "resolved":
        problems.append(
            {
                "severity": "error",
                "code": f"engine-{status}",
                "message": (
                    f"EngineAssociation {association!r} has status {status} "
                    "and could not be bound to one Build.version"
                ),
            }
        )
    return result_document(
        "ue-itps.engine-resolution.v1",
        {
            "association_raw": association or None,
            "status": status,
            "resolution_method": source,
            "resolution_candidates": candidates,
            "engine_root": normalized(root) if root else None,
            "build_version_file": normalized(build_file) if build_file else None,
            "version": version,
            "build": build,
        },
        problems,
        responsibility=(
            "Resolve EngineAssociation to one Engine root and read Build.version."
        ),
        boundaries=[
            "EngineAssociation is an association key, not authoritative version evidence.",
            "The result does not prove that the project builds or runs with the Engine.",
            "Registry and ancestor lookup are static resolution mechanisms only.",
        ],
    )
