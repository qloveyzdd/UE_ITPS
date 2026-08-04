from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
import uuid

from .storage import open_snapshot, snapshot_metadata


MANIFEST_SCHEMA = "ue-itps.information-pool.manifest"
MANIFEST_NAME = "manifest.json"


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate manifest field: {key}")
        result[key] = value
    return result


def load_manifest(pool_directory: Path) -> dict[str, Any]:
    path = pool_directory.resolve() / MANIFEST_NAME
    if not path.is_file():
        raise ValueError(
            f"Information pool has no active snapshot: {pool_directory.resolve()}"
        )
    try:
        document = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicates,
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid information-pool manifest: {path}") from exc
    if not isinstance(document, dict) or document.get("schema_version") != MANIFEST_SCHEMA:
        raise ValueError(f"Unsupported information-pool manifest: {path}")
    required = {
        "active_generation_id",
        "active_source_commit",
        "active_snapshot",
    }
    if not required.issubset(document):
        raise ValueError(f"Incomplete information-pool manifest: {path}")
    return document


def activate_snapshot(
    pool_directory: Path,
    snapshot_path: Path,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    pool_directory = pool_directory.resolve()
    relative = snapshot_path.resolve().relative_to(pool_directory).as_posix()
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "active_generation_id": metadata["generation_id"],
        "active_source_commit": metadata["source_commit"],
        "active_snapshot": relative,
        "project": {
            "name": metadata["project_name"],
            "descriptor": metadata["project_descriptor"],
        },
    }
    pool_directory.mkdir(parents=True, exist_ok=True)
    target = pool_directory / MANIFEST_NAME
    temporary = pool_directory / f".{MANIFEST_NAME}.{uuid.uuid4().hex}.tmp"
    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return manifest


def list_snapshots(pool_directory: Path) -> list[dict[str, Any]]:
    snapshots = pool_directory.resolve() / "snapshots"
    if not snapshots.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(snapshots.glob("*.sqlite3"), key=lambda item: item.name):
        connection = open_snapshot(path)
        try:
            metadata = snapshot_metadata(connection)
        finally:
            connection.close()
        metadata["database"] = str(path)
        results.append(metadata)
    return results


def resolve_snapshot(
    pool_directory: Path,
    selector: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    pool_directory = pool_directory.resolve()
    if selector is None or selector == "active":
        manifest = load_manifest(pool_directory)
        path = (pool_directory / str(manifest["active_snapshot"])).resolve()
        try:
            path.relative_to(pool_directory)
        except ValueError as exc:
            raise ValueError("Active snapshot escapes the information pool") from exc
        connection = open_snapshot(path)
        try:
            metadata = snapshot_metadata(connection)
        finally:
            connection.close()
        if (
            metadata["generation_id"] != manifest["active_generation_id"]
            or metadata["source_commit"] != manifest["active_source_commit"]
        ):
            raise ValueError("Active manifest and snapshot metadata disagree")
        return path, metadata

    matches = [
        item
        for item in list_snapshots(pool_directory)
        if str(item["generation_id"]).startswith(selector)
        or str(item["source_commit"]).startswith(selector)
    ]
    if not matches:
        raise ValueError(f"Information-pool snapshot not found: {selector}")
    if len(matches) > 1:
        raise ValueError(f"Information-pool snapshot selector is ambiguous: {selector}")
    selected = matches[0]
    return Path(str(selected.pop("database"))), selected
