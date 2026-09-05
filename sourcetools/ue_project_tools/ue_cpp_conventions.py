from __future__ import annotations

from collections.abc import Collection, Sequence


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

UE_DELEGATE_PUBLISH_APIS = frozenset(
    {
        "Broadcast",
        "Execute",
        "ExecuteIfBound",
    }
)

UE_DELEGATE_SUBSCRIBE_APIS = frozenset(
    {
        "AddDynamic",
        "AddLambda",
        "AddRaw",
        "AddSP",
        "AddStatic",
        "AddThreadSafeSP",
        "AddUFunction",
        "AddUniqueDynamic",
        "AddUObject",
        "AddWeakLambda",
        "BindDynamic",
        "BindLambda",
        "BindRaw",
        "BindSP",
        "BindStatic",
        "BindThreadSafeSP",
        "BindUFunction",
        "BindUObject",
        "BindWeakLambda",
        "CreateLambda",
        "CreateRaw",
        "CreateSP",
        "CreateStatic",
        "CreateThreadSafeSP",
        "CreateUFunction",
        "CreateUObject",
        "CreateWeakLambda",
    }
)

UE_AMBIGUOUS_DELEGATE_SUBSCRIBE_APIS = frozenset(
    {
        "Add",
        "AddUnique",
    }
)

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

UE_DELEGATE_DECLARATION_TYPE_ARGUMENTS = {
    **{
        f"{prefix}{suffix}": 0
        for prefix in (
            "DECLARE_DELEGATE",
            "DECLARE_DYNAMIC_DELEGATE",
            "DECLARE_DYNAMIC_MULTICAST_DELEGATE",
            "DECLARE_MULTICAST_DELEGATE",
            "DECLARE_TS_MULTICAST_DELEGATE",
        )
        for suffix in _UE_DELEGATE_PARAMETER_SUFFIXES
    },
    **{
        f"{prefix}{suffix}": 1
        for prefix in (
            "DECLARE_DELEGATE_RetVal",
            "DECLARE_DYNAMIC_DELEGATE_RetVal",
            "DECLARE_EVENT",
        )
        for suffix in _UE_DELEGATE_PARAMETER_SUFFIXES
    },
    **{
        f"DECLARE_DERIVED_EVENT{suffix}": 2
        for suffix in _UE_DELEGATE_PARAMETER_SUFFIXES
    },
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


def ue_delegate_declared_type(
    macro_name: str, arguments: Sequence[str]
) -> str | None:
    type_argument = UE_DELEGATE_DECLARATION_TYPE_ARGUMENTS.get(macro_name)
    if type_argument is None or type_argument >= len(arguments):
        return None
    declared_type = arguments[type_argument].strip()
    return declared_type.rsplit("::", 1)[-1] or None


def ue_delegate_operation(
    api: str,
    *,
    owner_type: str | None = None,
    known_delegate_types: Collection[str] = (),
) -> str | None:
    if api in UE_DELEGATE_PUBLISH_APIS:
        return "publish"
    if api in UE_DELEGATE_SUBSCRIBE_APIS:
        return "subscribe"
    if api in UE_AMBIGUOUS_DELEGATE_SUBSCRIBE_APIS and owner_type:
        short_owner = owner_type.rsplit("::", 1)[-1]
        if short_owner in known_delegate_types:
            return "subscribe"
    return None
