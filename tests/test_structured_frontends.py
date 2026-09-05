from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

from tree_sitter import Language, Parser
import tree_sitter_ue_cpp

from tests.support import ROOT

sys.path.insert(0, str(ROOT / "sourcetools"))

from ue_project_tools.cpp_frontend import load_cpp_unit
from ue_project_tools.project_graph import build_project_graph
from ue_project_tools.syntax_tree import parse_csharp_model


class StructuredFrontendTests(unittest.TestCase):
    def test_csharp_operations_expose_structured_paths(self) -> None:
        model = parse_csharp_model(
            """
class SampleTarget : TargetRules
{
    void Configure()
    {
        this.ExtraModuleNames.AddRange(new string[] { "Sample" });
        Type = global::UnrealBuildTool.TargetType.Game;
    }
}
"""
        )
        operations = model["classes"][0]["methods"][0]["operations"]
        self.assertEqual(operations[0]["callee_path"], ["ExtraModuleNames", "AddRange"])
        self.assertEqual(operations[0]["member_name"], "AddRange")
        self.assertEqual(operations[1]["target_path"], ["Type"])
        self.assertEqual(
            operations[1]["value_path"],
            ["global", "UnrealBuildTool", "TargetType", "Game"],
        )

    def test_cpp_calls_expose_nested_template_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Sample.cpp"
            source.write_text(
                """
void FSample::Send()
{
    Router.BroadcastMessage<TEnvelope<FPayload>>(TAG_Test, Payload);
}
""",
                encoding="utf-8",
            )
            model = load_cpp_unit(source, [source], root)

        call = next(iter(model["references"].values()))["call_details"][0]
        self.assertEqual(call["callee_path"], ["Router", "BroadcastMessage"])
        self.assertEqual(call["target_name"], "BroadcastMessage")
        self.assertEqual(call["template_arguments"], ["TEnvelope<FPayload>"])

    def test_cpp_macro_association_uses_ast_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Sample.h"
            source.write_text(
                """
UCLASS()
// Comments are trivia and do not break the declaration association.
class ASample
{
    GENERATED_BODY()
};
""",
                encoding="utf-8",
            )
            model = load_cpp_unit(source, [source], root)

        sample = next(item for item in model["types"] if item["name"] == "ASample")
        self.assertEqual(sample["macros"], ["UCLASS()"])

    def test_only_declaration_annotations_attach_to_entities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Sample.h"
            source.write_text(
                """
DECLARE_DELEGATE(FBeforeSample)
UCLASS()
class ASample
{
    GENERATED_BODY()

    int32 Count;
    void Run();
};
""",
                encoding="utf-8",
            )
            model = load_cpp_unit(source, [source], root)

        sample = next(item for item in model["types"] if item["name"] == "ASample")
        self.assertEqual(sample["macros"], ["UCLASS()"])
        self.assertEqual(sample["fields"][0]["macros"], [])
        self.assertEqual(sample["methods"][0]["macros"], [])

    def test_slate_arguments_do_not_consume_following_members(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Sample.h"
            source.write_text(
                """
class SSample
{
public:
    SLATE_BEGIN_ARGS(SSample)
        : _Value(1)
    {
    }
    SLATE_ARGUMENT(int32, Value)
    SLATE_END_ARGS()

    void Construct();
    int32 Count;
};
""",
                encoding="utf-8",
            )
            model = load_cpp_unit(source, [source], root)

        sample = next(item for item in model["types"] if item["name"] == "SSample")
        self.assertEqual(model["diagnostics"], [])
        self.assertIn("Construct", {item["name"] for item in sample["methods"]})
        self.assertIn("Count", {item["name"] for item in sample["fields"]})
        self.assertFalse(
            any(item["name"] == "SLATE_BEGIN_ARGS" for item in model["macros"])
        )

    def test_enum_metadata_is_parsed_with_its_enumerator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Sample.h"
            source.write_text(
                """
UENUM()
enum class ESample : uint8
{
    Visible = 1,
    Hidden UMETA(Hidden),
};
""",
                encoding="utf-8",
            )
            model = load_cpp_unit(source, [source], root)

        enum = next(item for item in model["types"] if item["name"] == "ESample")
        hidden = next(item for item in enum["enumerators"] if item["name"] == "Hidden")
        self.assertEqual(model["diagnostics"], [])
        self.assertEqual(hidden["value"], None)
        self.assertEqual(hidden["macros"], ["UMETA(Hidden)"])

    def test_type_members_inside_preprocessor_blocks_keep_their_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Sample.h"
            source.write_text(
                """
UCLASS()
class ASample
{
    GENERATED_BODY()

#if WITH_EDITORONLY_DATA
    UPROPERTY()
    int32 EditorValue;
#endif

#if WITH_EDITOR
    UFUNCTION()
    void Edit();
#endif
};
""",
                encoding="utf-8",
            )
            model = load_cpp_unit(source, [source], root)

        sample = next(item for item in model["types"] if item["name"] == "ASample")
        editor_value = next(
            item for item in sample["fields"] if item["name"] == "EditorValue"
        )
        edit = next(item for item in sample["methods"] if item["name"] == "Edit")
        self.assertEqual(editor_value["macros"], ["UPROPERTY()"])
        self.assertEqual(edit["macros"], ["UFUNCTION()"])
        self.assertEqual(
            1,
            sum(
                item["qualified_name"] == "ASample::Edit"
                for item in model["functions"]
            ),
        )

    def test_ue_declaration_and_statement_modifiers_parse(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Sample.cpp"
            source.write_text(
                """
SAMPLE_API DECLARE_LOG_CATEGORY_EXTERN(LogSample, Log, All);

FAutoConsoleCommand SampleCommand(
    TEXT("Sample.Command"),
    TEXT("Usage: ") TEXT("Sample.Command"),
    SampleDelegate);

FORCEINLINE void Send()
{
    PRAGMA_DISABLE_DEPRECATION_WARNINGS
    SendValues(FirstValue, OUT ResultValue, LastValue);
    PRAGMA_ENABLE_DEPRECATION_WARNINGS
    ENSURE_READY_OR_RETURN(Send, );
}
""",
                encoding="utf-8",
            )
            model = load_cpp_unit(source, [source], root)

        self.assertEqual(model["diagnostics"], [])
        self.assertIn("Send", {item["name"] for item in model["functions"]})
        self.assertIn(
            "DECLARE_LOG_CATEGORY_EXTERN",
            {item["name"] for item in model["macros"]},
        )

    def test_pointer_to_member_invocation_parses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Sample.cpp"
            source.write_text(
                """
void Invoke(FObject* Object, void(FObject::* Function)())
{
    (Object->*Function)();
}
""",
                encoding="utf-8",
            )
            model = load_cpp_unit(source, [source], root)

        self.assertEqual(model["diagnostics"], [])
        self.assertIn("Invoke", {item["name"] for item in model["functions"]})

    def test_pragma_between_if_condition_and_body_parses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Sample.cpp"
            source.write_text(
                """
#if WITH_EDITOR
void Validate()
{
    if (Condition)
    PRAGMA_ENABLE_DEPRECATION_WARNINGS
    {
        ReportError();
    }
}
#endif
""",
                encoding="utf-8",
            )
            model = load_cpp_unit(source, [source], root)

        self.assertEqual(model["diagnostics"], [])
        self.assertIn("Validate", {item["name"] for item in model["functions"]})

    def test_preprocessor_block_may_end_with_dangling_else(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Sample.cpp"
            source.write_text(
                """
void Run()
{
#if WITH_FEATURE
    if (Condition)
    {
        UseFeature();
    }
    else
#endif
    {
        UseFallback();
    }
}
""",
                encoding="utf-8",
            )
            model = load_cpp_unit(source, [source], root)

        self.assertEqual(model["diagnostics"], [])
        self.assertIn("Run", {item["name"] for item in model["functions"]})

    def test_gameplay_tag_macros_create_variables_without_leaking_adjacency(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            header = root / "SampleTags.h"
            source = root / "SampleTags.cpp"
            header.write_text(
                """
namespace SampleTags
{
    SAMPLE_API UE_DECLARE_GAMEPLAY_TAG_EXTERN(SharedTag);
    UE_DECLARE_GAMEPLAY_TAG_EXTERN(HeaderOnlyTag);
}
""",
                encoding="utf-8",
            )
            source.write_text(
                """
namespace SampleTags
{
    UE_DEFINE_GAMEPLAY_TAG(SharedTag, "Sample.Shared");
    UE_DEFINE_GAMEPLAY_TAG_COMMENT(CommentedTag, "Sample.Commented", "Comment");
    UE_DEFINE_GAMEPLAY_TAG_STATIC(LocalTag, "Sample.Local");

    int32 OrdinaryGlobal = 0;
    void TouchTags() {}
}
""",
                encoding="utf-8",
            )
            model = load_cpp_unit(source, [source, header], root)

        variables = {
            (item["qualified_name"], item["role"]): item
            for item in model["variables"]
        }
        declaration = variables[("SampleTags::SharedTag", "declaration")]
        self.assertEqual(declaration["type_expression"], "FNativeGameplayTag")
        self.assertEqual(declaration["linkage"], "external")
        self.assertIn(
            ("SampleTags::HeaderOnlyTag", "declaration"), variables
        )

        shared = variables[("SampleTags::SharedTag", "definition")]
        commented = variables[("SampleTags::CommentedTag", "definition")]
        local = variables[("SampleTags::LocalTag", "definition")]
        self.assertEqual(shared["linkage"], "external")
        self.assertEqual(commented["linkage"], "external")
        self.assertEqual(local["linkage"], "internal")
        self.assertEqual(local["type_expression"], "FNativeGameplayTag")

        ordinary = variables[("SampleTags::OrdinaryGlobal", "definition")]
        self.assertEqual(ordinary["macros"], [])
        touch = next(
            item
            for item in model["functions"]
            if item["qualified_name"] == "SampleTags::TouchTags"
        )
        self.assertEqual(touch["macros"], [])

    def test_dependency_graph_consumes_structured_nested_type_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Source" / "Sample" / "Types.h"
            source.parent.mkdir(parents=True)
            source.write_text(
                """
class FBase {};
class FDependency {};
class FOwner : public FBase
{
    TArray<TObjectPtr<FDependency>> Values;
};
""",
                encoding="utf-8",
            )
            graph, _, problems = build_project_graph(root)

        self.assertEqual(problems, [])
        edges = {
            (edge.source, edge.target, edge.kind, edge.member) for edge in graph.edges
        }
        self.assertIn(("FOwner", "FBase", "inheritance", ""), edges)
        self.assertIn(("FOwner", "FDependency", "field", "Values"), edges)

    def test_dependency_graph_reports_cpp_syntax_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Source" / "Sample" / "Broken.h"
            source.parent.mkdir(parents=True)
            source.write_text(
                """
class FBroken
{
    int = ;
};
""",
                encoding="utf-8",
            )

            model = load_cpp_unit(source, [source], root)
            _, _, problems = build_project_graph(root)

        self.assertGreater(model["diagnostic_error_count"], 0)
        self.assertTrue(
            any(
                problem["code"] == "project-tree-sitter-cpp-syntax-warning"
                for problem in problems
            )
        )

    def test_cpp_diagnostics_include_anonymous_missing_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "MissingSemicolon.cpp"
            source.write_text(
                """
void Run()
{
    Call()
}
""",
                encoding="utf-8",
            )

            model = load_cpp_unit(source, [source], root)

        self.assertGreater(model["diagnostic_error_count"], 0)
        self.assertTrue(
            any("missing syntax ';'" in item["message"] for item in model["diagnostics"])
        )

    def test_preprocessor_directive_may_end_at_eof(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "MissingNewline.cpp"
            source.write_bytes(b"#undef SAMPLE_MACRO")

            model = load_cpp_unit(source, [source], root)
            tree = Parser(Language(tree_sitter_ue_cpp.language())).parse(
                source.read_bytes()
            )

        self.assertEqual(model["diagnostics"], [])
        self.assertFalse(tree.root_node.has_error)

    def test_ue_runtime_statement_macros_may_own_their_semicolon(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "RuntimeMacros.cpp"
            source.write_text(
                """
void Register()
{
    check(Value)
    checkf(Value, TEXT("Expected value"))
    DOREPLIFETIME(ThisClass, Value)
    DOREPLIFETIME_WITH_PARAMS_FAST(ThisClass, OtherValue, Params)
}
""",
                encoding="utf-8",
            )

            model = load_cpp_unit(source, [source], root)

        self.assertEqual(model["diagnostics"], [])

    def test_ue_test_declaration_macros_do_not_require_semicolons(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "AutomationTests.cpp"
            source.write_text(
                """
ACTOR_ANIMATION_TEST(FAnimationTest, "Project.Animation")
{
    FAnimationTest() {}
};

TEST_CLASS_WITH_FLAGS(FMapTest, "Project.Map", EFlags::Editor | EFlags::Product)
{
};

BEGIN_DEFINE_SPEC(FMenuSpec, "Project.Menu", EFlags::Client)
    void ClickButton() const;
END_DEFINE_SPEC(FMenuSpec)
""",
                encoding="utf-8",
            )

            model = load_cpp_unit(source, [source], root)

        self.assertEqual(model["diagnostics"], [])

    def test_slate_declaration_macros_are_complete_class_items(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "SlateDeclarations.h"
            source.write_text(
                """
class FSlot
{
    SLATE_SLOT_BEGIN_ARGS(FSlot, TSlotBase<FSlot>)
    SLATE_SLOT_END_ARGS()
};

class SWidget
{
    SLATE_ARGUMENT(const FSlateBrush*, Brush)
    SLATE_ATTRIBUTE(float, Opacity)
    SLATE_STYLE_ARGUMENT(FTextBlockStyle, TextStyle)
    SLATE_SLOT_ARGUMENT(FSlot, Slots)
    SLATE_END_ARGS()

    void Construct();
};
""",
                encoding="utf-8",
            )

            model = load_cpp_unit(source, [source], root)

        self.assertEqual(model["diagnostics"], [])
        widget = next(item for item in model["types"] if item["name"] == "SWidget")
        self.assertIn("Construct", {item["name"] for item in widget["methods"]})

    def test_slate_begin_args_has_a_dedicated_syntax_node(self) -> None:
        source = b"""class SWidget
{
    SLATE_BEGIN_ARGS(SWidget)
        : _Opacity(1.0f)
    {
        _Enabled = true;
    }
    SLATE_ATTRIBUTE(float, Opacity)
    SLATE_END_ARGS()
};
"""
        tree = Parser(Language(tree_sitter_ue_cpp.language())).parse(source)
        stack = [tree.root_node]
        nodes = []
        while stack:
            node = stack.pop()
            nodes.append(node)
            stack.extend(reversed(node.named_children))

        self.assertFalse(tree.root_node.has_error)
        declarations = [
            node for node in nodes if node.type == "ue_slate_arguments_declaration"
        ]
        self.assertEqual(len(declarations), 1)
        self.assertIsNotNone(declarations[0].child_by_field_name("body"))
        self.assertFalse(
            any(
                node.type == "function_definition"
                and source[node.start_byte : node.end_byte].lstrip().startswith(
                    b"SLATE_BEGIN_ARGS"
                )
                for node in nodes
            )
        )

    def test_ue_test_macros_own_their_generated_declaration_bodies(self) -> None:
        source = b"""#if WITH_AUTOMATION_TESTS
ACTOR_ANIMATION_TEST(FGeneratedTest, "Project.Generated")
{
    FGeneratedTest() {}
    void Run() {}
};

BEGIN_DEFINE_SPEC(FGeneratedSpec, "Project.Spec", EFlags::Client)
    int32 Value;
    void Helper() const;
END_DEFINE_SPEC(FGeneratedSpec)
#endif
"""
        tree = Parser(Language(tree_sitter_ue_cpp.language())).parse(source)
        stack = [tree.root_node]
        nodes = []
        while stack:
            node = stack.pop()
            nodes.append(node)
            stack.extend(reversed(node.named_children))

        self.assertFalse(tree.root_node.has_error)
        classes = [
            node for node in nodes if node.type == "ue_test_class_declaration"
        ]
        specs = [node for node in nodes if node.type == "ue_test_spec_declaration"]
        self.assertEqual(len(classes), 1)
        self.assertEqual(len(specs), 1)
        self.assertEqual(
            classes[0].child_by_field_name("body").type,
            "field_declaration_list",
        )
        self.assertEqual(
            len(
                [
                    child
                    for child in specs[0].children_by_field_name("member")
                    if child.type == "field_declaration"
                ]
            ),
            2,
        )

    def test_conditional_compilation_else_stays_attached_to_if(self) -> None:
        source = b"""void Run()
{
#if FEATURE_ENABLED
    if (Enabled)
    {
        UsePrimary();
    }
    else
#endif
    {
        UseFallback();
    }
}
"""
        tree = Parser(Language(tree_sitter_ue_cpp.language())).parse(source)

        self.assertFalse(tree.root_node.has_error)
        stack = [tree.root_node]
        if_nodes = []
        while stack:
            node = stack.pop()
            if node.type == "if_statement":
                if_nodes.append(node)
            stack.extend(reversed(node.named_children))

        self.assertEqual(len(if_nodes), 1)
        self.assertIsNotNone(if_nodes[0].child_by_field_name("alternative"))


if __name__ == "__main__":
    unittest.main()
