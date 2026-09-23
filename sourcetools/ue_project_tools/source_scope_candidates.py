"""Evidence-backed declaration candidates within an explicit scope, never bindings."""
from __future__ import annotations

import re

from .source_name_resolution import LocalNameResolver, lookup
from .semantic_contracts import contracts_for_call
from .ue_cpp_conventions import UE_SCOPE_POINTER_WRAPPERS


NEXT_STEPS = {
    "declaration_not_in_scope": "Select the declaring header/source explicitly, then refresh the scope.",
    "receiver_type_unresolved": "Inspect the receiver declaration, alias or return type; select its defining unit.",
    "ambiguous_candidates": "Inspect every candidate signature and location; compiler configuration may be required.",
    "unsupported_expression": "Inspect the source expression; indirect calls need additional semantic evidence.",
    "requires_semantics": "Use template/macro or compiler evidence for the selected build configuration.",
    "unclassified_reference": "Inspect the located non-call reference; this index currently follows calls only.",
    "scope_candidate": "Follow the candidate locations; this is not a compiler-resolved or runtime call edge.",
    "macro": "Inspect the macro definition and preprocessing context; do not treat it as a function edge.",
    "semantic_contract": "A bounded UE API contract matched; compiler headers are still needed for exact overload and visibility.",
    "member_address": "Inspect the member declaration; this is an address/member reference, not an external call.",
}


