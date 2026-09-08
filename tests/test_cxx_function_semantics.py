from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests.support import create_fixture, run_cli, write_text


class CxxFunctionSemanticsTests(unittest.TestCase):

    def test_named_casts_preserve_operand_calls_and_target_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            write_text(fixture.source, """
                void Run() {
                    Consume(const_cast<FTarget*>(Acquire()));
                    Consume(static_cast<FBase*>(Acquire()));
                    Consume(reinterpret_cast<FBuffer*>(Acquire()));
                    Consume(dynamic_cast<FDerived*>(Acquire()));
                    Consume(static_cast<FBase*>(const_cast<FTarget*>(Acquire())));
                    Cast<FTarget>(Acquire());
                }
            """)
            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py", "--source", fixture.source,
                "--function", "Run", "--include-syntax-flow",
            )
            self.assertEqual(completed.returncode, 0, result)
            match = result["matches"][0]
            calls = [c["callee"] for c in match["syntax_flow"]["calls"]]
            self.assertEqual(calls, ["Consume", "Acquire"] * 5 + ["Cast<FTarget>", "Acquire"])
            symbols = {(s["kind"], s["spelling"]) for s in match["external_symbols"]}
            self.assertTrue({("type", name) for name in
                             ("FTarget*", "FBase*", "FBuffer*", "FDerived*", "FTarget")} <= symbols)
            self.assertIn(("unknown", "Cast<FTarget>()"), symbols)
            self.assertFalse(any("_cast<" in spelling for _, spelling in symbols))

    def test_address_targets_require_function_evidence_and_respect_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            write_text(fixture.header, """
                namespace Game {
                    void Ready();
                    void Overload();
                    void Overload(int);
                    int Value;
                    struct FWorker {
                        void Run(int Parameter);
                        void Finished();
                        int Field;
                        int Children[2];
                    };
                }
            """)
            source = write_text(fixture.source, """
                void Game::FWorker::Run(int Parameter) {
                    int Local = 0;
                    Sink(&Local, &Parameter, &Field, &FWorker::Field, &Game::Value);
                    Sink(&Children[0], &External::Missing);
                    Sink(&Ready, &FWorker::Finished, &Game::Overload);
                    Sink(
                        &(FWorker::Finished));
                    { int Ready = 0; Sink(&Ready); }
                    Sink(&Ready);
                    auto Lambda = [](int Ready) { Sink(&Ready); };
                    auto Callback = &FWorker::Finished;
                    for (auto& Ready : Children) { Sink(&Ready); }
                    Sink(&Ready);
                }
            """)
            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py", "--source", source, fixture.header,
                "--function", "Game::FWorker::Run",
            )
            self.assertEqual(completed.returncode, 0, result)
            symbols = result["matches"][0]["external_symbols"]
            addresses = [s for s in symbols if s["kind"] == "function_address"]
            self.assertEqual([s["spelling"] for s in addresses],
                             ["Ready", "FWorker::Finished", "Game::Overload",
                              "FWorker::Finished", "Ready", "FWorker::Finished", "Ready"])
            self.assertEqual([s["evidence"]["line"] for s in addresses], [5, 5, 5, 7, 9, 11, 13])
            self.assertIn(("unknown", "&External::Missing"),
                          {(s["kind"], s["spelling"]) for s in symbols})
            self.assertFalse(any(s["kind"] == "unknown" and s["spelling"] in
                                 {"&Local", "&Parameter", "&Field", "&FWorker::Field", "&Game::Value"}
                                 for s in symbols))

    def test_inline_friends_are_namespace_functions_not_members(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            write_text(fixture.header, """
                namespace Game {
                    struct First {
                        friend uint32 GetTypeHash(const First& Value) { return FirstHash(Value); }
                    };
                    struct Second {
                        friend FORCEINLINE uint32 GetTypeHash(Second Value) { return SecondHash(Value); }
                    };
                }
            """)
            completed, result = run_cli("sourcetools/ue_inspect_cxx_function.py", "--source",
                                        fixture.header, "--function", "Game::GetTypeHash",
                                        "--include-syntax-flow")
            self.assertEqual(completed.returncode, 0, result)
            self.assertEqual(result["match_count"], 2)
            self.assertEqual({m["syntax_flow"]["calls"][0]["callee"] for m in result["matches"]},
                             {"FirstHash", "SecondHash"})
            _, inventory = run_cli("sourcetools/ue_list_cxx_types.py", "--source", fixture.header)
            self.assertEqual([f["qualified_name"] for f in inventory["free_functions"]],
                             ["Game::GetTypeHash", "Game::GetTypeHash"])
            _, details = run_cli("sourcetools/ue_inspect_cxx_type.py", "--source",
                                 fixture.header, "--type", "Game::First")
            self.assertEqual(details["matches"][0]["member_functions"], [])
            self.assertEqual(details["matches"][0]["member_anchors"], [])

    def test_local_type_bodies_are_separate_from_enclosing_function_and_lambda(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            write_text(fixture.source, """
                namespace Game {
                    DECLARE_DELEGATE(FDone);
                    void Outer() {
                        struct Local {
                            FDone Done;
                            void Run() { InnerOnly(); Done.Execute(); }
                        };
                        OuterOnly();
                        auto Work = [] {
                            struct InLambda { void Run(FDone Done) { LambdaMemberOnly(); Done.Execute(); } };
                            LambdaOnly();
                        };
                    }
                    void Other() {
                        struct Local { void Run() { OtherInnerOnly(); } };
                    }
                }
            """)
            for selector, calls, operations in (
                ("Game::Outer", {"OuterOnly", "LambdaOnly"}, []),
                ("Game::Outer::Local::Run", {"InnerOnly", "Done.Execute"}, ["execute"]),
                ("Game::Outer::InLambda::Run", {"LambdaMemberOnly", "Done.Execute"}, ["execute"]),
                ("Game::Other::Local::Run", {"OtherInnerOnly"}, []),
            ):
                with self.subTest(selector=selector):
                    completed, result = run_cli("sourcetools/ue_inspect_cxx_function.py", "--source",
                                                fixture.source, "--function", selector, "--include-syntax-flow")
                    self.assertEqual(completed.returncode, 0, result)
                    match = result["matches"][0]
                    self.assertEqual({c["callee"] for c in match["syntax_flow"]["calls"]}, calls)
                    self.assertEqual([o["operation"] for o in match["delegate_operations"]], operations)
                    for operation in match["delegate_operations"]:
                        self.assertEqual(operation["resolution"]["status"], "identified")
                        self.assertEqual(operation["execution_scope"], {"kind": "function"})
            _, inventory = run_cli("sourcetools/ue_list_cxx_types.py", "--source", fixture.source)
            self.assertEqual({t["qualified_name"] for t in inventory["structs"]},
                             {"Game::Outer::Local", "Game::Outer::InLambda", "Game::Other::Local"})
            self.assertEqual(inventory["global_variables"], [])

    def test_ue_test_containers_expose_named_methods_and_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            write_text(fixture.source, """
                TEST_CLASS_WITH_FLAGS(FCheck, "Tests", Flags) {
                    FCheck() { Construct(); }
                    void Helper() { Help(); }
                    BEFORE_EACH() { Prepare(); }
                    TEST_METHOD(First) { CheckFirst(); }
                    TEST_METHOD(Second) { CheckSecond(); }
                    AFTER_EACH() { Cleanup(); }
                };
                BEGIN_DEFINE_SPEC(FSpec, "Tests.Spec", Flags)
                    int Value;
                    void Helper() { SpecHelp(); }
                END_DEFINE_SPEC(FSpec)
            """)
            for name, call in (("FCheck::FCheck", "Construct"), ("FCheck::Helper", "Help"),
                               ("FCheck::Setup", "Prepare"), ("FCheck::First", "CheckFirst"),
                               ("FCheck::Second", "CheckSecond"), ("FCheck::TearDown", "Cleanup"),
                               ("FSpec::Helper", "SpecHelp")):
                with self.subTest(name=name):
                    completed, result = run_cli("sourcetools/ue_inspect_cxx_function.py", "--source",
                                                fixture.source, "--function", name, "--include-syntax-flow")
                    self.assertEqual(completed.returncode, 0, result)
                    self.assertEqual(result["match_count"], 1)
                    self.assertEqual(result["matches"][0]["syntax_flow"]["calls"][0]["callee"], call)
            _, inventory = run_cli("sourcetools/ue_list_cxx_types.py", "--source", fixture.source)
            self.assertEqual([t["name"] for t in inventory["structs"]], ["FCheck"])
            self.assertEqual([t["name"] for t in inventory["classes"]], ["FSpec"])
            self.assertEqual(inventory["free_functions"], [])

    def test_conditional_definitions_keep_independent_bodies_and_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            write_text(fixture.header, """
                DECLARE_DELEGATE(FDone);
                class AWorker { FDone Done; void Run(); void Ready(); };
                #if HEADER_IMPLEMENTATION
                void AWorker::Run() { HeaderOnly(); Done.IsBound(); }
                #endif
            """)
            write_text(fixture.source, """
                #if SERVER
                void AWorker::Run() { ServerOnly(); Done.BindUObject(this, &AWorker::Ready); }
                #elif CLIENT
                void AWorker::Run() { ClientOnly(); Done.Execute(); }
                #else
                void AWorker::Run() { FallbackOnly(); Done.Unbind(); }
                #endif
            """)
            arguments = ("--source", fixture.source, fixture.header,
                         "--function", "AWorker::Run", "--include-syntax-flow")
            completed, result = run_cli("sourcetools/ue_inspect_cxx_function.py", *arguments)
            self.assertEqual(completed.returncode, 0, result)
            matches = result["matches"]
            self.assertEqual(len(matches), 4)
            # Check content before identity so a signature-keyed reference map fails here.
            by_call = {m["syntax_flow"]["calls"][0]["callee"]: m for m in matches}
            self.assertEqual(set(by_call), {"HeaderOnly", "ServerOnly", "ClientOnly", "FallbackOnly"})
            for call, operation in (("HeaderOnly", "query"), ("ServerOnly", "bind"),
                                    ("ClientOnly", "execute"), ("FallbackOnly", "unbind")):
                match = by_call[call]
                self.assertIn(call + "()", [s["spelling"] for s in match["external_symbols"]])
                self.assertEqual([o["operation"] for o in match["delegate_operations"]], [operation])
                self.assertEqual(match["delegate_operations"][0]["resolution"]["status"], "identified")
            self.assertEqual(len({m["function_id"] for m in matches}), 4)
            _, repeated = run_cli("sourcetools/ue_inspect_cxx_function.py", *arguments)
            self.assertEqual(repeated["matches"], matches)

    def test_same_line_definitions_have_distinct_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            write_text(fixture.source, "void Run() { First(); } void Run() { Second(); }")
            completed, result = run_cli("sourcetools/ue_inspect_cxx_function.py", "--source",
                                        fixture.source, "--function", "Run", "--include-syntax-flow")
            self.assertEqual(completed.returncode, 0, result)
            self.assertEqual(len({m["function_id"] for m in result["matches"]}), 2)
            self.assertEqual({m["syntax_flow"]["calls"][0]["callee"] for m in result["matches"]},
                             {"First", "Second"})

    def test_call_template_types_and_same_line_source_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            source = write_text(fixture.source, """
                void AWorker::Run(FRouter* Router) {
                    Router->GetSet<FPayload>();
                    Router->Apply<TArray<FPayload>, 3, (1 + 2)>();
                    UE_LOG(LogTemp, Warning, TEXT("message"));
                }
            """)
            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py", "--source", source,
                fixture.header, "--function", "AWorker::Run",
            )
            self.assertEqual(completed.returncode, 0)
            symbols = result["matches"][0]["external_symbols"]
            self.assertEqual(
                [s["spelling"] for s in symbols if s["kind"] == "type"],
                ["FPayload", "TArray<FPayload>"],
            )
            self.assertEqual(
                [s["spelling"] for s in symbols if s["kind"] == "macro"],
                ["UE_LOG()", "TEXT()"],
            )
            self.assertTrue(all(set(s) <= {"kind", "spelling", "owner_type", "evidence"}
                                for s in symbols))

    def test_symbol_types_preserve_namespaces_and_template_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(fixture.header, """
                namespace Game {
                    class AWorker {
                        Other::FContainer Field;
                        void Run(Events::FOnReady::FDelegate&& Delegate);
                        void Helper();
                    };
                }
            """)
            source = write_text(fixture.source, """
                namespace Game {
                    void AWorker::Run(Events::FOnReady::FDelegate&& Delegate) {
                        TMap<int32, Other::TEnvelope<Other::FPayload>> Values;
                        Values.Reset();
                        Field.Reset();
                        Delegate.Execute();
                        Services::FManager::Get().Refresh();
                        Services::FManager::Refresh();
                        Helper();
                    }
                }
            """)
            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py", "--source", source, header,
                "--function", "Game::AWorker::Run",
            )
            self.assertEqual(completed.returncode, 0)
            match = result["matches"][0]
            template = "TMap<int32,Other::TEnvelope<Other::FPayload>>"
            self.assertEqual(
                {item["spelling"] for item in match["external_symbols"] if item["kind"] == "type"},
                {template},
            )
            self.assertEqual(
                {item["owner_type"] for item in match["external_symbols"] if item["kind"] == "member_call"},
                {template, "Other::FContainer", "Events::FOnReady::FDelegate",
                 "Services::FManager", "Game::AWorker"},
            )
            self.assertEqual(match["delegate_operations"][0]["subject"]["expression"], "Delegate")
            self.assertEqual(match["delegate_operations"][0]["resolution"]["status"], "candidate")
            self.assertIsNone(match["delegate_operations"][0]["subject"]["qualified_name"])

    def test_delegate_events_use_local_and_chained_receiver_owners(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            source = write_text(fixture.source, """
                void AWorker::Activate(FRouter* Parameter) {
                    FRouter* Local;
                    Local->GetEvent().AddUObject(this, &AWorker::OnFinished);
                    Parameter->GetEvent().Broadcast();
                    Local->Changed.Broadcast();
                    this->Changed.Broadcast();
                    Missing->GetEvent().Broadcast();
                    Local->GetUnknown().GetEvent().Broadcast();
                }
            """)
            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py", "--source", source,
                fixture.header, "--function", "AWorker::Activate",
            )
            self.assertEqual(completed.returncode, 0)
            operations = result["matches"][0]["delegate_operations"]
            self.assertEqual(
                [item["subject"]["qualified_name"] for item in operations],
                [None] * 6,
            )
            self.assertTrue(all(item["resolution"]["status"] == "candidate" for item in operations))

    def test_scoped_free_calls_do_not_become_member_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            source = write_text(fixture.source, """
                namespace Tools { void Run() {} void Get() {} }
                namespace Outer {
                    namespace Helpers { void Run() {} }
                    void Invoke() {
                        Tools::Run();
                        Tools::Get();
                        Helpers::Run();
                        FWorker::Run();
                    }
                }
            """)
            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py", "--source", source,
                "--function", "Outer::Invoke",
            )
            self.assertEqual(completed.returncode, 0)
            symbols = result["matches"][0]["external_symbols"]
            self.assertEqual(
                {(item["kind"], item["spelling"]) for item in symbols},
                {("free_function", "Tools::Run"), ("free_function", "Tools::Get"),
                 ("free_function", "Outer::Helpers::Run"),
                 ("member_call", "FWorker->Run()")},
            )

    def test_qualified_function_selector_avoids_same_name_collisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                class AWorker
                {
                public:
                    void Run();
                };

                struct FWorker
                {
                    void Run();
                };

                namespace Tools
                {
                    struct FWorker
                    {
                        void Run();
                    };
                }
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                void AWorker::Run() {}
                void FWorker::Run() {}
                namespace Tools
                {
                    void FWorker::Run() {}
                }
                """,
            )

            completed, simple = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "Run",
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(simple["match_count"], 3)

            completed, qualified = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "AWorker::Run",
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(qualified["match_count"], 1)
            self.assertIn("AWorker|Run", qualified["matches"][0]["function_id"])

            completed, namespaced = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "Tools::FWorker::Run",
            )
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(namespaced["match_count"], 1)
            self.assertIn(
                "Tools|FWorker|Run", namespaced["matches"][0]["function_id"]
            )

            completed, missing = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "Missing::Run",
            )
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(missing["match_count"], 0)

    def test_same_type_get_accessor_resolves_chained_member_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                class AWorker
                {
                public:
                    void ShowNotification();
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                void AWorker::ShowNotification()
                {
                    FNotificationInfo Info;
                    FSlateNotificationManager::Get().AddNotification(Info);
                    FSlateApplication::Get().GetPlatformApplication();
                    FContainer Container;
                    Container.Get().DoWork();
                }
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "ShowNotification",
            )

            self.assertEqual(completed.returncode, 0)
            symbols = result["matches"][0]["external_symbols"]
            self.assertIn("FNotificationInfo", {item["spelling"] for item in symbols})
            notification_call = next(
                item for item in symbols if item["spelling"].endswith("AddNotification()")
            )
            self.assertEqual(notification_call["kind"], "member_call")
            self.assertEqual(
                notification_call["spelling"],
                "FSlateNotificationManager->AddNotification()",
            )
            self.assertEqual(
                notification_call["owner_type"], "FSlateNotificationManager"
            )
            application_call = next(
                item
                for item in symbols
                if item["spelling"].endswith("GetPlatformApplication()")
            )
            self.assertEqual(application_call["kind"], "member_call")
            self.assertEqual(
                application_call["spelling"],
                "FSlateApplication->GetPlatformApplication()",
            )
            self.assertEqual(application_call["owner_type"], "FSlateApplication")
            object_get_call = next(
                item for item in symbols if item["spelling"].endswith("DoWork()")
            )
            self.assertEqual(object_get_call["kind"], "unknown")
            self.assertNotIn(
                "FSlateNotificationManager->Get()",
                {item["spelling"] for item in symbols},
            )
            self.assertNotIn(
                "FSlateApplication->Get()",
                {item["spelling"] for item in symbols},
            )
            self.assertEqual(result["matches"][0]["delegate_operations"], [])

    def test_external_symbol_exclusions_preserve_syntax_flow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                class AWorker
                {
                public:
                    void ConvertNames();
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                void AWorker::ConvertNames()
                {
                    FText::Format(Pattern);
                    FText::FromName(Name);
                    FOtherText::FromName(Name);
                }
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "ConvertNames",
            )

            self.assertEqual(completed.returncode, 0)
            match = result["matches"][0]
            spellings = {item["spelling"] for item in match["external_symbols"]}
            self.assertNotIn("FText->Format()", spellings)
            self.assertNotIn("FText->FromName()", spellings)
            self.assertIn("FOtherText->FromName()", spellings)
            self.assertNotIn("syntax_flow", match)

            completed, with_flow = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "ConvertNames",
                "--include-syntax-flow",
            )
            self.assertEqual(completed.returncode, 0)
            calls = {
                item["callee"]
                for item in with_flow["matches"][0]["syntax_flow"]["calls"]
            }
            self.assertIn("FText::Format", calls)
            self.assertIn("FText::FromName", calls)

    def test_known_ue_function_like_macros_use_macro_kind(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                #define PROJECT_MACRO(Value) Value
                class AWorker
                {
                public:
                    void BuildText();
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                void AWorker::BuildText()
                {
                    LOCTEXT("Key", "Value");
                    NSLOCTEXT("Namespace", "Key", "Value");
                    INVTEXT("Value");
                    UE_LOG(LogTemp, Log, TEXT("Message"));
                    DOREPLIFETIME(AWorker, Value);
                    PROJECT_MACRO(Value);
                    UNKNOWN_MACRO_STYLE();
                }
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "BuildText",
                "--include-syntax-flow",
            )

            self.assertEqual(completed.returncode, 0)
            symbols = {
                item["spelling"]: item["kind"]
                for item in result["matches"][0]["external_symbols"]
            }
            self.assertNotIn("LOCTEXT()", symbols)
            self.assertEqual(symbols["NSLOCTEXT()"], "macro")
            self.assertEqual(symbols["INVTEXT()"], "macro")
            self.assertEqual(symbols["TEXT()"], "macro")
            self.assertEqual(symbols["UE_LOG()"], "macro")
            self.assertEqual(symbols["DOREPLIFETIME()"], "macro")
            self.assertEqual(symbols["PROJECT_MACRO()"], "macro")
            self.assertEqual(symbols["UNKNOWN_MACRO_STYLE()"], "unknown")
            calls = {
                item["callee"]
                for item in result["matches"][0]["syntax_flow"]["calls"]
            }
            self.assertIn("LOCTEXT", calls)

    def test_member_call_receiver_uses_current_class_field_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                class AWorker
                {
                public:
                    void CheckExperience() const;

                private:
                    FPrimaryAssetId ExperienceOverride;
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                void AWorker::CheckExperience() const
                {
                    ExperienceOverride.IsValid();
                }
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "CheckExperience",
            )

            self.assertEqual(completed.returncode, 0)
            symbol = next(
                item
                for item in result["matches"][0]["external_symbols"]
                if item["spelling"].endswith("IsValid()")
            )
            self.assertEqual(symbol["kind"], "member_call")
            self.assertEqual(symbol["spelling"], "FPrimaryAssetId->IsValid()")
            self.assertEqual(symbol["owner_type"], "FPrimaryAssetId")
            self.assertEqual(symbol["evidence"], {"unit": "cpp", "line": 4})

    def test_function_inside_preprocessor_condition_is_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                class AWorker
                {
                public:
                #if WITH_EDITOR
                    void OnPlayInEditorStarted() const;
                #endif
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                #if WITH_EDITOR
                void AWorker::OnPlayInEditorStarted() const
                {
                }
                #endif
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "OnPlayInEditorStarted",
            )

            self.assertEqual(completed.returncode, 0)
            self.assertEqual(result["match_count"], 1)
            self.assertNotIn("selection", result)
            self.assertNotIn("function", result["matches"][0])
            self.assertNotIn("relation", result["matches"][0])

            completed, missing = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "MissingFunction",
            )
            self.assertEqual(completed.returncode, 1)
            self.assertNotIn("selection", missing)
            self.assertTrue(
                all("selection" not in item for item in missing["validation"]["problems"])
            )

    def test_function_id_and_external_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                class AWorker
                {
                public:
                    void Normalize(TArray<int>& Values) const;
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                int32 GCounter = 0;

                void AWorker::Normalize(TArray< int >& Values) const
                {
                    ++GCounter;
                }
                """,
            )

            completed, normalized = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "Normalize",
            )
            self.assertEqual(completed.returncode, 0)
            match = normalized["matches"][0]
            self.assertIn("AWorker|Normalize", match["function_id"])
            self.assertTrue(match["function_id"].rsplit("|", 1)[0].endswith(" const"))
            self.assertTrue(match["function_id"].endswith("|cpp:4:1"))
            global_symbol = next(
                item
                for item in match["external_symbols"]
                if item["kind"] == "global_variable"
            )
            self.assertEqual(global_symbol["spelling"], "GCounter")
            self.assertEqual(global_symbol["evidence"], {"unit": "cpp", "line": 6})

    def test_delegate_projection_ignores_non_delegate_register_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                DECLARE_MULTICAST_DELEGATE(FOnFinished);
                class AWorker
                {
                public:
                    FOnFinished OnFinishedEvent;
                    FOnFinished CompletedEvent;
                    void Activate();
                    void OnFinished();
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                void AWorker::Activate()
                {
                    FRouter Router;
                    Router.RegisterListenerInternal();
                    OnFinishedEvent.AddUObject(this, &AWorker::OnFinished);
                    CompletedEvent.Broadcast();
                }
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "Activate",
            )
            self.assertEqual(completed.returncode, 0)
            operations = result["matches"][0]["delegate_operations"]
            self.assertEqual(len(operations), 2)
            self.assertEqual(operations[0]["operation"], "add")
            self.assertEqual(operations[0]["api"], "AddUObject")
            self.assertEqual(
                operations[0]["callback"]["qualified_name"],
                "AWorker::OnFinished",
            )
            self.assertEqual(operations[1]["operation"], "broadcast")
            self.assertEqual(operations[1]["api"], "Broadcast")
            self.assertEqual(
                operations[1]["subject"]["qualified_name"],
                "AWorker::CompletedEvent",
            )

    def test_delegate_projection_ignores_ambiguous_container_add_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                class AWorker
                {
                public:
                    void Collect();
                    void OnFinished();
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                void AWorker::Collect()
                {
                    TMap<int32, int32> ValuesById;
                    TArray<int32> Values;
                    ValuesById.Add(1, 2);
                    Values.AddUnique(2);
                    ValuesById.Add(3, &AWorker::OnFinished);
                }
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "Collect",
            )

            self.assertEqual(completed.returncode, 0)
            match = result["matches"][0]
            self.assertEqual(match["delegate_operations"], [])
            function_address = next(
                item
                for item in match["external_symbols"]
                if item["spelling"] == "AWorker::OnFinished"
            )
            self.assertEqual(function_address["kind"], "function_address")

    def test_delegate_projection_accepts_locally_declared_ambiguous_apis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                DECLARE_MULTICAST_DELEGATE(FOnFinished);
                DECLARE_DYNAMIC_MULTICAST_DELEGATE(FOnDynamic);
                class AWorker
                {
                public:
                    void Activate();
                    void OnFinished();

                private:
                    FOnFinished FinishedEvent;
                    FOnDynamic UniqueFinishedEvent;
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                void AWorker::Activate()
                {
                    FOnFinished::FDelegate Callback;
                    FinishedEvent.Add(Callback);
                    FOnDynamic::FDelegate DynamicCallback;
                    UniqueFinishedEvent.AddUnique(DynamicCallback);
                }
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "Activate",
            )

            self.assertEqual(completed.returncode, 0)
            match = result["matches"][0]
            operations = match["delegate_operations"]
            self.assertEqual(
                [(item["operation"], item["api"]) for item in operations],
                [("add", "Add"), ("add", "AddUnique")],
            )
            self.assertTrue(all(item["resolution"]["status"] == "identified" for item in operations))
            self.assertTrue(all(item["callback"]["kind"] == "delegate_value" for item in operations))

    def test_delegate_projection_keeps_external_delegate_type_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            header = write_text(
                fixture.header,
                """
                #pragma once
                class AWorker
                {
                public:
                    void Activate();
                    void OnFinished();

                private:
                    FExternalDelegate ExternalEvent;
                };
                """,
            )
            source = write_text(
                fixture.source,
                """
                #include "Worker.h"
                void AWorker::Activate()
                {
                    ExternalEvent.Add(&AWorker::OnFinished);
                }
                """,
            )

            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py",
                "--source",
                source,
                header,
                "--function",
                "Activate",
            )

            self.assertEqual(completed.returncode, 0)
            match = result["matches"][0]
            self.assertEqual(len(match["delegate_operations"]), 1)
            self.assertEqual(match["delegate_operations"][0]["resolution"]["status"], "candidate")
            function_address = next(
                item
                for item in match["external_symbols"]
                if item["spelling"] == "AWorker::OnFinished"
            )
            self.assertEqual(function_address["kind"], "function_address")


if __name__ == "__main__":
    unittest.main()
