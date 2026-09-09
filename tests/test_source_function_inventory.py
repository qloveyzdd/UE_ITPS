from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests.support import create_fixture, run_cli, write_text


class SourceFunctionInventoryTests(unittest.TestCase):
    def test_definitions_are_navigable_without_visible_owner_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            write_text(fixture.source, """
                void Invisible::Run() {}
                void Invisible::Run(int) {}
                void Prototype();
                namespace N { void Free() {} }
                void Outer() { struct Local { void Run() {} }; }
            """)
            completed, result = run_cli("sourcetools/ue_list_cxx_functions.py", "--source", fixture.source)
            self.assertEqual(completed.returncode, 0, result)
            functions = result["functions"]
            self.assertEqual(len(functions), 5)
            self.assertEqual(len({f["function_id"] for f in functions}), 5)
            self.assertEqual([f["qualified_name"] for f in functions].count("Invisible::Run"), 2)
            for name in {f["qualified_name"] for f in functions}:
                _, details = run_cli("sourcetools/ue_inspect_cxx_function.py", "--source",
                                     fixture.source, "--function", name)
                self.assertEqual({f["function_id"] for f in functions if f["qualified_name"] == name},
                                 {f["function_id"] for f in details["matches"]})

    def test_injected_class_name_needs_local_evidence_and_keeps_original_selector(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            write_text(fixture.header, "struct A { static void Get(); }; namespace N { namespace N { void Free(); } }")
            write_text(fixture.source, "void A::A::Get() {}\nvoid Missing::Missing::Get() {}\nnamespace N { namespace N { void Free() {} } }")
            sources = (fixture.source, fixture.header)
            _, result = run_cli("sourcetools/ue_list_cxx_functions.py", "--source", *sources)
            functions = {f["source_qualified_name"]: f for f in result["functions"]}
            self.assertEqual(functions["A::A::Get"]["qualified_name"], "A::Get")
            self.assertIn("A::A::Get", functions["A::A::Get"]["signature"])
            self.assertEqual(functions["Missing::Missing::Get"]["qualified_name"], "Missing::Missing::Get")
            self.assertEqual(functions["N::N::Free"]["qualified_name"], "N::N::Free")
            for selector in ("A::Get", "A::A::Get"):
                completed, details = run_cli("sourcetools/ue_inspect_cxx_function.py", "--source",
                                             *sources, "--function", selector)
                self.assertEqual(completed.returncode, 0, details)
                self.assertEqual(details["matches"][0]["function_id"], functions["A::A::Get"]["function_id"])
            _, typed = run_cli("sourcetools/ue_inspect_cxx_type.py", "--source", *sources, "--type", "A")
            self.assertEqual(len(typed["matches"][0]["member_functions"]), 1)

    def test_empty_file_and_invalid_input_use_the_public_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            write_text(fixture.source, "void Prototype();")
            completed, result = run_cli("sourcetools/ue_list_cxx_functions.py", "--source", fixture.source)
            self.assertEqual(completed.returncode, 0, result)
            self.assertEqual(result["functions"], [])
            completed, result = run_cli("sourcetools/ue_list_cxx_functions.py", "--source", fixture.root / "Missing.cpp")
            self.assertEqual(completed.returncode, 2, result)

