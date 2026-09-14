"""Authored retrieval guidance checked against explicit, current source facts."""
from __future__ import annotations

import hashlib


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def validate_navigation(unit):
    hashes = unit.get("reviewed_sources")
    if hashes is not None:
        if not isinstance(hashes, dict) or set(hashes) != set(unit["sources"]):
            raise ValueError("reviewed_sources must fingerprint every explicitly selected source")
        if any(not isinstance(v, str) or len(v) != 64 or set(v) - set("0123456789abcdef") for v in hashes.values()):
            raise ValueError("reviewed_sources values must be SHA-256 hex digests")
    navigation = unit.get("navigation", [])
    if not isinstance(navigation, list):
        raise ValueError("navigation must be an array")
    seen = set()
    required = {"id", "intent", "purpose", "kind", "target", "role", "reason", "checks"}
    for item in navigation:
        if not isinstance(item, dict) or set(item) != required:
            raise ValueError("Expected navigation id, intent, purpose, kind, target, role, reason and checks")
        if any(not _text(item[k]) for k in required - {"checks"}):
            raise ValueError("Navigation labels must be non-empty strings")
        if item["id"] in seen:
            raise ValueError("Duplicate navigation id in source unit")
        seen.add(item["id"])
        if item["kind"] == "type":
            allowed = item["purpose"] == "structure" and item["role"] == "type_structure"
            check_kinds = {"member"}
        else:
            allowed = (item["kind"] == "function" and item["purpose"] in {"behavior", "structure"}
                       and item["role"] in {"system_entry", "internal_function"})
            check_kinds = {"call", "statement"}
        if not allowed:
            raise ValueError("Navigation kind, purpose and role are inconsistent")
        checks = item["checks"]
        if not isinstance(checks, list) or not checks:
            raise ValueError("Navigation requires explicit evidence checks")
        for check in checks:
            if (not isinstance(check, dict) or set(check) != {"kind", "name"}
                    or check["kind"] not in check_kinds or not _text(check["name"])):
                raise ValueError("Expected an exact call name, statement expression or type member name")


def navigation_metadata(scope, spec):
    loaded = scope.units[spec["id"]]
    hashes = {relative: hashlib.sha256(scope.paths[(scope.root / relative).resolve().as_posix().casefold()][1]
                                      .encode("utf-8")).hexdigest() for relative in spec["sources"]}
    previous = spec.get("reviewed_sources")
    review_status = "unreviewed" if previous is None else ("current" if previous == hashes else "stale")
    result = {"source_hashes": hashes, "review_status": review_status}
    if "navigation" not in spec:
        return result
    result["navigation"] = []
    for guide in spec["navigation"]:
        pool = scope.functions if guide["kind"] == "function" else scope.types
        targets = [t for t in pool.values() if t["unit"] == spec["id"] and t["anchor"]["name"] == guide["target"]
                   and (guide["kind"] == "function" or t["raw"]["kind"] in {"class", "struct", "union"})]
        definitions = []
        complete = []
        observed_any = False
        for target in targets:
            raw = target["raw"]
            checks = []
            for required in guide["checks"]:
                matches = []
                if required["kind"] == "call":
                    refs = loaded["cpp_model"]["references"][raw["occurrence_id"]]
                    for call in refs["call_details"]:
                        if call["callee"] == required["name"]:
                            matches.append({"expression": call["expression"], "arguments": list(call["arguments"]),
                                            "evidence": scope._evidence(raw["file"], call["line"], call["syntax"]["column"]),
                                            "execution_scope": dict(call["execution_scope"])})
                elif required["kind"] == "statement":
                    refs = loaded["cpp_model"]["references"][raw["occurrence_id"]]
                    for statement in refs["statements"]:
                        if statement["expression"] == required["name"]:
                            matches.append({k: v for k, v in statement.items() if k not in {"kind", "location"}}
                                           | {"evidence": scope._evidence(raw["file"], statement["location"]["line"], statement["location"]["column"])})
                else:
                    for member in [*raw.get("fields", []), *raw.get("methods", [])]:
                        if member["name"] == required["name"]:
                            matches.append({"expression": member.get("signature", member.get("type_expression", member["name"])),
                                            "evidence": scope._evidence(raw["file"], member["line"])})
                checks.append({**required, "matches": matches})
                observed_any |= bool(matches)
            complete.append(all(check["matches"] for check in checks))
            definitions.append({"evidence": dict(target["anchor"]["evidence"]), "checks": checks})
        evidence_status = "matched" if targets and all(complete) else ("partial" if observed_any else "missing")
        status = ("unresolved" if not targets else
                  "reviewed" if len(targets) == 1 and review_status == "current" and evidence_status == "matched"
                  and not loaded["cpp_model"]["diagnostics"] else "candidate")
        item = {**guide, "status": status, "evidence_status": evidence_status, "definitions": definitions}
        if targets:
            item["query"] = {"tool": "ue_inspect_cxx_function" if guide["kind"] == "function" else "ue_inspect_cxx_type",
                             "selector": guide["target"]}
            if guide["kind"] == "function":
                item["query"].update(view=guide["purpose"], focus=list(dict.fromkeys(c["name"] for c in guide["checks"] if c["kind"] == "call")))
                if any(c["kind"] == "statement" for c in guide["checks"]):
                    item["query"]["include_syntax_flow"] = True
        result["navigation"].append(item)
    return result
