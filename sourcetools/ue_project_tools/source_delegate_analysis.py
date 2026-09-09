"""One evidence-based delegate analysis shared by operations and callback symbols."""
from .source_name_resolution import LocalNameResolver, lookup as _lookup, syntax_name
from .ue_cpp_conventions import (
    delegate_api_rule, UE_DELEGATE_DECLARATIONS, UE_DELEGATE_TEMPLATE_TYPES,
)


def _evidence(item):
    return {"unit": "header" if item["file"].endswith((".h", ".hpp")) else "cpp",
            "line": item["line"]}


def _operation_id(unit, syntax):
    # A chained outer call and its receiver call can start at the same byte.
    return f'{unit}:{syntax["line"]}:{syntax["column"]}:{syntax["end_offset"]}'


class DelegateAnalyzer(LocalNameResolver):
    def __init__(self, model):
        super().__init__(model)
        self.delegates = {}
        for macro in model["macros"]:
            rule = UE_DELEGATE_DECLARATIONS.get(macro["name"])
            if not rule or len(macro["arguments"]) <= rule["type_argument"]:
                continue
            name = macro["arguments"][rule["type_argument"]]["expression"].strip()
            qualified = "::".join(filter(None, (macro.get("scope"), name)))
            fact = {"qualified_name": qualified, "cardinality": rule["cardinality"],
                    "dispatch": rule["dispatch"], "policy": rule["policy"],
                    "evidence": _evidence(macro)}
            # Conflicting conditional definitions must not silently pick one branch.
            if qualified in self.delegates and self.delegates[qualified] != fact:
                self.delegates[qualified] = {**fact, "ambiguous": True}
            else:
                self.delegates[qualified] = fact

    def type_info(self, fact, scope, seen=()):
        scope = (fact or {}).get("scope", scope)
        expression = fact.get("expression", "") if fact else ""
        name = expression
        if not name:
            return None, False
        delegate = _lookup(name, scope, self.delegates)
        if delegate:
            return {"expression": expression, **delegate}, False
        alias = _lookup(name, scope, self.aliases)
        if alias:
            if alias.get("ambiguous") or alias["qualified_name"] in seen:
                return None, False
            resolved, ordinary = self.type_info(alias["type"], alias["qualified_name"].rpartition("::")[0],
                                                (*seen, alias["qualified_name"]))
            return ({**resolved, "expression": expression} if resolved else None), ordinary
        if name.endswith("::FDelegate"):
            outer = _lookup(name.removesuffix("::FDelegate"), scope, self.delegates)
            if outer and outer["cardinality"] == "multicast":
                return {**outer, "expression": expression, "cardinality": "single",
                        "qualified_name": outer["qualified_name"] + "::FDelegate"}, False
        template = fact.get("template_name")
        if template in UE_DELEGATE_TEMPLATE_TYPES:
            cardinality, dispatch = UE_DELEGATE_TEMPLATE_TYPES[template]
            return {"expression": expression, "qualified_name": None,
                    "cardinality": cardinality, "dispatch": dispatch,
                    "policy": None, "evidence": None}, False
        return None, bool(_lookup(name, scope, self.types) or template)

    def subject(self, node, call, scope):
        if node and node["kind"] == "call_expression":
            unknown = {"expression": node["expression"], "kind": "unknown", "qualified_name": None}
            callee = node["function"]
            factory = delegate_api_rule(callee.get("name", ""), None)
            if factory and factory["operation"] == "create" and callee.get("scope"):
                fact = {"expression": callee["scope"]["expression"],
                        "template_name": callee["scope"].get("name")}
                delegate, _ = self.type_info(fact, scope)
                if delegate and delegate["cardinality"] == factory["cardinality"] and delegate["dispatch"] == factory["dispatch"]:
                    return {**unknown, "kind": "temporary"}, fact
        return super().subject(node, call, scope)

    def callback(self, argument, role, scope, call):
        if argument is None:
            return None
        raw = argument["expression"]
        result = {"kind": "unknown", "expression": raw, "qualified_name": None,
                  "source_operation": None}
        if role == "function_name":
            return {**result, "kind": "reflection_name"}
        if role == "delegate":
            return {**result, "kind": "delegate_value"}
        if argument["kind"] == "lambda_expression":
            return {**result, "kind": "lambda"}
        target = argument.get("operand") if argument["kind"] == "pointer_expression" else argument
        if target and target["kind"] in {"identifier", "qualified_identifier"}:
            name = syntax_name(target)
            found = self.resolve(name, scope, call["bindings"])
            if found and found["kind"] != "function":
                return result
            functions = found["value"] if found else None
            member = "::" in name
            if functions:
                member = bool(functions[0].get("owner")) and "static" not in functions[0].get("qualifiers", [])
            return {**result, "kind": "member_function" if member else "function",
                    "qualified_name": functions[0]["qualified_name"] if functions else None}
        return result

    def analyze(self, function, references):
        scope = function["qualified_name"]
        unit = _evidence(function)["unit"]
        operations = []
        callback_offsets = set()
        callback_symbols = []
        for call in references["call_details"]:
            api = call["target_name"]
            rule = delegate_api_rule(api, None)
            if not rule or call["receiver_kind"] not in {"member", "scope"}:
                continue
            callee = call["syntax"]["function"]
            if rule["operation"] == "create":
                if call["receiver_kind"] != "scope":
                    continue
                subject = {"expression": call["receiver"], "kind": "type", "qualified_name": None}
                fact = {"expression": call["receiver"], "template_name": (callee.get("scope") or {}).get("name")}
            else:
                receiver = callee.get("receiver")
                if receiver is None:
                    receiver = {"kind": "qualified_identifier", "expression": call["receiver"] or ""}
                subject, fact = self.subject(receiver, call, scope)
            dtype, ordinary = self.type_info(fact, scope)
            if ordinary:
                continue
            rule = delegate_api_rule(api, dtype["dispatch"] if dtype else None)
            reasons = []
            if dtype is None:
                reasons.append("delegate-type-not-visible")
            elif dtype.pop("ambiguous", False):
                reasons.append("ambiguous-delegate-declaration")
            if dtype and rule["cardinality"] and dtype["cardinality"] != rule["cardinality"]:
                reasons.append("incompatible-delegate-cardinality")
            if dtype and rule["dispatch"] and dtype["dispatch"] != rule["dispatch"]:
                reasons.append("incompatible-delegate-dispatch")
            args = call["argument_syntax"]
            if len(args) < len(rule["roles"]) or (rule["tail"] is None and len(args) != len(rule["roles"])):
                reasons.append("unsupported-argument-shape")
            callback = None
            callback_arg = None
            arguments = []
            for index, argument in enumerate(args):
                role = rule["roles"][index] if index < len(rule["roles"]) else rule["tail"] or "unknown"
                arguments.append({"role": role, "expression": argument["expression"]})
                if role in {"callback", "delegate", "function_name"}:
                    callback_arg = argument
                    callback = self.callback(argument, role, scope, call)
                    if role == "callback" and rule["callback_form"] == "functor" and argument["kind"] != "lambda_expression":
                        callback["kind"] = "unknown"
                        callback["qualified_name"] = None
                    elif role == "callback" and rule["callback_form"] == "function" and callback["kind"] in {"member_function", "function"}:
                        callback["kind"] = "function"
                    target = argument.get("operand") or argument
                    if role == "callback" and target["kind"] in {"identifier", "qualified_identifier"}:
                        _, target_type = self.subject(target, call, scope)
                        if target_type is not None:
                            callback["kind"] = "unknown"
                            callback["qualified_name"] = None
                    if role == "delegate" and argument["kind"] == "pointer_expression":
                        reasons.append("delegate-value-required")
            evidence = {"unit": unit, "line": call["syntax"]["line"], "column": call["syntax"]["column"]}
            operation_id = _operation_id(unit, call["syntax"])
            if subject["kind"] == "type" and dtype:
                subject["qualified_name"] = dtype["qualified_name"]
            result = None
            if call["result_target"]:
                result = {"expression": call["result_target"],
                          "kind": rule["result"]}
            if dtype is None and fact and fact.get("expression"):
                dtype = {"expression": fact["expression"], "qualified_name": None,
                         "cardinality": None, "dispatch": None, "policy": None, "evidence": None}
            operation = {
                "operation_id": operation_id, "operation": rule["operation"], "api": api,
                "subject": subject, "delegate_type": dtype, "callback": callback,
                "binding": rule["binding"], "arguments": arguments, "result": result,
                "resolution": {"status": "candidate" if reasons else "identified", "reasons": reasons},
                "execution_scope": call["execution_scope"], "evidence": evidence,
            }
            operations.append(operation)
            if callback and not reasons and callback["kind"] in {"member_function", "function"}:
                callback_offsets.add(callback_arg["start_offset"])
                target = callback_arg.get("operand") or callback_arg
                callback_symbols.append({"kind": "callback_target", "spelling": target["expression"],
                                         "line": target["line"], "start_offset": callback_arg["start_offset"]})
        # Directly nested creation is traceable without following variable data flow.
        by_location = {o["operation_id"]: o for o in operations}
        calls_by_location = {_operation_id(unit, c["syntax"]): c for c in references["call_details"]}
        for operation in operations:
            callback = operation["callback"]
            if not callback:
                continue
            call = calls_by_location[operation["operation_id"]]
            for arg in call["argument_syntax"]:
                if arg["expression"] != callback["expression"]:
                    continue
                nested_id = _operation_id(unit, arg)
                nested = by_location.get(nested_id)
                if nested and nested["operation"] == "create" and nested_id != operation["operation_id"]:
                    callback["source_operation"] = nested_id
        symbols = [s for s in references["external_symbols"]
                   if not (s["kind"] in {"function_address", "unknown"} and s["start_offset"] in callback_offsets)]
        symbols.extend(callback_symbols)
        references["external_symbols"] = sorted(symbols, key=lambda s: s["start_offset"])
        references["delegate_operations"] = operations


def analyze_delegates(model):
    analyzer = DelegateAnalyzer(model)
    for function in model["functions"]:
        if function["role"] == "definition":
            analyzer.analyze(function, model["references"][function["occurrence_id"]])
