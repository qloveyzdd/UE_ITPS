"""Bounded UE API role hints; never compiler bindings or overload decisions."""
from __future__ import annotations

import re

from .source_name_resolution import lookup
from .ue_cpp_conventions import UE_SCOPE_POINTER_WRAPPERS

ACTOR_COMPONENT_METHODS = frozenset({
    "SetIsReplicatedByDefault", "IsUsingRegisteredSubObjectList",
    "IsReadyForReplication", "AddReplicatedSubObject", "RemoveReplicatedSubObject",
})
FAST_ARRAY_METHODS = frozenset({"MarkItemDirty", "MarkArrayDirty"})
ABILITY_SYSTEM_METHODS = frozenset({
    "GiveAbility", "AddAttributeSetSubobject", "ApplyGameplayEffectSpecToSelf",
    "MakeOutgoingSpec", "MakeEffectContext", "RemoveActiveEffects",
    "HasMatchingGameplayTag", "FindAbilitySpecFromHandle", "TryActivateAbility",
    "InvokeReplicatedEvent", "GetAvatarActor",
})
COMPONENT_BASES = frozenset({"UActorComponent", "UPawnComponent"})
TYPE_CONSTRUCTORS = frozenset({"FGameplayTagContainer", "FGameplayAbilitySpecHandleAndPredictionKey"})
NESTED_ROLES = {
    ("call_expression", "GetDynamicSpecSourceTags", "AddTag", "FGameplayAbilitySpec"): "gameplay_tag_write",
    ("call_expression", "GetDynamicSpecSourceTags", "HasTagExact", "FGameplayAbilitySpec"): "gameplay_tag_query",
    ("call_expression", "GetCurrentActivationInfo", "GetActivationPredictionKey", "UGameplayAbility"): "activation_prediction_key",
    ("field_expression", "ActivationInfo", "GetActivationPredictionKey", "FGameplayAbilitySpec"): "activation_prediction_key",
    ("field_expression", "DynamicGrantedTags", "AddTag", "FGameplayEffectSpec"): "gameplay_tag_write",
    ("field_expression", "Data", "Get", "FGameplayEffectSpecHandle"): "handle_storage_access",
}


def _contract(kind, name, *, owner=None, template_type=None, effect=None):
    result = {"kind": kind, "name": name, "source": "ue_api_contract"}
    for key, value in (("owner", owner), ("template_type", template_type), ("effect", effect)):
        if value:
            result[key] = value
    return result


def _family(fact, scope, resolver, *, arrow=False, visited=None):
    if not fact or fact.get("ambiguous") or fact.get("is_placeholder"):
        return set()
    name = re.sub(r"^(?:const|volatile)\s+", "", str(fact.get("expression") or "")).strip(" *&")
    if arrow:
        wrapper = re.fullmatch(r"(\w+)\s*<\s*(?:const\s+)?([\w:]+)\s*>", name)
        if wrapper and wrapper[1] in UE_SCOPE_POINTER_WRAPPERS:
            name = wrapper[2]
    scope = fact.get("scope", scope)
    visited = set() if visited is None else visited
    key = (scope, name)
    if not name or key in visited:
        return set()
    visited.add(key)
    alias = lookup(name, scope, resolver.aliases)
    if alias:
        return set() if alias.get("ambiguous") else _family(alias.get("type"), alias["qualified_name"].rpartition("::")[0], resolver, visited=visited)
    definition = lookup(name, scope, resolver.types)
    if not definition:
        return {name.removeprefix("::")}
    if definition.get("ambiguous"):
        return set()
    result = {definition["qualified_name"]}
    for base in definition.get("base_type_facts", []):
        result.update(_family(base, definition["qualified_name"], resolver, visited=visited))
    return result


def contracts_for_call(call, function, resolver):
    """Use declared receiver types and unshadowed names, never suffixes alone."""
    target, callee = call["target_name"], call["callee"]
    syntax = call["syntax"]["function"]
    scope = function["qualified_name"]
    direct = call["receiver_kind"] is None and call["callee_path"] == [target]
    global_name = syntax["expression"].lstrip().startswith("::")
    found = resolver.resolve(("::" if global_name else "") + target, scope, call["bindings"]) if direct else None
    template_type = (call.get("template_arguments") or [None])[0]
    if direct and not found:
        if target in {"Cast", "CastChecked"} and template_type:
            return [_contract("type_narrowing", callee, template_type=template_type, effect="narrows_or_checks_the_runtime_object_type")]
        if target in {"GetDefault", "NewObject"} and template_type:
            effect = "reads_class_default_object" if target == "GetDefault" else "constructs_ue_object"
            return [_contract("ue_factory", callee, template_type=template_type, effect=effect)]
        if target in TYPE_CONSTRUCTORS:
            return [_contract("type_constructor", callee, effect="constructs_value_object")]
    if direct and found and found["kind"] in {"local", "parameter"}:
        types = _family(found["value"].get("type"), scope, resolver)
        if any(re.fullmatch(r"TFunction(?:Ref)?\s*<\s*bool\s*\(.*\)\s*>", t) for t in types):
            return [_contract("callback_predicate", callee, effect="evaluates_boolean_callback")]

    def subject_types(node, arrow=False):
        _, fact = resolver.subject(node, call, scope)
        return _family(fact, scope, resolver, arrow=arrow)

    receiver = syntax.get("receiver")
    current = _family({"expression": function.get("owner", "")}, scope, resolver)
    owners = subject_types(receiver, syntax.get("operator") == "->") if receiver else (current if direct and not global_name and not found else set())
    if target in ACTOR_COMPONENT_METHODS and owners & COMPONENT_BASES:
        return [_contract("replication_lifecycle", callee, owner="UActorComponent")]
    if target in FAST_ARRAY_METHODS and "FFastArraySerializer" in owners:
        return [_contract("fast_array_replication", callee, owner="FFastArraySerializer", effect="marks_replication_dirty")]
    if target in ABILITY_SYSTEM_METHODS and "UAbilitySystemComponent" in owners:
        return [_contract("ability_system_api", callee, owner="UAbilitySystemComponent")]
    if target == "HasAuthority" and "AActor" in owners:
        return [_contract("authority_check", callee, owner="AActor", effect="checks_authority")]
    if not receiver:
        return []
    if target == "Find" and receiver["kind"] == "identifier" and receiver["expression"] == "AbilityTargetDataMap" and "UAbilitySystemComponent" in current and not resolver.resolve("AbilityTargetDataMap", scope, call["bindings"]):
        return [_contract("target_data_lookup", callee, owner="UAbilitySystemComponent")]
    intermediate = receiver.get("function") if receiver["kind"] == "call_expression" else receiver
    if not intermediate or intermediate["kind"] != "field_expression":
        return []
    roots = subject_types(intermediate.get("receiver"), intermediate.get("operator") == "->")
    member = intermediate["name"]
    if any(owner + "::" + member in table for owner in roots for table in (resolver.functions, resolver.fields)):
        return []
    if target == "HasAuthority" and receiver["kind"] == "call_expression" and member == "GetOwner" and roots & COMPONENT_BASES:
        return [_contract("authority_check", callee, owner="AActor", effect="checks_authority")]
    for (node_kind, step, method, root_type), kind in NESTED_ROLES.items():
        if receiver["kind"] == node_kind and member == step and target == method and root_type in roots:
            return [_contract(kind, callee, owner=root_type)]
    return []