class ScopeCandidateIndex:
    def __init__(self, scope):
        self.scope = scope
        self.model = {key: [item for unit in scope.units.values() for item in unit["cpp_model"][key]]
                      for key in ("types", "aliases", "variables", "functions")}
        self.resolvers = {}
        self.units = {}
        self.definition_ids = {item["raw"]["occurrence_id"]: key for key, item in scope.functions.items()}
        for unit_id, loaded in scope.units.items():
            for path, _ in loaded["parsed_files"]:
                self.units[path.as_posix().casefold()] = unit_id

    def _resolver(self, unit_id):
        if unit_id not in self.resolvers:
            def visible(item):
                local = item.get("anonymous_namespace") or (not item.get("owner") and item.get("linkage") == "internal")
                return not local or self.units[item["file"]] == unit_id
            self.resolvers[unit_id] = LocalNameResolver({key: [item for item in items if visible(item)]
                                                        for key, items in self.model.items()})
        return self.resolvers[unit_id]

    def _owner(self, fact, lexical_scope, resolver, arrow=False):
        if not fact or fact.get("ambiguous") or fact.get("is_placeholder"):
            return ""
        name = resolver.owner_type(fact, lexical_scope)
        # Only the explicitly supported UE wrapper and an actual -> expression.
        if arrow:
            match = re.fullmatch(r"(\w+)\s*<\s*(?:const\s+)?([\w:]+)\s*>", name)
            if match and match[1] in UE_SCOPE_POINTER_WRAPPERS:
                name = match[2]
        name = re.sub(r"^(?:const|volatile)\s+", "", name).strip(" *&")
        if not re.fullmatch(r"(?:::)?[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*", name):
            return ""
        known = lookup(name, fact.get("scope", lexical_scope), resolver.types)
        if known:
            return "" if known.get("ambiguous") else known["qualified_name"]
        return name

    def _members(self, owner, name, resolver, visited=None):
        visited = set() if visited is None else visited
        if owner in visited:
            return [], []
        visited.add(owner)
        direct = resolver.functions.get(owner + "::" + name, [])
        if direct:
            return direct, ["receiver_type_and_member_name"]
        definition = resolver.types.get(owner)
        if not definition or definition.get("ambiguous"):
            return [], []
        result = []
        for base in definition.get("base_type_facts", []):
            base_name = self._owner(base, owner, resolver)
            matches, _ = self._members(base_name, name, resolver, visited)
            result.extend(matches)
        return result, ["base_type_and_member_name"] if result else []

    def analyze(self, record):
        public, call = record["public"], record["call"]
        function = self.scope.functions[public["source"]]["raw"]
        source_unit = self.units[function["file"]]
        resolver = self._resolver(source_unit)
        fact = public["fact"]
        if public["kind"] == "symbol" and fact["kind"] == "macro":
            return self._result("macro")
        if call is None:
            expression = str(fact.get("spelling") or "")
            if re.fullmatch(r"&\s*[A-Za-z_]\w*(?:\s*(?:\.|->)\s*[A-Za-z_]\w*)+", expression):
                member = expression.lstrip("&").strip()
                return self._result("member_address", status="candidate", member={
                    "expression": expression,
                    "path": [part.strip() for part in re.split(r"\.|->", member)],
                })
            return self._result("unclassified_reference")
        syntax = call["syntax"]["function"]
        lexical_scope = function["qualified_name"]
        candidates, basis = [], []
        receiver_types = []
        owner = ""
        reason = "declaration_not_in_scope"
        if call["receiver_kind"] == "indirect":
            return self._result("unsupported_expression")
        if call["receiver_kind"] == "member":
            receiver = syntax.get("receiver")
            _, owner_fact = resolver.subject(receiver, call, lexical_scope)
            owner = self._owner(owner_fact, lexical_scope, resolver, syntax.get("operator") == "->")
            if not owner:
                reason = "receiver_type_unresolved"
            else:
                receiver_types = [item["anchor"] for item in self.scope.types.values()
                                  if item["anchor"]["name"] == owner
                                  and (not item["raw"].get("anonymous_namespace") or item["unit"] == source_unit)]
                candidates, basis = self._members(owner, call["target_name"], resolver)
        else:
            name = "::".join(call["callee_path"])
            if syntax["expression"].lstrip().startswith("::"):
                name = "::" + name
            found = resolver.resolve(name, lexical_scope, call["bindings"])
            if found and found["kind"] == "function":
                candidates, basis = found["value"], ["lexical_qualified_name"]
            elif found:
                reason = "ambiguous_candidates" if found["kind"] == "ambiguous" else "requires_semantics"
            elif function.get("owner") and len(call["callee_path"]) == 1:
                candidates, basis = self._members(function["qualified_name"].rpartition("::")[0], name, resolver)
        candidates = list({item["occurrence_id"]: item for item in candidates}.values())
        if not candidates:
            contracts = contracts_for_call(call, function, resolver)
            if contracts:
                return self._result("semantic_contract", status="candidate", contracts=contracts,
                                    receiver_types=receiver_types)
            if call.get("template_arguments") and reason == "declaration_not_in_scope":
                reason = "requires_semantics"
            return {**self._result(reason), "receiver_types": receiver_types}
        # Preserve declarations and definitions separately. Never pick an overload
        # from argument count, or collapse conditional definitions by spelling.
        signatures = {(item["qualified_name"], tuple(p["type_expression"] for p in item["parameter_facts"]),
                       tuple(q for q in item["qualifiers"] if q in {"const", "volatile", "&", "&&"}))
                      for item in candidates}
        definitions = [item for item in candidates if item["role"] == "definition"]
        ambiguous = len(signatures) > 1 or len(definitions) > 1
        result = self._result("ambiguous_candidates" if ambiguous else "scope_candidate")
        result["status"] = "ambiguous" if ambiguous else "candidate"
        result["basis"] = basis
        result["receiver_types"] = receiver_types
        for item in sorted(candidates, key=lambda f: (f["file"], f["start_offset"])):
            target = {"name": item["qualified_name"], "signature": item["signature"], "role": item["role"],
                      "unit": self.units[item["file"]],
                      "evidence": self.scope._evidence(item["file"], item["line"], item["column"])}
            target["evidence"]["byte_offset"] = item["start_offset"]
            if item["occurrence_id"] in self.definition_ids:
                target["function_id"] = self.definition_ids[item["occurrence_id"]]
            result["candidates"].append(target)
        return result

    @staticmethod
    def _result(reason, *, status="unresolved", contracts=None, receiver_types=None, member=None):
        result = {"status": status, "reason": reason, "next_step": NEXT_STEPS[reason],
                  "basis": ["ue_api_contract"] if contracts else (["member_address_syntax"] if member else []), "candidates": [],
                  "contracts": list(contracts or [])}
        if receiver_types is not None:
            result["receiver_types"] = receiver_types
        if member is not None:
            result["member"] = member
        return result
