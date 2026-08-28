from __future__ import annotations


UE_FUNCTION_LIKE_MACROS = frozenset(
    {
        "INVTEXT",
        "LOCTEXT",
        "NSLOCTEXT",
    }
)

UE_SAME_TYPE_STATIC_ACCESSORS = frozenset({"Get"})

UE_IGNORED_EXTERNAL_MEMBER_CALLS = frozenset(
    {
        ("FText", "FromName"),
    }
)

UE_DELEGATE_PUBLISH_APIS = frozenset(
    {
        "Broadcast",
        "Execute",
        "ExecuteIfBound",
    }
)

UE_DELEGATE_SUBSCRIBE_APIS = frozenset(
    {
        "Add",
        "AddDynamic",
        "AddLambda",
        "AddRaw",
        "AddSP",
        "AddStatic",
        "AddThreadSafeSP",
        "AddUFunction",
        "AddUnique",
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


def is_ue_function_like_macro(name: str) -> bool:
    return name in UE_FUNCTION_LIKE_MACROS


def is_ue_same_type_static_accessor(name: str) -> bool:
    return name in UE_SAME_TYPE_STATIC_ACCESSORS


def is_ignored_external_member_call(owner_type: str, method_name: str) -> bool:
    return (owner_type, method_name) in UE_IGNORED_EXTERNAL_MEMBER_CALLS


def ue_delegate_operation(api: str) -> str | None:
    if api in UE_DELEGATE_PUBLISH_APIS:
        return "publish"
    if api in UE_DELEGATE_SUBSCRIBE_APIS:
        return "subscribe"
    return None
