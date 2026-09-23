"""Input provenance and optional physical inventory for explicit scope scans."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

from .common import read_json
from .cpp_frontend import frontend_version
from .project_cxx_sources import list_module_cxx_sources
from .ue_cpp_conventions import UE_RETRIEVAL_RULES_VERSION


SCOPE_ANALYSIS_REVISION = 2


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def provenance(scope, descriptor):
    engines = []
    for root in sorted({str(unit["engine_root"]) for unit in scope.units.values() if unit["engine_root"]}):
        version = Path(root) / "Engine/Build/Build.version"
        engines.append({"root": Path(root).as_posix(),
                        "build_version": read_json(version) if version.is_file() else None})
    files = [{"path": relative, "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
             for relative, text in sorted(scope.paths.values())]
    return {"analysis_revision": SCOPE_ANALYSIS_REVISION, "frontend": frontend_version(),
            "retrieval_rules_version": UE_RETRIEVAL_RULES_VERSION,
            "project": scope.project.as_posix(), "descriptor_sha256": digest(descriptor),
            "profile_sha256": digest(scope.profile), "sources_sha256": digest(files),
            "engines": engines,
            "text_hash_policy": "UTF-8 decoded text; BOM removed; CRLF/CR normalized to LF"}


def audit(scope):
    selected = {}
    for unit_id, unit in scope.units.items():
        for path, parsed in unit["parsed_files"]:
            relative = path.relative_to(scope.root).as_posix()
            diagnostics = [d for d in unit["cpp_model"]["diagnostics"]
                           if d["file"].casefold() == path.as_posix().casefold()]
            selected[relative] = {"path": relative, "unit": unit_id,
                                  "status": "parsed_with_diagnostics" if diagnostics else "parsed",
                                  "text_sha256": hashlib.sha256(parsed["text"].encode("utf-8")).hexdigest(),
                                  "diagnostics": diagnostics}
    discovered = set()
    inventories = []
    for relative in scope.profile.get("inventory_rules", []):
        path = (scope.root / relative).resolve()
        result = list_module_cxx_sources(path)
        files = set(result["header_only"]) | set(result["cpp_only"])
        for pair in result["pairs"]:
            files.update((pair["header"], pair["cpp"]))
        for problem in result["validation"]["problems"]:
            files.update(problem.get("headers", []))
            files.update(problem.get("cpp", []))
        discovered.update(files)
        inventories.append({"rules": relative, "file_count": len(files),
                            "validation": result["validation"], "limits": result["limits"]})
    files = [*selected.values(), *({"path": path, "status": "not_selected",
                                   "reason": "not_in_profile"}
                                  for path in sorted(discovered - selected.keys()))]
    counts = Counter(item["status"] for item in files)
    return {"inventory_basis": "explicit_modules" if inventories else "profile_only",
            "inventories": inventories,
            "coverage": {"selected": len(selected), "inventoried": len(discovered) if inventories else None,
                         "selected_outside_inventory": sorted(selected.keys() - discovered) if inventories else [],
                         "by_status": dict(sorted(counts.items()))},
            "files": sorted(files, key=lambda item: item["path"]),
            "counting": {"unresolved_symbols": "Unknown symbol occurrences, including hidden items; not unique names or parser failures.",
                         "facts.call": "Supplemental calls without a symbol occurrence; not total calls.",
                         "call_occurrences": "Unique call locations in selected function definitions, including lambda bodies.",
                         "candidate_status": "One result per call location; declarations and definitions remain separate candidates."},
            "limits": ["Inventory enumerates paths only; unselected source contents are not parsed.",
                       "Inventory exclusions follow the listed module tool contracts; this is not whole-project coverage.",
                       "Invalid or unreadable selected files fail the scan; they are never silently skipped.",
                       "Hashes describe parsed text, not raw file bytes. Environment/include provenance is not an immutable build snapshot."]}
