from __future__ import annotations

from collections.abc import Sequence


UE_FUNCTION_LIKE_MACROS = frozenset(
    {
        "ABILITYLIST_SCOPE_LOCK",
        "ASSERT_THAT",
        "CSV_CATEGORY_INDEX",
        "CSV_EVENT",
        "CSV_METADATA",
        "DISABLE_REPLICATED_PROPERTY",
        "DOREPLIFETIME",
        "DOREPLIFETIME_CONDITION",
        "DOREPLIFETIME_CONDITION_NOTIFY",
        "DOREPLIFETIME_WITH_PARAMS_FAST",
        "GAMEPLAYATTRIBUTE_REPNOTIFY",
        "GET_FUNCTION_NAME_CHECKED",
        "GET_MEMBER_NAME_CHECKED",
        "INVTEXT",
        "LOCTEXT",
        "MARK_PROPERTY_DIRTY_FROM_NAME",
        "NSLOCTEXT",
        "QUICK_SCOPE_CYCLE_COUNTER",
        "RETURN_QUICK_DECLARE_CYCLE_STAT",
        "SCOPED_BOOT_TIMING",
        "SCOPE_LOG_TIME_IN_SECONDS",
        "TEXT",
        "TRACE_CPUPROFILER_EVENT_SCOPE",
        "UE_ARRAY_COUNT",
        "UE_CLOG",
        "UE_LOG",
    }
)

UE_SAME_TYPE_STATIC_ACCESSORS = frozenset({"Get"})

UE_IGNORED_EXTERNAL_MACROS = frozenset({"LOCTEXT"})

UE_IGNORED_EXTERNAL_MEMBER_CALLS = frozenset(
    {
        ("FText", "Format"),
        ("FText", "FromName"),
    }
)

# Presentation policy only. Matching uses frontend type/callee facts, not text
# patterns. Unlisted methods (including forwarded calls through pointers) remain.
UE_RETRIEVAL_RULES_VERSION = 1
UE_RETRIEVAL_RULES = (
    {
        "id": "container-query", "match": "member",
        "owners": frozenset({"TMap", "TMultiMap", "TArray", "TSet"}),
        "names": frozenset({"Find", "FindChecked", "FindRef", "Contains", "Num", "IsEmpty", "IsValidIndex", "GetData"}),
        "behavior": "hide", "structure": "hide",
    },
    {
        "id": "container-update", "match": "member",
        "owners": frozenset({"TMap", "TMultiMap", "TArray", "TSet"}),
        "names": frozenset({"Add", "AddUnique", "Emplace", "Append", "FindOrAdd", "Remove", "RemoveAll", "RemoveAt", "Reset", "Empty", "Reserve", "SetNum"}),
        "behavior": "fold", "structure": "fold",
    },
    {
        "id": "pointer-access", "match": "member",
        "owners": frozenset({"TSharedPtr", "TSharedRef", "TWeakPtr", "TWeakObjectPtr", "TWeakInterfacePtr", "TObjectPtr", "TSoftObjectPtr", "TSoftClassPtr", "TUniquePtr"}),
        "names": frozenset({"Get", "IsValid", "IsSet", "Pin"}),
        "behavior": "hide", "structure": "hide",
    },
    {
        "id": "text-formatting", "match": "member",
        "owners": frozenset({"FString", "FText", "FName"}),
        "names": frozenset({"Printf", "Format", "FromName", "FromString", "ToString"}),
        "behavior": "hide", "structure": "hide",
    },
    {
        "id": "text-macro", "match": "macro",
        "names": frozenset({"TEXT", "LOCTEXT", "NSLOCTEXT", "INVTEXT"}),
        "behavior": "hide", "structure": "hide",
    },
    {
        "id": "instrumentation", "match": "macro",
        "names": frozenset({"UE_LOG", "UE_CLOG", "CSV_CATEGORY_INDEX", "CSV_EVENT", "CSV_METADATA", "QUICK_SCOPE_CYCLE_COUNTER", "RETURN_QUICK_DECLARE_CYCLE_STAT", "SCOPED_BOOT_TIMING", "SCOPE_LOG_TIME_IN_SECONDS", "TRACE_CPUPROFILER_EVENT_SCOPE"}),
        "behavior": "hide", "structure": "hide",
    },
    {
        "id": "basic-value-type", "match": "type",
        "names": frozenset({"int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64", "FString", "FName", "FText", "FVector", "FVector2D", "FRotator", "FQuat", "FTransform"}),
        "behavior": "hide", "structure": "fold",
    },
)

