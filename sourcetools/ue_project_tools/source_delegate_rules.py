from __future__ import annotations


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


def ue_delegate_operation(api: str) -> str | None:
    if api in UE_DELEGATE_PUBLISH_APIS:
        return "publish"
    if api in UE_DELEGATE_SUBSCRIBE_APIS:
        return "subscribe"
    return None
