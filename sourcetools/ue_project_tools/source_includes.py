from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable

from .code_inventory import discover_module_build_rules
from .common import normalized


def _is_relative_to_resolved(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _nearest_plugin_descriptor(
    path: Path,
    stop: Path,
    cache: dict[tuple[Path, Path], Path | None] | None = None,
) -> Path | None:
    current = path
    visited: list[Path] = []
    result: Path | None = None
    while _is_relative_to_resolved(current, stop):
        cache_key = (current, stop)
        if cache is not None and cache_key in cache:
            result = cache[cache_key]
            break
        visited.append(current)
        descriptors = sorted(
            current.glob("*.uplugin"), key=lambda item: item.name.casefold()
        )
        if len(descriptors) == 1:
            result = descriptors[0].resolve()
            break
        if current == stop:
            break
        current = current.parent
    if cache is not None:
        for visited_path in visited:
            cache[(visited_path, stop)] = result
    return result


def module_records(
    project_root: Path,
    engine_root: Path | None,
    additional_module_roots: Iterable[Path] = (),
    additional_plugin_roots: Iterable[Path] = (),
) -> list[dict[str, Any]]:
    project_root = project_root.resolve()
    roots: list[tuple[Path, str, Path]] = [
        (project_root / "Source", "project_module", project_root),
        (project_root / "Plugins", "project_plugin_module", project_root),
        (project_root / "Platforms", "project_module", project_root),
    ]
    roots.extend(
        (path.resolve(), "project_module", project_root)
        for path in additional_module_roots
    )
    roots.extend(
        (path.resolve(), "project_plugin_module", project_root)
        for path in additional_plugin_roots
    )
    if engine_root is not None:
        engine_root = engine_root.resolve()
        roots.extend(
            [
                (
                    engine_root / "Engine" / "Source",
                    "engine_module",
                    engine_root,
                ),
                (
                    engine_root / "Engine" / "Plugins",
                    "engine_plugin_module",
                    engine_root,
                ),
                (
                    engine_root / "Engine" / "Platforms",
                    "engine_module",
                    engine_root,
                ),
            ]
        )

    rules_by_path: dict[str, tuple[Path, str, Path]] = {}
    for search_root, default_kind, boundary in roots:
        resolved_boundary = boundary.resolve()
        rules_by_module, _ = discover_module_build_rules([search_root])
        for rules_paths in rules_by_module.values():
            for rules in rules_paths:
                resolved_rules = rules.resolve()
                rules_by_path.setdefault(
                    resolved_rules.as_posix().casefold(),
                    (resolved_rules, default_kind, resolved_boundary),
                )

    records: list[dict[str, Any]] = []
    descriptor_cache: dict[tuple[Path, Path], Path | None] = {}
    for rules, default_kind, boundary in rules_by_path.values():
        module_root = rules.parent
        descriptor = _nearest_plugin_descriptor(
            module_root,
            boundary,
            descriptor_cache,
        )
        kind = default_kind
        if descriptor is not None:
            kind = (
                "project_plugin_module"
                if _is_relative_to_resolved(descriptor, project_root)
                else "engine_plugin_module"
            )
        records.append(
            {
                "name": rules.name[: -len(".Build.cs")],
                "root": module_root,
                "rules": rules,
                "kind": kind,
                "plugin": descriptor.stem if descriptor else None,
                "plugin_descriptor": descriptor,
                "_include_base_strings": (
                    os.fspath(module_root),
                    os.fspath(module_root / "Public"),
                    os.fspath(module_root / "Private"),
                    os.fspath(module_root / "Classes"),
                ),
            }
        )
    return sorted(
        records,
        key=lambda item: (
            Path(item["root"]).as_posix().casefold(),
            str(item["name"]).casefold(),
        ),
    )


def owner_for_path(
    path: Path, records: Iterable[dict[str, Any]]
) -> dict[str, Any] | None:
    resolved = path.resolve()
    candidates = [
        record
        for record in records
        if _is_relative_to_resolved(resolved, Path(record["root"]))
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: len(item["root"].parts))


def public_owner(owner: dict[str, Any] | None) -> dict[str, Any] | None:
    if owner is None:
        return None
    result: dict[str, Any] = {
        "kind": owner["kind"],
        "module": owner["name"],
    }
    if owner.get("plugin"):
        result["plugin"] = owner["plugin"]
    return result


def include_owner(owner: dict[str, Any] | None) -> dict[str, Any] | None:
    if owner is None:
        return None
    return {"kind": owner["kind"]}


def rooted_path(
    path: Path, project_root: Path, engine_root: Path | None
) -> dict[str, str]:
    resolved = path.resolve()
    for name, root in (("project", project_root), ("engine", engine_root)):
        if root is None:
            continue
        resolved_root = root.resolve()
        if not _is_relative_to_resolved(resolved, resolved_root):
            continue
        return {
            "root": name,
            "path": resolved.relative_to(resolved_root).as_posix(),
        }
    return {"root": "absolute", "path": normalized(resolved)}


def resolve_include(
    include: dict[str, Any],
    including_file: Path,
    records: list[dict[str, Any]],
    project_root: Path,
    engine_root: Path | None,
) -> dict[str, Any]:
    spelling = str(include["spelling"])
    if include["syntax"] == "macro":
        return {
            "status": (
                "generated_source"
                if spelling.startswith("UE_INLINE_GENERATED_CPP_BY_NAME")
                else "macro_unresolved"
            )
        }
    direct = including_file.parent / spelling
    candidates: set[Path] = set()
    candidate_owners: dict[Path, list[dict[str, Any]]] = {}
    methods: set[str] = set()
    if direct.is_file():
        candidates.add(direct.resolve())
        methods.add("including-file-relative")

    for record in records:
        include_bases = record.get("_include_base_strings")
        if include_bases is None:
            module_root = Path(record["root"])
            include_bases = (
                os.fspath(module_root),
                os.fspath(module_root / "Public"),
                os.fspath(module_root / "Private"),
                os.fspath(module_root / "Classes"),
            )
        for base in include_bases:
            candidate = os.path.join(base, spelling)
            if os.path.isfile(candidate):
                resolved_candidate = Path(candidate).resolve()
                candidates.add(resolved_candidate)
                candidate_owners.setdefault(resolved_candidate, []).append(record)
                methods.add("known-module-exact-path")

    ordered = sorted(candidates, key=lambda item: normalized(item).casefold())
    def resolved_owner(path: Path) -> dict[str, Any] | None:
        known_owners = candidate_owners.get(path, [])
        if known_owners:
            return max(
                known_owners,
                key=lambda item: len(Path(item["root"]).parts),
            )
        return owner_for_path(path, records)

    if len(ordered) == 1:
        selected = ordered[0]
        return {
            "status": "resolved",
            "location": rooted_path(selected, project_root, engine_root),
            "owner": include_owner(resolved_owner(selected)),
            "method": sorted(methods),
        }
    if ordered:
        return {
            "status": "ambiguous",
            "candidates": [
                {
                    "location": rooted_path(path, project_root, engine_root),
                    "owner": include_owner(resolved_owner(path)),
                }
                for path in ordered
            ],
            "method": sorted(methods),
        }
    if spelling.casefold().endswith(".generated.h"):
        return {"status": "generated_header"}
    if include["syntax"] == "angle":
        return {"status": "system_or_sdk_unresolved"}
    return {"status": "not_found"}
