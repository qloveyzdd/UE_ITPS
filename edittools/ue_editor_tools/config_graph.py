from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .value_refs import unique_references


_ASSIGNMENT = re.compile(
    r"^(?P<operator>[+\-.!]?)\s*(?P<key>[^=]+?)\s*=\s*(?P<value>.*)$"
)
_TAG_TEXT = re.compile(r"^[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+$")
_STRUCT_FIELD = re.compile(r"(?P<key>[A-Za-z_]\w*)\s*=\s*(?P<value>\"[^\"]*\"|[^,()]+)")
_DIRECTORY = re.compile(r"\bPath\s*=\s*\"(?P<path>/[^\"]+)\"")


def config_files(project_root: Path) -> list[Path]:
    roots = [
        project_root / "Config",
        project_root / "Plugins",
        project_root / "Platforms",
    ]
    return sorted(
        {
            path.resolve()
            for root in roots
            if root.is_dir()
            for path in root.rglob("*.ini")
            if path.is_file()
            and not any(
                part in {"Binaries", "Intermediate", "Saved"} for part in path.parts
            )
        },
        key=lambda path: path.relative_to(project_root).as_posix().casefold(),
    )


def _tag_reference(section: str, key: str, value: str) -> list[dict[str, str]]:
    hint = f"{section}.{key}".casefold()
    cleaned = value.strip().strip('"')
    if "tag" in hint and _TAG_TEXT.fullmatch(cleaned):
        return [
            {"kind": "gameplay_tag", "target": cleaned, "field": key, "value": value}
        ]
    return []


def parse_config_file(path: Path, project_root: Path) -> list[dict[str, Any]]:
    section = ""
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1
    ):
        stripped = raw.strip()
        if not stripped or stripped.startswith((";", "#")):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
            continue
        match = _ASSIGNMENT.match(stripped)
        if not match or not section:
            continue
        operator = match.group("operator") or "set"
        key = match.group("key").strip()
        value = match.group("value").strip()
        references = unique_references(value)
        references.extend(_tag_reference(section, key, value))
        unique = {
            (item["kind"], item["target"], item.get("field", "")): item
            for item in references
        }
        rows.append(
            {
                "section": section,
                "key": key,
                "operator": operator,
                "value": value,
                "references": [unique[item] for item in sorted(unique)],
                "evidence": {
                    "root": "project",
                    "path": path.relative_to(project_root).as_posix(),
                    "line": line_number,
                },
            }
        )
    return rows


def _fold(declarations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values: dict[tuple[str, str], list[str]] = {}
    for item in declarations:
        key = (str(item["section"]), str(item["key"]))
        current = values.setdefault(key, [])
        operator = item["operator"]
        value = str(item["value"])
        if operator == "!":
            current.clear()
        elif operator == "-":
            current[:] = [existing for existing in current if existing != value]
        elif operator == "+":
            if value not in current:
                current.append(value)
        elif operator == ".":
            current.append(value)
        else:
            current[:] = [value]
    return [
        {"section": section, "key": key, "values": value}
        for (section, key), value in sorted(
            values.items(),
            key=lambda item: (item[0][0].casefold(), item[0][1].casefold()),
        )
    ]


def _primary_asset_declaration(item: dict[str, Any]) -> dict[str, Any] | None:
    if (
        not str(item["section"]).endswith("AssetManagerSettings")
        or item["key"] != "PrimaryAssetTypesToScan"
    ):
        return None
    value = str(item["value"])
    fields = {
        match.group("key"): match.group("value").strip().strip('"')
        for match in _STRUCT_FIELD.finditer(value)
    }
    type_name = fields.get("PrimaryAssetType", "")
    if not type_name:
        return None
    references = [
        reference
        for reference in item.get("references", [])
        if reference.get("kind") in {"asset", "class"}
    ]
    directories = {match.group("path") for match in _DIRECTORY.finditer(value)}
    return {
        "primary_asset_type": type_name,
        "operator": item["operator"],
        "asset_base_class": fields.get("AssetBaseClass"),
        "has_blueprint_classes": fields.get("bHasBlueprintClasses", "").casefold()
        == "true",
        "is_editor_only": fields.get("bIsEditorOnly", "").casefold() == "true",
        "directories": sorted(directories, key=str.casefold),
        "specific_assets": sorted(
            {
                str(reference["target"])
                for reference in references
                if reference.get("kind") == "asset"
                and str(reference["target"]) not in directories
            },
            key=str.casefold,
        ),
        "rules": {
            key: fields[key]
            for key in ("Priority", "ChunkId", "bApplyRecursively", "CookRule")
            if key in fields
        },
        "evidence": item["evidence"],
    }


def scan_config_graph(project_file: Path) -> dict[str, Any]:
    project_file = project_file.resolve()
    if not project_file.is_file() or project_file.suffix.casefold() != ".uproject":
        raise ValueError(f"Project must be an existing .uproject file: {project_file}")
    root = project_file.parent
    files = config_files(root)
    declarations = [item for path in files for item in parse_config_file(path, root)]
    primary_asset_types = [
        parsed
        for item in declarations
        if (parsed := _primary_asset_declaration(item)) is not None
    ]
    return {
        "project": str(project_file).replace("\\", "/"),
        "config_files": [path.relative_to(root).as_posix() for path in files],
        "declaration_count": len(declarations),
        "declarations": declarations,
        "observed_values": _fold(declarations),
        "primary_asset_types": primary_asset_types,
    }
