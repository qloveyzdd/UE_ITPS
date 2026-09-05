from __future__ import annotations

from pathlib import Path
import sys
import unittest

from tree_sitter import Language, Parser
import tree_sitter_ue_cpp

from tests.support import ROOT

sys.path.insert(0, str(ROOT / "sourcetools"))

from ue_project_tools.cpp_frontend import load_cpp_unit


class LyraTreeSitterBaselineTests(unittest.TestCase):
    def test_full_lyra_source_tree_matches_baseline(self) -> None:
        project_root = ROOT / "LyraStarterGame"
        files = sorted(
            path
            for path in (*project_root.rglob("*.h"), *project_root.rglob("*.cpp"))
            if "Source" in path.relative_to(project_root).parts
            and not {"Intermediate", "Binaries"}.intersection(
                path.relative_to(project_root).parts
            )
        )

        self.assertEqual(len(files), 707)

        parser = Parser(Language(tree_sitter_ue_cpp.language()))
        syntax_counts = {
            "ue_slate_arguments_declaration": 0,
            "ue_test_class_declaration": 0,
            "ue_test_spec_declaration": 0,
        }
        for path in files:
            tree = parser.parse(path.read_bytes())
            self.assertFalse(tree.root_node.has_error, path.as_posix())
            stack = [tree.root_node]
            while stack:
                node = stack.pop()
                if node.type in syntax_counts:
                    syntax_counts[node.type] += 1
                stack.extend(reversed(node.named_children))

        self.assertEqual(syntax_counts["ue_slate_arguments_declaration"], 8)
        self.assertEqual(syntax_counts["ue_test_class_declaration"], 4)
        self.assertEqual(syntax_counts["ue_test_spec_declaration"], 1)

        model = load_cpp_unit(files[0], files, project_root)

        self.assertEqual(model["diagnostic_error_count"], 0)
        self.assertEqual(len(model["types"]), 2010)
        self.assertEqual(len(model["functions"]), 6047)
        self.assertEqual(len(model["variables"]), 302)
        self.assertEqual(len(model["includes"]), 3254)
        self.assertEqual(len(model["macros"]), 3016)

        definitions = [item for item in model["types"] if item["role"] == "definition"]
        self.assertEqual(sum(len(item.get("fields", [])) for item in definitions), 1842)
        self.assertEqual(sum(len(item.get("methods", [])) for item in definitions), 2452)
        self.assertEqual(
            sum(len(item.get("enumerators", [])) for item in definitions), 234
        )
        self.assertEqual(
            sum(
                any(
                    str(macro).startswith("UPROPERTY(")
                    for macro in field.get("macros", [])
                )
                for item in definitions
                for field in item.get("fields", [])
            ),
            1130,
        )


if __name__ == "__main__":
    unittest.main()
