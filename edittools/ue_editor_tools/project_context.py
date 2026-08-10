from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TOOLS_ROOT = REPOSITORY_ROOT / "sourcetools"
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from ue_project_tools.common import normalized, read_json  # noqa: E402
from ue_project_tools.engine import resolve_engine  # noqa: E402


@dataclass(frozen=True)
class ProjectContext:
    project_file: Path
    project_root: Path
    project_name: str
    engine_root: Path
    engine_version: str


def resolve_project_context(
    project: str, engine_root: str | None = None
) -> ProjectContext:
    project_file = Path(project).expanduser().resolve()
    if not project_file.is_file() or project_file.suffix.casefold() != ".uproject":
        raise ValueError(f"Project must be an existing .uproject file: {project_file}")
    try:
        descriptor: dict[str, Any] = read_json(project_file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Cannot read project descriptor {project_file}: {exc}"
        ) from exc
    association = str(descriptor.get("EngineAssociation", ""))
    result = resolve_engine(
        project_file,
        association,
        Path(engine_root).expanduser().resolve() if engine_root else None,
    )
    if result["status"] != "resolved" or not result.get("engine_root"):
        raise ValueError(
            f"Cannot resolve one Engine installation for {normalized(project_file)}; "
            "pass --engine-root explicitly"
        )
    return ProjectContext(
        project_file=project_file,
        project_root=project_file.parent,
        project_name=project_file.stem,
        engine_root=Path(str(result["engine_root"])).resolve(),
        engine_version=str(result.get("version") or "unknown"),
    )


def validate_engine_root(value: str) -> tuple[Path, str]:
    root = Path(value).expanduser().resolve()
    build_file = root / "Engine" / "Build" / "Build.version"
    if not build_file.is_file():
        raise ValueError(
            f"Engine root does not contain Engine/Build/Build.version: {root}"
        )
    build = read_json(build_file)
    parts = [
        build.get("MajorVersion"),
        build.get("MinorVersion"),
        build.get("PatchVersion"),
    ]
    version = (
        ".".join(str(item) for item in parts)
        if all(isinstance(item, int) for item in parts)
        else "unknown"
    )
    return root, version