UE_RETRIEVAL_TYPE_DISPLAY = {"behavior": "fold", "structure": "expand"}
UE_RETRIEVAL_DEFINITION_DISPLAY = {
    "behavior": {"classes": "fold", "structs": "fold", "enums": "fold", "global_variables": "expand", "free_functions": "expand", "macros": "fold"},
    "structure": {"classes": "expand", "structs": "expand", "enums": "expand", "global_variables": "expand", "free_functions": "fold", "macros": "fold"},
}

UE_DECLARATION_ANNOTATION_MACROS = {
    "type": frozenset({"UCLASS", "USTRUCT", "UENUM", "UINTERFACE"}),
    "field": frozenset({"UPROPERTY"}),
    "function": frozenset({"UFUNCTION"}),
}

UE_GAMEPLAY_TAG_SYMBOL_MACROS = {
    "UE_DECLARE_GAMEPLAY_TAG_EXTERN": ("declaration", "external"),
    "UE_DEFINE_GAMEPLAY_TAG": ("definition", "external"),
    "UE_DEFINE_GAMEPLAY_TAG_COMMENT": ("definition", "external"),
    "UE_DEFINE_GAMEPLAY_TAG_STATIC": ("definition", "internal"),
}

# CQTest.h: these source declarations own the following function body.
UE_TEST_LIFECYCLE_METHODS = {"BEFORE_EACH": "Setup", "AFTER_EACH": "TearDown"}

# UE 5.8 delegate API contract. Exact names only; roles refer to argument indexes.
# Syntax classification and type evidence are handled by the single delegate analyzer.
UE_DELEGATE_APIS = {}
for prefix, operation, cardinality in (
    ("Create", "create", "single"), ("Bind", "bind", "single"),
    ("Add", "add", "multicast"),
):
    for suffix, roles, binding in (
        ("Static", ("callback",), "static"),
        ("Raw", ("object", "callback"), "raw"),
        ("SP", ("object", "callback"), "shared_weak"),
        ("ThreadSafeSP", ("object", "callback"), "shared_weak"),
        ("UObject", ("object", "callback"), "uobject_weak"),
        ("UFunction", ("object", "function_name"), "uobject_weak"),
        ("Lambda", ("callback",), "lambda"),
        ("SPLambda", ("object", "callback"), "shared_weak"),
        ("WeakLambda", ("object", "callback"), "uobject_weak"),
    ):
        UE_DELEGATE_APIS[prefix + suffix] = {
            "operation": operation, "cardinality": cardinality, "dispatch": "native",
            "roles": roles, "tail": "payload", "binding": binding,
            "callback_form": "functor" if suffix in {"Lambda", "SPLambda", "WeakLambda"} else
                             "function" if suffix == "Static" else "member",
            "result": "delegate" if operation == "create" else "handle" if operation == "add" else "value",
        }
for api, operation, cardinality in (
    ("BindDynamic", "bind", "single"), ("AddDynamic", "add", "multicast"),
    ("AddUniqueDynamic", "add", "multicast"), ("RemoveDynamic", "remove", "multicast"),
    ("IsAlreadyBound", "query", "multicast"),
):
    UE_DELEGATE_APIS[api] = {
        "operation": operation, "cardinality": cardinality, "dispatch": "dynamic",
        "roles": ("object", "callback"), "tail": "payload", "binding": "uobject_weak",
        "callback_form": "member", "result": "value",
    }
for api, operation, cardinality, roles, tail in (
    ("Add", "add", "multicast", ("delegate",), None),
    ("AddUnique", "add", "multicast", ("delegate",), None),
    ("Unbind", "unbind", "single", (), None),
    ("Remove", "remove", "multicast", ("handle",), None),
    ("RemoveAll", "remove", "multicast", ("object",), None),
    ("Clear", "clear", "multicast", (), None),
    ("Execute", "execute", "single", (), "invocation"),
    ("ExecuteIfBound", "execute", "single", (), "invocation"),
    ("Broadcast", "broadcast", "multicast", (), "invocation"),
    ("IsBound", "query", None, (), None),
    ("IsBoundToObject", "query", None, ("object",), None),
    ("GetHandle", "query", "single", (), None),
):
    UE_DELEGATE_APIS[api] = {
        "operation": operation, "cardinality": cardinality,
        "dispatch": "dynamic" if api == "AddUnique" else None,
        "roles": roles, "tail": tail, "binding": None,
        "callback_form": "delegate" if operation == "add" else None,
        "result": "handle" if api == "GetHandle" else "value",
    }


