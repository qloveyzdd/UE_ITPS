"""Layered navigation over explicit source units, without cross-unit binding."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

from .common import read_json, result_document
from .cpp_frontend import frontend_version
from .source_context import load_source_context
from .source_function_references import _function_id, _list_functions_from_context
from .source_priority import FunctionPriorityView, validate_view
from .source_type_details import _compound
from .source_type_facts import _list_types_from_context, _unit
from .ue_cpp_conventions import UE_RETRIEVAL_RULES_VERSION


RESPONSIBILITY = "Navigate a configured source scope from overview to exact syntax evidence."
MAP_RESPONSIBILITY = "Export reusable file and name hints for ordinary SourceTools queries."
BOUNDARIES = [
    "Only explicit profile source units are parsed; referenced bodies and transitive headers are not read.",
    "Profile roles and entry points are authored navigation labels, not inferred program behavior.",
    "Relation groups summarize syntax candidates; spelling matches do not bind cross-file targets.",
    "Out-of-class method navigation uses owner names; conditional ownership remains unbound.",
    "Counts denote source occurrences, not executions. Delegate status is preserved.",
    "Selection IDs belong to the reported source/profile snapshot; regenerate them after changes.",
]


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _id(kind, *parts):
    digest = hashlib.sha256(_json(parts).encode("utf-8")).hexdigest()[:24]
    return f"{kind}:{digest}"


def _string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Expected a non-empty {label}")
    return value


def _profile(path):
    data = read_json(path)
    if not isinstance(data, dict) or type(data.get("version")) is not int or data["version"] != 1:
        raise ValueError("Expected scope profile version 1")
    if set(data) - {"version", "id", "name", "description", "units"}:
        raise ValueError("Unknown scope profile fields")
    for key in ("id", "name", "description"):
        _string(data.get(key), key)
    if not isinstance(data.get("units"), list) or not data["units"]:
        raise ValueError("Scope profile requires explicit units")
    seen = set()
    for unit in data["units"]:
        if not isinstance(unit, dict):
            raise ValueError("Expected a unit object")
        if set(unit) - {"id", "sources", "roles", "entry_points"}:
            raise ValueError("Unknown scope unit fields")
        key = _string(unit.get("id"), "unit id")
        if key in seen:
            raise ValueError(f"Duplicate unit id: {key}")
        seen.add(key)
        if not isinstance(unit.get("sources"), list) or not 1 <= len(unit["sources"]) <= 2:
            raise ValueError(f"Unit {key} requires one source or an explicit header/source pair")
        for source in unit["sources"]:
            _string(source, "source path")
        roles = unit.get("roles", {})
        if not isinstance(roles, dict):
            raise ValueError("roles must map exact type names to labels")
        for symbol, labels in roles.items():
            _string(symbol, "role symbol")
            if not isinstance(labels, list) or not labels:
                raise ValueError("Role labels must be a non-empty array")
            for label in labels:
                _string(label, "role label")
        entries = unit.get("entry_points", [])
        if not isinstance(entries, list):
            raise ValueError("entry_points must be an array of exact function names")
        for entry in entries:
            _string(entry, "entry point")
    return data


def validate_scope_query(level, select, view, focus, offset, limit):
    if level not in {"system", "type", "function", "evidence"}:
        raise ValueError(f"Unknown scope level: {level}")
    validate_view(view, focus)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Expected offset >= 0 and limit between 1 and 100")
    if (level == "system") != (select is None):
        raise ValueError("--select is required only for type, function and evidence levels")
    if select is not None:
        _string(select, "selection id")


class SourceScope:
    def __init__(self, project: Path, profile: Path, engine_override: Path | None = None):
        project = project.resolve()
        if project.suffix.casefold() != ".uproject" or not project.is_file():
            raise ValueError("Expected an explicitly selected .uproject file")
        descriptor = read_json(project)
        self.project = project
        self.root = project.parent
        self.profile = _profile(profile)
        self.units = {}
        self.paths = {}
        self.problems = []
        seen_files = set()
        fingerprint = hashlib.sha256(_json([
            str(project), descriptor, self.profile, frontend_version(), UE_RETRIEVAL_RULES_VERSION,
        ]).encode("utf-8"))
        for spec in self.profile["units"]:
            paths = []
            for relative in spec["sources"]:
                path = (self.root / relative).resolve()
                if Path(relative).is_absolute() or not path.is_relative_to(self.root):
                    raise ValueError(f"Profile source must remain within the selected project: {relative}")
                canonical = str(path).casefold()
                if canonical in seen_files:
                    raise ValueError(f"Duplicate source file in scope: {relative}")
                seen_files.add(canonical)
                paths.append(path)
            loaded = load_source_context(paths, engine_override, load_includes=True)
            if loaded["project_root"] != self.root:
                raise ValueError("All profile units must belong to the selected project")
            unit_id = spec["id"]
            self.units[unit_id] = loaded
            self.problems.extend({**p, "scope_unit": unit_id}
                                 for p in [*loaded["problems"], *loaded["include_problems"]])
            for path, parsed in loaded["parsed_files"]:
                normalized = path.as_posix().casefold()
                self.paths[normalized] = (path.relative_to(self.root).as_posix(), parsed["text"])
                fingerprint.update(_json([normalized, parsed["text"]]).encode("utf-8"))
        self.snapshot = fingerprint.hexdigest()[:24]
        self.types = {}
        self.functions = {}
        self.records = []
        self._build()

    def navigation_map(self):
        """Persist navigation hints, leaving current evidence to the focused tools."""
        units = []
        for spec in self.profile["units"]:
            types = {}
            entries = Counter()
            functions = 0
            for item in self.types.values():
                if item["unit"] != spec["id"]:
                    continue
                name, kind = item["anchor"]["name"], item["raw"]["kind"]
                key = (name, kind)
                if key not in types:
                    types[key] = {"name": name, "kind": kind,
                                  "roles": list(item["anchor"]["roles"]), "definition_count": 0}
                types[key]["definition_count"] += 1
            for item in self.functions.values():
                if item["unit"] == spec["id"]:
                    functions += 1
                    if item["anchor"].get("entry_point"):
                        entries[item["anchor"]["name"]] += 1
            units.append({
                "id": spec["id"], "sources": list(spec["sources"]),
                "types": list(types.values()),
                "entry_points": [{"name": name, "definition_count": count} for name, count in entries.items()],
                "function_definition_count": functions,
            })
        return result_document(
            "source_navigation_map", {
                "project": self.project.as_posix(), "snapshot": self.snapshot,
                "scope": {key: self.profile[key] for key in ("id", "name", "description")},
                "classification_source": "profile", "units": units,
                "summary": {"units": len(units), "files": len(self.paths),
                            "types": len(self.types), "functions": len(self.functions)},
            }, self.problems, responsibility=MAP_RESPONSIBILITY, boundaries=[
                "Roles and entry points are profile-authored navigation hints, not inferred behavior.",
                "Resolve sources relative to the reported project; use names with the existing type/function tools.",
                "Only type names and configured entry points are indexed; list functions in the selected unit for other names.",
                "Definition counts preserve name ambiguity. Current queries must retain every matching definition.",
                "Snapshot records generation provenance only. Read current evidence with focused tools; refresh hints after file/name/profile changes.",
                "This map does not monitor changes or automatically route natural-language questions.",
            ],
        )

    def _evidence(self, file, line, column=None, end_line=None):
        evidence = {"path": self.paths[file.casefold()][0], "line": line}
        if column is not None:
            evidence["column"] = column
        if end_line is not None:
            evidence["end_line"] = end_line
        return evidence

    def _call(self, call):
        return {key: call[key] for key in ("callee", "expression", "arguments", "execution_scope")}

    def _build(self):
        for spec in self.profile["units"]:
            unit_id = spec["id"]
            loaded = self.units[unit_id]
            model = loaded["cpp_model"]
            types = _list_types_from_context(loaded)
            raw_types = [t for t in model["types"] if t["role"] == "definition"]
            for kind in ("classes", "structs", "enums"):
                for item in types[kind]:
                    candidates = [t for t in raw_types if t["qualified_name"] == item["qualified_name"]
                                  and _unit(t["file"]) == item["evidence"]["unit"]
                                  and t.get("annotation_line", t["line"]) == item["evidence"]["line"]]
                    # Positions, not names, distinguish conditional and same-line definitions.
                    for raw in candidates:
                        key = _id("type", self.snapshot, unit_id, raw["file"], raw["start_offset"])
                        self.types[key] = {
                            "anchor": {"kind": "type", "id": key, "name": item["qualified_name"],
                                       "roles": spec.get("roles", {}).get(item["qualified_name"], []),
                                       "evidence": self._evidence(raw["file"], item["evidence"]["line"],
                                                                  raw.get("column"), raw["end_line"])},
                            "raw": raw, "unit": unit_id,
                        }
                        self.types[key]["anchor"]["evidence"]["byte_offset"] = raw["start_offset"]
            inventory = _list_functions_from_context(loaded)
            functions = {_function_id(f): f for f in model["functions"] if f["role"] == "definition"}
            for item in inventory["functions"]:
                raw = functions[item["function_id"]]
                key = _id("function", self.snapshot, unit_id, item["function_id"])
                anchor = {"kind": "function", "id": key, "name": item["qualified_name"],
                          "evidence": self._evidence(raw["file"], raw["line"], raw["column"], raw["end_line"])}
                if item["qualified_name"] in spec.get("entry_points", []):
                    anchor["entry_point"] = True
                self.functions[key] = {"anchor": anchor, "raw": raw, "unit": unit_id}
                refs = model["references"][raw["occurrence_id"]]
                calls = {call["start_offset"]: call for call in refs["call_details"]}
                covered_calls = set()
                for index, symbol in enumerate(refs["symbol_occurrences"]):
                    call = calls.get(symbol.get("start_offset"))
                    public = {k: v for k, v in symbol.items() if k not in {"line", "start_offset"}}
                    record = self._record("symbol", key, index, public, raw["file"], symbol["line"], call)
                    record["public"]["evidence"]["byte_offset"] = symbol["start_offset"]
                    record["symbol"] = symbol
                    self.records.append(record)
                    if call:
                        covered_calls.add(call["start_offset"])
                for index, operation in enumerate(refs["delegate_operations"]):
                    self.records.append(self._record("delegate", key, index, operation, raw["file"],
                                                     operation["evidence"]["line"]))
                for index, call in enumerate(refs["call_details"]):
                    if call["start_offset"] not in covered_calls:
                        self.records.append(self._record("call", key, index, self._call(call),
                                                         raw["file"], call["line"], call))
            names = {t["qualified_name"] for t in raw_types}
            missing_roles = set(spec.get("roles", {})) - names
            missing_entries = set(spec.get("entry_points", [])) - {f["qualified_name"] for f in functions.values()}
            if missing_roles or missing_entries:
                raise ValueError(f"Profile {unit_id} references missing definitions: {sorted(missing_roles | missing_entries)}")
            includes = [*loaded["includes"], *(p["include"] for p in loaded["include_problems"] if "include" in p)]
            for index, fact in enumerate(includes):
                file = next(str(p).replace("\\", "/").casefold() for p, _ in loaded["parsed_files"]
                            if _unit(str(p)) == fact["evidence"]["unit"])
                self.records.append(self._record("include", unit_id, index, fact, file, fact["evidence"]["line"]))

    def _record(self, kind, source, index, fact, file, line, call=None):
        public = {"kind": kind, "id": _id("evidence", self.snapshot, source, kind, index),
                  "source": source, "evidence": self._evidence(file, line, call["syntax"]["column"] if call else None),
                  "fact": fact}
        if call:
            public["call"] = self._call(call)
        return {"public": public, "call": call}

    def _groups(self, records, view, focus):
        policies = {key: FunctionPriorityView(unit["cpp_model"], view, focus)
                    for key, unit in self.units.items()} if view != "full" else {}
        groups = {}
        for record in records:
            public = record["public"]
            kind, fact, source = public["kind"], public["fact"], public["source"]
            if kind == "call":
                continue  # Supplemental syntax flow remains available at the evidence level.
            display, rule = "expand", None
            function = self.functions.get(source)
            if kind == "symbol":
                relation_kind, target = fact["kind"], fact["spelling"]
                status = "unresolved" if relation_kind == "unknown" else "syntax_candidate"
                identity = dict(fact)
                if record["call"]:
                    identity["receiver"] = record["call"]["receiver"]
                    identity["execution_scope"] = record["call"]["execution_scope"]
                if view != "full":
                    display, rule = policies[function["unit"]].classify(record["symbol"], record["call"], function["raw"])
            elif kind == "delegate":
                relation_kind = "delegate"
                target = fact["operation"] + " " + fact["subject"]["expression"]
                status = fact["resolution"]["status"]
                identity = {k: v for k, v in fact.items() if k != "evidence"}
            else:
                relation_kind, target, status = "include", fact["spelling"], "source_reference"
                identity = {k: v for k, v in fact.items() if k != "evidence"}
                if view == "behavior":
                    display, rule = "fold", "include-detail"
                if target in focus:
                    display, rule = "expand", "explicit-focus"
            key = _id("relation", self.snapshot, source, kind, identity)
            if key not in groups:
                item = {"kind": "relation", "id": key, "source": source,
                        "source_name": function["anchor"]["name"] if function else source,
                        "relation_kind": relation_kind, "target": target, "status": status,
                        "display": display, "count": 0}
                if rule:
                    item["rule"] = rule
                if record["call"]:
                    call = record["call"]
                    if call["receiver"]:
                        item["receiver"] = call["receiver"]
                    if call["execution_scope"]["kind"] != "function":
                        item["execution_scope"] = call["execution_scope"]
                groups[key] = {"item": item, "records": []}
            groups[key]["records"].append(record)
            groups[key]["item"]["count"] += 1
            rank = {"expand": 0, "fold": 1, "hide": 2}
            if rank[display] < rank[groups[key]["item"]["display"]]:
                groups[key]["item"]["display"] = display
                if rule:
                    groups[key]["item"]["rule"] = rule
        return groups

    def _function_ids_for_type(self, selected):
        name = selected["anchor"]["name"]
        alternatives = [t["raw"] for t in self.types.values()
                        if t["unit"] == selected["unit"] and t["anchor"]["name"] == name]
        result = set()
        for key, function in self.functions.items():
            raw = function["raw"]
            if (function["unit"] != selected["unit"] or raw["owner"] != name
                    or raw["qualified_name"] != f"{name}::{raw['name']}"):
                continue
            enclosing = [t for t in alternatives if t["file"] == raw["file"]
                         and t["start_offset"] <= raw["start_offset"] < t["end_offset"]]
            if not enclosing or selected["raw"] in enclosing:
                result.add(key)
        return result

    def query(self, *, level="system", select=None, view="behavior", focus=(), offset=0, limit=20):
        validate_scope_query(level, select, view, focus, offset, limit)
        focus = list(dict.fromkeys(name.strip() for name in focus))
        records = self.records
        anchors = []
        details = {}
        if level == "system":
            anchors = [t["anchor"] for t in self.types.values()]
            owners = {(t["unit"], t["anchor"]["name"]) for t in self.types.values()}
            anchors += [f["anchor"] for f in self.functions.values() if f["anchor"].get("entry_point")
                        or (f["unit"], f["raw"]["owner"]) not in owners]
            details["description"] = self.profile["description"]
            details["classification_source"] = "profile"
        elif level == "type" and select in self.types:
            selected = self.types[select]
            details["selection"] = selected["anchor"]
            ids = self._function_ids_for_type(selected)
            anchors = [self.functions[key]["anchor"] for key in sorted(ids)]
            records = [r for r in records if r["public"]["source"] in ids]
            if selected["raw"]["kind"] != "enum":
                details["type_details"] = _compound(selected["raw"])
        elif level == "function" and select in self.functions:
            selected = self.functions[select]
            details["selection"] = selected["anchor"]
            records = [r for r in records if r["public"]["source"] == select]
        elif level != "evidence":
            raise ValueError("Selection not found in this snapshot; refresh after source/profile changes")
        groups = self._groups(records, view, focus)
        if level == "evidence":
            if select in self.functions:
                selected = self.functions[select]
                details["selection"] = selected["anchor"]
                records = [r for r in records if r["public"]["source"] == select]
                raw = selected["raw"]
                refs = self.units[selected["unit"]]["cpp_model"]["references"][raw["occurrence_id"]]
                if offset == 0:
                    details["controls"] = refs["controls"]
                    lines = self.paths[raw["file"]][1].splitlines()
                    details["source_excerpt"] = "\n".join(lines[raw["line"] - 1:raw["end_line"]])
            elif select in groups:
                details["selection"] = groups[select]["item"]
                records = groups[select]["records"]
            else:
                records = [r for r in records if r["public"]["id"] == select]
                if not records:
                    raise ValueError("Selection not found in this snapshot; refresh after source/profile changes")
            items = [r["public"] for r in records]
            hidden = {}
        else:
            hidden = Counter()
            for group in groups.values():
                if group["item"]["display"] == "hide":
                    hidden[group["item"].get("rule", "default")] += group["item"]["count"]
            items = [*anchors, *(g["item"] for g in groups.values() if g["item"]["display"] != "hide")]

            def rank(item):
                if item.get("name") in focus or item.get("rule") == "explicit-focus":
                    priority = 0
                elif item["kind"] == "function" and item.get("entry_point"):
                    priority = 1 if view == "behavior" else 2
                elif item["kind"] == "type":
                    priority = 1 if view == "structure" else (2 if item["roles"] else 4)
                elif item["kind"] == "function":
                    priority = 2
                else:
                    priority = 6 if item["display"] == "fold" else 3
                    if item["relation_kind"] in {"unknown", "macro"}:
                        priority = max(priority, 5)
                entry = self.functions.get(item.get("source"), {}).get("anchor", {}).get("entry_point", False)
                return (priority, not entry, -item.get("count", 0), item.get("name", item.get("target", "")), item["id"])

            items.sort(key=rank)
        end = offset + limit
        counts = Counter(r["public"]["kind"] for r in records)
        summary = {"facts": dict(sorted(counts.items())), "hidden_by_rule": dict(sorted(hidden.items()))}
        summary["unresolved_symbols"] = sum(r["public"]["kind"] == "symbol"
                                            and r["public"]["fact"]["kind"] == "unknown" for r in records)
        if level == "system":
            summary.update(units=len(self.units), files=len(self.paths), types=len(self.types), functions=len(self.functions),
                           unclassified_types=sum(not t["anchor"]["roles"] for t in self.types.values()))
        return result_document(
            "ue_inspect_cxx_scope",
            {"scope": {"id": self.profile["id"], "name": self.profile["name"]},
             "snapshot": self.snapshot, "level": level, "view": view, "focus": focus,
             **details, "summary": summary, "items": items[offset:end],
             "page": {"offset": offset, "limit": limit, "total": len(items),
                      "next_offset": end if end < len(items) else None}},
            self.problems, responsibility=RESPONSIBILITY, boundaries=BOUNDARIES,
        )
