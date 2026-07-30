from __future__ import annotations

import hashlib
import json
import re
from typing import Any


_SPACE = re.compile(r"\s+")


def normalize_text(value: str | None) -> str:
    return _SPACE.sub(" ", value or "").strip()


def stable_id(prefix: str, *parts: Any) -> str:
    canonical = json.dumps(
        parts,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def project_key(project_name: str, descriptor_name: str) -> str:
    return f"{normalize_text(project_name)}|{normalize_text(descriptor_name)}"


def project_id(key: str) -> str:
    return stable_id("project", key)


def plugin_id(key: str, name: str) -> str:
    return stable_id("plugin", key, normalize_text(name))


def module_id(key: str, name: str, build_rules: str) -> str:
    return stable_id(
        "module",
        key,
        normalize_text(name),
        normalize_text(build_rules).replace("\\", "/"),
    )


def file_id(key: str, root: str, path: str) -> str:
    return stable_id(
        "file",
        key,
        normalize_text(root),
        normalize_text(path).replace("\\", "/"),
    )


def symbol_id(
    key: str,
    *,
    kind: str,
    qualified_name: str,
    owner: str | None = None,
    signature: str | None = None,
    linkage: str | None = None,
    source_path: str | None = None,
) -> tuple[str, str]:
    scope_path = (
        normalize_text(source_path).replace("\\", "/")
        if linkage == "internal" or "(anonymous)" in qualified_name
        else ""
    )
    canonical = "|".join(
        (
            key,
            normalize_text(kind),
            normalize_text(qualified_name),
            normalize_text(owner),
            normalize_text(signature),
            normalize_text(linkage),
            scope_path,
        )
    )
    return stable_id("symbol", canonical), canonical


def external_symbol_id(key: str, kind: str, spelling: str) -> tuple[str, str]:
    canonical = "|".join(
        (
            key,
            "external_symbol",
            normalize_text(kind),
            normalize_text(spelling),
        )
    )
    return stable_id("external", canonical), canonical


def relation_id(
    source_id: str,
    kind: str,
    target_id: str,
    evidence_key: str,
) -> str:
    return stable_id(
        "relation",
        source_id,
        normalize_text(kind),
        target_id,
        normalize_text(evidence_key),
    )