def delegate_api_rule(api: str, dispatch: str | None) -> dict | None:
    rule = UE_DELEGATE_APIS.get(api)
    if rule is None:
        return None
    if api == "Remove" and dispatch == "dynamic":
        return {**rule, "roles": ("object", "function_name"), "tail": "payload"}
    if api == "Add" and dispatch == "native":
        return {**rule, "result": "handle"}
    return rule

UE_DELEGATE_TEMPLATE_TYPES = {
    "TDelegate": ("single", "native"),
    "TMulticastDelegate": ("multicast", "native"),
    "TDynamicDelegate": ("single", "dynamic"),
    "TDynamicMulticastDelegate": ("multicast", "dynamic"),
}
UE_DELEGATE_CONTRACT_REVISION = 2

_UE_DELEGATE_PARAMETER_SUFFIXES = (
    "",
    "_OneParam",
    "_TwoParams",
    "_ThreeParams",
    "_FourParams",
    "_FiveParams",
    "_SixParams",
    "_SevenParams",
    "_EightParams",
    "_NineParams",
)

UE_DELEGATE_DECLARATIONS = {}
for prefix, index, cardinality, dispatch, policy in (
    ("DECLARE_DELEGATE", 0, "single", "native", None),
    ("DECLARE_DELEGATE_RetVal", 1, "single", "native", None),
    ("DECLARE_DYNAMIC_DELEGATE", 0, "single", "dynamic", None),
    ("DECLARE_DYNAMIC_DELEGATE_RetVal", 1, "single", "dynamic", None),
    ("DECLARE_MULTICAST_DELEGATE", 0, "multicast", "native", None),
    ("DECLARE_DYNAMIC_MULTICAST_DELEGATE", 0, "multicast", "dynamic", None),
    ("DECLARE_TS_MULTICAST_DELEGATE", 0, "multicast", "native", "thread_safe"),
    ("DECLARE_EVENT", 1, "multicast", "native", "event"),
):
    for suffix in _UE_DELEGATE_PARAMETER_SUFFIXES:
        UE_DELEGATE_DECLARATIONS[prefix + suffix] = {
            "type_argument": index, "cardinality": cardinality,
            "dispatch": dispatch, "policy": policy,
        }
UE_DELEGATE_DECLARATIONS["DECLARE_DERIVED_EVENT"] = {
    "type_argument": 2, "cardinality": "multicast", "dispatch": "native", "policy": "event",
}


def is_ue_function_like_macro(name: str) -> bool:
    return name in UE_FUNCTION_LIKE_MACROS


def is_ue_same_type_static_accessor(name: str) -> bool:
    return name in UE_SAME_TYPE_STATIC_ACCESSORS


def is_ignored_external_macro(name: str) -> bool:
    return name in UE_IGNORED_EXTERNAL_MACROS


def is_ignored_external_member_call(owner_type: str, method_name: str) -> bool:
    return (owner_type, method_name) in UE_IGNORED_EXTERNAL_MEMBER_CALLS


def is_ue_declaration_annotation(name: str, target: str) -> bool:
    return name in UE_DECLARATION_ANNOTATION_MACROS.get(target, ())


def is_ue_gameplay_tag_symbol_macro(name: str) -> bool:
    return name in UE_GAMEPLAY_TAG_SYMBOL_MACROS


def ue_gameplay_tag_symbol(
    macro_name: str, arguments: Sequence[str]
) -> tuple[str, str, str] | None:
    rule = UE_GAMEPLAY_TAG_SYMBOL_MACROS.get(macro_name)
    if rule is None or not arguments:
        return None
    symbol = arguments[0].strip()
    parts = symbol.split("::")
    if not parts or any(not part.isidentifier() for part in parts):
        return None
    role, linkage = rule
    return symbol, role, linkage
