"""Selected-file name lookup shared by calls, addresses and delegate subjects."""
from __future__ import annotations


def lookup(name, scope, table):
    if name.startswith("::"):
        return table.get(name[2:])
    parts = scope.split("::") if scope else []
    for depth in range(len(parts), -1, -1):
        found = table.get("::".join([*parts[:depth], name]))
        if found is not None:
            return found
    return None


def syntax_name(node):
    if not node:
        return ""
    if node["kind"] == "qualified_identifier" and "name" in node:
        return syntax_name(node.get("scope")) + "::" + node["name"].strip()
    return node["expression"].strip()


class LocalNameResolver:
    def __init__(self, model):
        self.model = model
        self.types = self._table(model["types"], "type")
        self.aliases = self._table(model["aliases"], "alias")
        self.globals = self._table(model["variables"], "global")
        self.fields = self._table([
            {**field, "qualified_name": item["qualified_name"] + "::" + field["name"]}
            for item in model["types"] for field in item.get("fields", [])
        ], "member")
        self.functions = {}
        for function in model["functions"]:
            self.functions.setdefault(function["qualified_name"], []).append(function)
            if function.get("source_qualified_name"):
                self.functions.setdefault(function["source_qualified_name"], []).append(function)
        self.names = {}
        for kind, table in (("type", self.types), ("type", self.aliases),
                            ("global", self.globals), ("member", self.fields),
                            ("function", self.functions)):
            for name, value in table.items():
                previous = self.names.get(name)
                # An out-of-class static data definition and its member
                # declaration describe the same object.
                if kind == "member" and previous and previous["kind"] == "global":
                    # Use the class declaration's type in its lexical scope;
                    # a definition can qualify nested names or omit `class`.
                    previous["value"] = {**previous["value"], "type": value.get("type", {}),
                                         "ambiguous": previous["value"].get("ambiguous") or value.get("ambiguous")}
                    continue
                self.names[name] = {"kind": "ambiguous"} if previous else {"kind": kind, "value": value}

    @staticmethod
    def _table(items, kind):
        groups = {}
        for item in items:
            groups.setdefault(item["qualified_name"], []).append(item)
        result = {}
        for name, candidates in groups.items():
            definitions = [c for c in candidates if c.get("role") == "definition"]
            item = (definitions or candidates)[0]
            expressions = {c.get("type", {}).get("expression") for c in candidates}
            ambiguous = len(expressions) > 1 or kind == "type" and len(definitions) > 1
            result[name] = {**item, "ambiguous": ambiguous}
        return result

    def resolve(self, name, scope, bindings):
        if not name.startswith("::") and name.split("::")[0] in bindings:
            binding = bindings[name.split("::")[0]]
            return {"kind": binding["kind"], "value": binding} if "::" not in name else {"kind": "ambiguous"}
        return lookup(name, scope, self.names)

    def owner_type(self, fact, scope):
        if not fact or fact.get("is_placeholder") or fact.get("ambiguous"):
            return ""
        expression = fact.get("expression", "")
        alias = lookup(expression, fact.get("scope", scope), self.aliases)
        if alias and alias.get("ambiguous"):
            return ""
        known = lookup(expression, fact.get("scope", scope), self.types)
        if known:
            return "" if known.get("ambiguous") else known["qualified_name"]
        return expression

    def subject(self, node, call, scope):
        unknown = {"expression": node["expression"] if node else "", "kind": "unknown",
                   "qualified_name": None}
        if node is None:
            return unknown, None
        kind = node["kind"]
        name = syntax_name(node)
        if kind == "parenthesized_expression":
            return self.subject(node["operand"], call, scope)
        if kind == "pointer_expression" and node.get("operator") == "*":
            return self.subject(node["operand"], call, scope)
        if kind in {"identifier", "qualified_identifier", "type_identifier"}:
            found = self.resolve(name, scope, call["bindings"])
            if found and found["kind"] in {"parameter", "local", "member", "global"}:
                item = found["value"]
                fact = item.get("type", {})
                if item.get("ambiguous"):
                    fact = {"is_placeholder": True}
                qualified = item.get("qualified_name")
                if qualified:
                    fact = {**fact, "scope": qualified.rpartition("::")[0]}
                return {**unknown, "kind": found["kind"], "qualified_name": qualified}, fact
            return unknown, None
        if kind == "this":
            owner = self.enclosing_type(scope)
            return {**unknown, "kind": "member"}, {"expression": owner["qualified_name"]} if owner else None
        if kind == "field_expression":
            _, receiver_type = self.subject(node["receiver"], call, scope)
            owner_name = self.owner_type(receiver_type, scope)
            field = self.fields.get(owner_name + "::" + node["name"])
            if field:
                fact = {"is_placeholder": True} if field.get("ambiguous") else {**field["type"], "scope": owner_name}
                return {**unknown, "kind": "member", "qualified_name": field["qualified_name"]}, fact
            return {**unknown, "kind": "member"}, None
        if kind == "call_expression":
            callee = node["function"]
            target = syntax_name(callee)
            if callee["kind"] == "field_expression":
                _, receiver_type = self.subject(callee["receiver"], call, scope)
                target = self.owner_type(receiver_type, scope) + "::" + callee["name"]
            found = self.resolve(target, scope, call["bindings"])
            functions = found["value"] if found and found["kind"] == "function" else []
            returns = {f["return_type"]["expression"] for f in functions}
            return {**unknown, "kind": "return_value"}, {**functions[0]["return_type"], "scope": functions[0]["qualified_name"].rpartition("::")[0]} if len(returns) == 1 else None
        return unknown, None

    def enclosing_type(self, scope):
        while scope:
            if scope in self.types:
                return self.types[scope]
            scope = scope.rpartition("::")[0]
        return None

