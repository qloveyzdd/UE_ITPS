from __future__ import annotations

import json

from tests.support import CliTestCase, REPOSITORY_ROOT, SCHEMAS_ROOT, TOOLS_ROOT
from ue_project_tools.dependency_graph import DependencyGraph
from ue_project_tools.syntax_tree import parse_csharp_syntax


class ToolPoolEnrichmentTests(CliTestCase):
    def test_code_analysis_frontends_have_no_custom_lexer_or_cpp_tree_sitter(self) -> None:
        package = TOOLS_ROOT / "ue_project_tools"
        self.assertFalse((package / "source_tokens.py").exists())
        forbidden = (
            "lex_source",
            "source_tokens",
            "tree_sitter_cpp",
            "parse_cpp_syntax",
        )
        for path in sorted(package.glob("*.py")):
            source = path.read_text(encoding="utf-8-sig")
            with self.subTest(path=path.name):
                for marker in forbidden:
                    self.assertNotIn(marker, source)
        requirements = (REPOSITORY_ROOT / "requirements.txt").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("tree-sitter-cpp", requirements)

    def test_csharp_ast_covers_generics_lambda_and_calls(self) -> None:
        parsed = parse_csharp_syntax(
            """
            public class Rules<T> : ModuleRules
            {
                public void Configure()
                {
                    System.Func<int, int> map = value => value + 1;
                    PublicDependencyModuleNames.Add(map(1).ToString());
                }
            }
            """
        )
        self.assertEqual(parsed["parse_error_count"], 0)
        self.assertEqual(parsed["types"][0]["name"], "Rules")
        calls = [item["callee"] for item in parsed["functions"][0]["calls"]]
        self.assertIn("PublicDependencyModuleNames.Add", calls)

    def test_dependency_graph_deduplicates_cycles_and_traces_impact(self) -> None:
        graph = DependencyGraph()
        for name in ("A", "B", "C"):
            graph.add_node(name, kind="class", file=f"{name}.h")
        graph.add_edge("A", "B", kind="field")
        graph.add_edge("B", "C", kind="field")
        graph.add_edge("C", "A", kind="field")
        self.assertEqual(graph.cycles(), [["A", "B", "C", "A"]])
        self.assertEqual(
            [(item["name"], item["depth"]) for item in graph.impact("A", 3)],
            [("C", 1), ("B", 2)],
        )

    def test_existing_module_and_plugin_probes_expose_dependency_graphs(self) -> None:
        modules = self.cli(
            "ue_inspect_modules.py", "--project", str(self.fixture.project)
        )
        edges = modules["dependency_graph"]["edges"]
        self.assertTrue(
            any(
                edge["source"] == "SampleGame" and edge["target"] == "Core"
                for edge in edges
            )
        )

        plugins = self.cli(
            "ue_resolve_plugins.py", "--project", str(self.fixture.project)
        )
        self.assertTrue(
            any(
                edge["source"] == "SamplePlugin"
                and edge["target"] == "GameplayAbilities"
                for edge in plugins["dependency_graph"]["edges"]
            )
        )

    def test_new_graph_probes_and_tool_pool_are_deterministic(self) -> None:
        pool = self.cli("ue_list_tools.py")
        self.assertEqual(pool["tool_count"], 22)
        self.assertEqual(pool["schema_version"], "ue_list_tools")

        hierarchy = self.cli(
            "ue_query_cxx_hierarchy.py",
            "--project",
            str(self.fixture.project),
            "--class",
            "ASampleActor",
        )
        self.assertEqual(hierarchy["match"]["base_types"], ["AActor"])

        flow = self.cli(
            "ue_trace_cxx_function_flow.py",
            "--source",
            str(self.fixture.source_cpp),
            "--function",
            "BeginPlay",
        )
        self.assertEqual(flow["match_count"], 1)
        self.assertTrue(flow["matches"][0]["calls"])

    def test_schema_identifiers_and_output_constants_have_no_versions(self) -> None:
        for path in sorted(SCHEMAS_ROOT.glob("*.schema.json")):
            with self.subTest(schema=path.name):
                document = json.loads(path.read_text(encoding="utf-8"))
                self.assertNotRegex(document["$id"], r":v\d+$")
                if path.name == "common.schema.json":
                    continue
                expected = path.name.removesuffix(".schema.json")
                success = document["$defs"]["success"]
                self.assertEqual(
                    success["properties"]["schema_version"]["const"], expected
                )
