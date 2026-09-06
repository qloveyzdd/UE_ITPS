from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests.support import create_fixture, run_cli, write_text


class SourceTypeSemanticsTests(unittest.TestCase):
    def test_static_member_definitions_keep_identity_and_reference_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(fixture.header, """
                namespace Game {
                    struct A { static int Count; int Read(); };
                    struct B { static int Count; int Read(); };
                }
            """)
            source = write_text(fixture.source, """
                int Count = 0;
                namespace Game {
                    int A::Count = 1;
                    int Game::B::Count = 2;
                    int A::Read() { return Count + B::Count + ::Count; }
                    int B::Read() { return Count; }
                }
            """)
            completed, result = run_cli(
                "sourcetools/ue_list_cxx_types.py", "--source", source, header,
            )
            self.assertEqual(completed.returncode, 0)
            variables = result["global_variables"]
            self.assertEqual(
                [(item["qualified_name"], item["namespace"]) for item in variables],
                [("Count", None), ("Game::A::Count", "Game"), ("Game::B::Count", "Game")],
            )
            for selector, expected in [
                ("Game::A::Read", {"Game::A::Count", "Game::B::Count", "Count"}),
                ("Game::B::Read", {"Game::B::Count"}),
            ]:
                with self.subTest(selector=selector):
                    completed, result = run_cli(
                        "sourcetools/ue_inspect_cxx_function.py", "--source", source, header,
                        "--function", selector,
                    )
                    self.assertEqual(completed.returncode, 0)
                    self.assertEqual(
                        {item["spelling"] for item in result["matches"][0]["external_symbols"]
                         if item["kind"] == "global_variable"}, expected,
                    )

    def test_member_anchors_cover_inline_template_and_conditional_members(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(fixture.header, """
                class AWorker {
                    AWorker();
                    ~AWorker() {}
                    UFUNCTION() int GetCount() const { return 1; }
                    template<class T> void Bind(T Value);
                    template<class T> void Send(T Value) {}
                #if WITH_EDITOR
                    void Edit() {}
                #endif
                    struct FNested { void Inner() {} };
                };
            """)
            completed, result = run_cli(
                "sourcetools/ue_list_cxx_types.py", "--source", header,
            )
            self.assertEqual(completed.returncode, 0)
            worker = result["classes"][0]
            anchors = worker["member_anchors"]
            self.assertEqual([item["name"] for item in anchors],
                             ["AWorker", "~AWorker", "GetCount", "Bind", "Send", "Edit"])
            self.assertEqual(next(item for item in anchors if item["name"] == "GetCount")["macros"],
                             ["UFUNCTION()"])
            self.assertEqual([item["name"] for item in result["structs"][0]["member_anchors"]],
                             ["Inner"])
            definitions = result["member_functions"]
            self.assertEqual(len(definitions), 5)
            self.assertNotIn("Bind", {item["name"] for item in definitions})


if __name__ == "__main__":
    unittest.main()
