from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
