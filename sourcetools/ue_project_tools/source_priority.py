"""Optional retrieval views over existing facts; never change semantic resolution."""
from __future__ import annotations

from collections import Counter
import json

from .source_name_resolution import LocalNameResolver
from .ue_cpp_conventions import (
    UE_RETRIEVAL_DEFINITION_DISPLAY, UE_RETRIEVAL_RULES,
    UE_RETRIEVAL_RULES_VERSION, UE_RETRIEVAL_TYPE_DISPLAY,
)


def validate_view(view, focus):
    if view not in {"full", "behavior", "structure"}:
        raise ValueError(f"Unknown retrieval view: {view}")
    if any(not name.strip() for name in focus):
        raise ValueError("Focus names must not be empty")
    if view == "full" and focus:
        raise ValueError("--focus requires --view behavior or structure")


def view_metadata(view, focus):
    return {"mode": view, "rules_version": UE_RETRIEVAL_RULES_VERSION,
            "focus": list(dict.fromkeys(name.strip() for name in focus))}


def definition_view(groups, view, focus):
    """Selected definitions are navigation anchors, so none are suppressed."""
    sections = dict(UE_RETRIEVAL_DEFINITION_DISPLAY[view])
    focus_names = {name.strip() for name in focus}
    for group, items in groups.items():
        if any(focus_names & {item.get("name"), item.get("qualified_name")}
               for item in items):
            sections[group] = "expand"
    return {**view_metadata(view, focus), "sections": sections}


class FunctionPriorityView:
    def __init__(self, model, view, focus=()):
        self.view = view
        self.focus = {name.strip() for name in focus}
        self.resolver = LocalNameResolver(model)
        # Index existing structured type facts, including template argument types.
        self.types = {}

        def collect(value):
            if isinstance(value, dict):
                if "expression" in value and "references" in value:
                    self.types.setdefault(value["expression"], value)
                for child in value.values():
                    collect(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    collect(child)

        for key in ("types", "variables", "functions", "aliases"):
            collect(model[key])
        for refs in model["references"].values():
            collect(refs.get("local_variables", []))

    def classify(self, symbol, call, function):
        kind = symbol["kind"]
        names = {symbol["spelling"], function["qualified_name"], function["name"]}
        match = "type" if kind == "type" else ""
        name = symbol["spelling"]
        owner = None
        if kind == "type":
            fact = self.types.get(name, {})
            names.update(fact.get("references", []))
            # A wrapper containing a basic type is not itself a basic value type.
            name = fact.get("qualified_name") or name
            known = self.resolver.resolve(name, function["qualified_name"], {})
            if known and known["kind"] == "type":
                name = known["value"]["qualified_name"]
        if call and kind in {"member_call", "macro", "free_function", "unknown"}:
            name = call["target_name"]
            names.update((name, call["callee"], call.get("target_owner")))
            callee = call["syntax"]["function"]
            if kind == "macro":
                match = "macro"
            elif kind == "member_call":
                _, fact = self.resolver.subject(callee.get("receiver"), call, function["qualified_name"])
                if fact and not fact.get("is_placeholder") and not fact.get("ambiguous"):
                    owner = fact.get("qualified_name")
                    names.update(fact.get("references", []))
                    known = self.resolver.resolve(owner or "", function["qualified_name"], {})
                    if known and known["kind"] == "type":
                        owner = known["value"]["qualified_name"]
                # For qualified static calls, use the AST scope's exact name.
                if owner is None and call["receiver_kind"] == "scope":
                    owner = call.get("target_owner")
                match = "member"
                names.add(owner)
        if self.focus & names:
            return "expand", "explicit-focus"
        for rule in UE_RETRIEVAL_RULES:
            if (rule["match"] == match and name in rule["names"]
                    and ("owners" not in rule or owner in rule["owners"])):
                return rule[self.view], rule["id"]
        if kind == "type":
            return UE_RETRIEVAL_TYPE_DISPLAY[self.view], "type-reference"
        return "expand", "unclassified-reference"

    def project(self, function, references, unit):
        calls = {call["start_offset"]: call for call in references["call_details"]}
        groups = {}
        hidden = Counter()
        source_count = 0
        for symbol in references["external_symbols"]:
            source_count += 1
            call = calls.get(symbol.get("start_offset"))
            display, rule = self.classify(symbol, call, function)
            if display == "hide":
                hidden[rule] += 1
                continue
            group = {key: value for key, value in symbol.items()
                     if key not in {"line", "start_offset"}}
            if call and symbol["kind"] in {"member_call", "macro", "free_function", "unknown"}:
                if call["receiver"]:
                    group["receiver"] = call["receiver"]
                if call["execution_scope"]["kind"] != "function":
                    group["execution_scope"] = call["execution_scope"]
            key = (json.dumps(group, sort_keys=True), display, rule)
            if key not in groups:
                groups[key] = {**group, "count": 0, "lines": []}
                if display != "expand":
                    groups[key]["display"] = display
                if rule != "unclassified-reference":
                    groups[key]["rule"] = rule
            group = groups[key]
            group["count"] += 1
            group["lines"].append(symbol["line"])
        ordered = sorted(groups.values(), key=lambda g: g.get("display", "expand") != "expand")
        return {
            "unit": unit,
            "symbol_groups": ordered,
            "view_summary": {
                "source_count": source_count,
                "hidden_by_rule": dict(sorted(hidden.items())),
            },
        }


def detailed_syntax_flow(references):
    return {
        "calls": [{"callee": call["callee"], "expression": call["expression"],
                   "arguments": call["arguments"], "location": {"line": call["line"],
                   "column": call["syntax"]["column"]},
                   "execution_scope": call["execution_scope"]}
                  for call in references["call_details"]],
        "controls": references["controls"],
    }
