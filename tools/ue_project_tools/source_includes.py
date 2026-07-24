from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Iterable

from .code_inventory import discover_module_build_rules
from .common import normalized
from .source_preprocessor import preprocessor_conditions


_INCLUDE_DIRECTIVE_PATTERN = re.compile(
    r"^\s*#\s*include\s*(?P<operand>.+?)\s*$"
)
_INCLUDE_LITERAL_PATTERN = re.compile(
    r'^(?P<open>[<"])(?P<value>[^>"]+)[>"]$'
)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _nearest_plugin_descriptor(path: Path, stop: Path) -> Path | None:
    current = path.resolve()
    stop = stop.resolve()
    while _is_relative_to(current, stop):
        descriptors = sorted(
            current.glob("*.uplugin"), key=lambda item: item.name.casefold()
        )
        if len(descriptors) == 1:
            return descriptors[0].resolve()
        if current == stop:
            break
        current = current.parent
    return None


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
        rules_by_module, _ = discover_module_build_rules([search_root])
        for rules_paths in rules_by_module.values():
            for rules in rules_paths:
                rules_by_path.setdefault(
                    normalized(rules).casefold(),
                    (rules.resolve(), default_kind, boundary.resolve()),
                )

    records: list[dict[str, Any]] = []
    for rules, default_kind, boundary in rules_by_path.values():
        descriptor = _nearest_plugin_descriptor(rules.parent, boundary)
        kind = default_kind
        if descriptor is not None:
            kind = (
                "project_plugin_module"
                if _is_relative_to(descriptor, project_root)
                else "engine_plugin_module"
            )
        records.append(
            {
                "name": rules.name[: -len(".Build.cs")],
                "root": rules.parent.resolve(),
                "rules": rules,
                "kind": kind,
                "plugin": descriptor.stem if descriptor else None,
                "plugin_descriptor": descriptor,
            }
        )
    return sorted(
        records,
        key=lambda item: (
            normalized(item["root"]).casefold(),
            str(item["name"]).casefold(),
        ),
    )


def owner_for_path(
    path: Path, records: Iterable[dict[str, Any]]
) -> dict[str, Any] | None:
    resolved = path.resolve()
    candidates = [
        record for record in records if _is_relative_to(resolved, record["root"])
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


def rooted_path(
    path: Path, project_root: Path, engine_root: Path | None
) -> dict[str, str]:
    resolved = path.resolve()
    for name, root in (("project", project_root), ("engine", engine_root)):
        if root is None or not _is_relative_to(resolved, root):
            continue
        return {
            "root": name,
            "path": resolved.relative_to(root.resolve()).as_posix(),
        }
    return {"root": "absolute", "path": normalized(resolved)}


def extract_includes(text: str) -> list[dict[str, Any]]:
    contexts = preprocessor_conditions(text)
    includes: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        directive = _INCLUDE_DIRECTIVE_PATTERN.match(line)
        if not directive:
            continue
        operand = directive.group("operand").strip()
        literal = _INCLUDE_LITERAL_PATTERN.match(operand)
        spelling = literal.group("value") if literal else operand
        syntax = (
            "angle"
            if literal and literal.group("open") == "<"
            else ("quote" if literal else "macro")
        )
        includes.append(
            {
                "spelling": spelling.replace("\\", "/"),
                "syntax": syntax,
                "conditions": [
                    {
                        key: condition[key]
                        for key in ("kind", "expression", "branch", "start_line")
                    }
                    for condition in contexts.get(line_number, [])
                ],
                "line": line_number,
            }
        )
    return includes


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
    methods: set[str] = set()
    if direct.is_file():
        candidates.add(direct.resolve())
        methods.add("including-file-relative")

    for record in records:
        module_root = Path(record["root"])
        for prefix in (Path(), Path("Public"), Path("Private"), Path("Classes")):
            candidate = module_root / prefix / spelling
            if candidate.is_file():
                candidates.add(candidate.resolve())
                methods.add("known-module-exact-path")

    ordered = sorted(candidates, key=lambda item: normalized(item).casefold())
    if len(ordered) == 1:
        selected = ordered[0]
        return {
            "status": "resolved",
            "location": rooted_path(selected, project_root, engine_root),
            "owner": public_owner(owner_for_path(selected, records)),
            "method": sorted(methods),
        }
    if ordered:
        return {
            "status": "ambiguous",
            "candidates": [
                {
                    "location": rooted_path(path, project_root, engine_root),
                    "owner": public_owner(owner_for_path(path, records)),
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
