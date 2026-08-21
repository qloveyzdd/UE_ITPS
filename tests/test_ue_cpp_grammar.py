from __future__ import annotations

import unittest

from tree_sitter import Language, Node, Parser
import tree_sitter_ue_cpp

from tests.support import REPOSITORY_ROOT


def walk(node: Node):
    yield node
    for child in node.children:
        yield from walk(child)


class UECppGrammarTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = Parser(Language(tree_sitter_ue_cpp.language()))

    def parse_nodes(self, source: str) -> list[Node]:
        tree = self.parser.parse(source.encode("utf-8"))
        return list(walk(tree.root_node))

    def assert_no_syntax_errors(self, nodes: list[Node]) -> None:
        errors = [node for node in nodes if node.type == "ERROR" or node.is_missing]
        self.assertEqual(errors, [])

    def test_reflection_api_and_member_macros_are_grammar_nodes(self) -> None:
        nodes = self.parse_nodes(
            """
            UCLASS(BlueprintType, meta=(DisplayName="Example"))
            class SAMPLEGAME_API ASampleActor
            {
                GENERATED_BODY()

                UPROPERTY(EditAnywhere)
                int32 Count;

                UFUNCTION(BlueprintCallable)
                void Run();
            };
            """
        )

        self.assert_no_syntax_errors(nodes)
        self.assertEqual(
            sum(node.type == "ue_macro_invocation" for node in nodes),
            4,
        )
        self.assertEqual(sum(node.type == "ue_api_macro" for node in nodes), 1)

    def test_mixed_case_declaration_macro_keeps_following_field(self) -> None:
        nodes = self.parse_nodes(
            """
            class FOwner
            {
                DECLARE_EVENT_OneParam(FOwner, FChangedEvent, int32 Value)
                FChangedEvent OnChanged;
            };
            """
        )

        self.assert_no_syntax_errors(nodes)
        self.assertEqual(
            sum(node.type == "ue_macro_invocation" for node in nodes),
            1,
        )
        self.assertEqual(sum(node.type == "field_declaration" for node in nodes), 1)

    def test_expression_macros_remain_standard_call_expressions(self) -> None:
        nodes = self.parse_nodes(
            """
            void Run()
            {
                auto Label = TEXT("Label");
                auto Description = LOCTEXT("Key", "Description");
                UE_LOG(LogTemp, Warning, TEXT("Message"));
            }
            """
        )

        self.assert_no_syntax_errors(nodes)
        self.assertEqual(
            sum(node.type == "ue_macro_invocation" for node in nodes),
            0,
        )
        self.assertGreaterEqual(
            sum(node.type == "call_expression" for node in nodes),
            4,
        )

    def test_constructors_are_not_reclassified_as_macros(self) -> None:
        nodes = self.parse_nodes(
            "class FOwner { FOwner(); ~FOwner(); void Run(); };"
        )

        self.assert_no_syntax_errors(nodes)
        self.assertEqual(
            sum(node.type == "ue_macro_invocation" for node in nodes),
            0,
        )

    def test_generated_includes_have_dedicated_grammar_nodes(self) -> None:
        nodes = self.parse_nodes(
            """
            #include "SampleActor.generated.h"
            #include UE_INLINE_GENERATED_CPP_BY_NAME(SampleActor)
            #include "SampleActor.h"
            """
        )

        self.assert_no_syntax_errors(nodes)
        node_types = [node.type for node in nodes]
        self.assertEqual(node_types.count("ue_generated_header_path"), 1)
        self.assertEqual(node_types.count("ue_inline_generated_cpp_path"), 1)
        self.assertEqual(node_types.count("preproc_include"), 3)

    @unittest.skipUnless(
        (
            REPOSITORY_ROOT
            / "LyraStarterGame"
            / "Source"
            / "LyraEditor"
            / "LyraEditor.cpp"
        ).is_file(),
        "External Lyra fixture is not available",
    )
    def test_lyra_editor_source_parses_without_recovery_nodes(self) -> None:
        source = (
            REPOSITORY_ROOT
            / "LyraStarterGame"
            / "Source"
            / "LyraEditor"
            / "LyraEditor.cpp"
        ).read_bytes()
        nodes = list(walk(self.parser.parse(source).root_node))

        self.assert_no_syntax_errors(nodes)
