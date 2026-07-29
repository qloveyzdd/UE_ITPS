from __future__ import annotations

from tests.cxx_support import CxxAnalysisTestCase
from tests.support import write_text


class CxxFunctionTests(CxxAnalysisTestCase):
    def test_function_facts_match_declaration_and_external_references(self) -> None:
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Execute",
        )
        self.assertEqual(result["match_count"], 1)
        match = result["matches"][0]
        self.assertEqual(match["relation"]["status"], "matched")
        self.assertEqual(match["function"]["owner"], "USampleObject")
        self.assertEqual(
            match["external_symbols"],
            [
                {
                    "kind": "type",
                    "spelling": "UObject",
                    "evidence": {"unit": "cpp", "line": 4},
                },
                {
                    "kind": "member_call",
                    "spelling": "UObject->GetWorld()",
                    "owner_type": "UObject",
                    "evidence": {"unit": "cpp", "line": 8},
                },
                {
                    "kind": "type",
                    "spelling": "TObjectPtr<UObject>",
                    "evidence": {"unit": "cpp", "line": 9},
                },
                {
                    "kind": "member_call",
                    "spelling": "TObjectPtr<UObject>->GetName()",
                    "owner_type": "TObjectPtr<UObject>",
                    "evidence": {"unit": "cpp", "line": 9},
                },
            ],
        )
        self.assertNotIn("external_types", match)
        self.assertNotIn("external_methods", match)

    def test_function_facts_keep_namespace_in_local_identity(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            namespace A
            {
                void Tick();
            }
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            namespace A
            {
                void Tick() {}
            }
            namespace B
            {
                void Tick() {}
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Tick",
        )

        self.assertEqual(result["match_count"], 2)
        matches = {
            item["function"]["qualified_name"]: item
            for item in result["matches"]
        }
        self.assertEqual(set(matches), {"A::Tick", "B::Tick"})
        self.assertEqual(
            matches["A::Tick"]["function"]["namespace"],
            "A",
        )
        self.assertEqual(
            matches["B::Tick"]["function"]["namespace"],
            "B",
        )
        self.assertEqual(
            matches["A::Tick"]["function_id"],
            "free_function|A||Tick|()|",
        )
        self.assertEqual(
            matches["B::Tick"]["function_id"],
            "free_function|B||Tick|()|",
        )
        self.assertEqual(
            matches["A::Tick"]["relation"]["status"],
            "matched",
        )
        self.assertEqual(
            matches["B::Tick"]["relation"]["status"],
            "source_only",
        )

    def test_function_facts_namespace_same_named_class_methods(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            namespace A
            {
                class FWorker
                {
                    void Run();
                };
            }
            namespace B
            {
                class FWorker
                {
                    void Run();
                };
            }
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            void A::FWorker::Run() {}
            void B::FWorker::Run() {}
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Run",
        )

        matches = {
            item["function"]["qualified_name"]: item
            for item in result["matches"]
        }
        self.assertEqual(
            set(matches),
            {"A::FWorker::Run", "B::FWorker::Run"},
        )
        self.assertEqual(
            matches["A::FWorker::Run"]["function_id"],
            "method|A|FWorker|Run|()|",
        )
        self.assertEqual(
            matches["B::FWorker::Run"]["function_id"],
            "method|B|FWorker|Run|()|",
        )
        self.assertTrue(
            all(
                item["relation"]["status"] == "matched"
                for item in matches.values()
            )
        )

    def test_function_facts_keep_nested_class_owner_chain(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            namespace A
            {
                class FOuterOne
                {
                    class FInner
                    {
                        void Run();
                    };
                };
                class FOuterTwo
                {
                    class FInner
                    {
                        void Run();
                    };
                };
            }
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            void A::FOuterOne::FInner::Run() {}
            void A::FOuterTwo::FInner::Run() {}
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Run",
        )

        matches = {
            item["function"]["qualified_name"]: item
            for item in result["matches"]
        }
        self.assertEqual(
            set(matches),
            {
                "A::FOuterOne::FInner::Run",
                "A::FOuterTwo::FInner::Run",
            },
        )
        self.assertEqual(
            matches[
                "A::FOuterOne::FInner::Run"
            ]["function"]["owner"],
            "FOuterOne::FInner",
        )
        self.assertEqual(
            matches[
                "A::FOuterTwo::FInner::Run"
            ]["function"]["owner"],
            "FOuterTwo::FInner",
        )
        self.assertEqual(
            matches[
                "A::FOuterOne::FInner::Run"
            ]["function_id"],
            "method|A|FOuterOne::FInner|Run|()|",
        )
        self.assertEqual(
            matches[
                "A::FOuterTwo::FInner::Run"
            ]["function_id"],
            "method|A|FOuterTwo::FInner|Run|()|",
        )
        self.assertTrue(
            all(
                item["relation"]["status"] == "matched"
                for item in matches.values()
            )
        )

    def test_function_reports_external_symbol_categories_with_evidence(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            struct FMyConfig {};
            class UMySystem
            {
            public:
                void Initialize();
            };
            extern UMySystem* GDefaultSystem;
            UMySystem* CreateDefaultSystem(const FMyConfig& Config);
            void HandleReady();
            class UConsumer
            {
            public:
                void Execute(const FMyConfig& Config);
                void HandleMember();
            private:
                FSimpleDelegate ReadyDelegate;
            };
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            void UConsumer::Execute(const FMyConfig& Config)
            {
                UMySystem* System = GDefaultSystem;
                if (!System)
                {
                    System = CreateDefaultSystem(Config);
                }
                System->Initialize();
                auto Factory = &CreateDefaultSystem;
                FCoreDelegates::OnPostEngineInit.AddStatic(&HandleReady);
                ReadyDelegate.BindUObject(this, &UConsumer::HandleMember);
                ExternalRegistry.Service();
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Execute",
        )
        symbols = result["matches"][0]["external_symbols"]
        self.assertEqual(
            symbols,
            [
                {
                    "kind": "type",
                    "spelling": "FMyConfig",
                    "evidence": {"unit": "cpp", "line": 2},
                },
                {
                    "kind": "type",
                    "spelling": "UMySystem",
                    "evidence": {"unit": "cpp", "line": 4},
                },
                {
                    "kind": "global_variable",
                    "spelling": "GDefaultSystem",
                    "evidence": {"unit": "cpp", "line": 4},
                },
                {
                    "kind": "free_function",
                    "spelling": "CreateDefaultSystem",
                    "evidence": {"unit": "cpp", "line": 7},
                },
                {
                    "kind": "member_call",
                    "spelling": "UMySystem->Initialize()",
                    "owner_type": "UMySystem",
                    "evidence": {"unit": "cpp", "line": 9},
                },
                {
                    "kind": "function_address",
                    "spelling": "CreateDefaultSystem",
                    "evidence": {"unit": "cpp", "line": 10},
                },
                {
                    "kind": "unknown",
                    "spelling": (
                        "FCoreDelegates::OnPostEngineInit."
                        "AddStatic(&HandleReady)"
                    ),
                    "evidence": {"unit": "cpp", "line": 11},
                },
                {
                    "kind": "callback_target",
                    "spelling": "HandleReady",
                    "evidence": {"unit": "cpp", "line": 11},
                },
                {
                    "kind": "type",
                    "spelling": "FSimpleDelegate",
                    "evidence": {"unit": "cpp", "line": 12},
                },
                {
                    "kind": "member_call",
                    "spelling": (
                        "FSimpleDelegate.BindUObject("
                        "this, &UConsumer::HandleMember)"
                    ),
                    "owner_type": "FSimpleDelegate",
                    "evidence": {"unit": "cpp", "line": 12},
                },
                {
                    "kind": "callback_target",
                    "spelling": "UConsumer::HandleMember",
                    "owner_type": "UConsumer",
                    "evidence": {"unit": "cpp", "line": 12},
                },
                {
                    "kind": "unknown",
                    "spelling": "ExternalRegistry.Service()",
                    "evidence": {"unit": "cpp", "line": 13},
                },
            ],
        )

    def test_function_calls_require_confirmed_symbol_categories(self) -> None:
        write_text(self.fixture.header_file, "#pragma once")
        write_text(
            self.fixture.source_file,
            """
            class UConsumer
            {
                TFunction<void()> MemberCallback;
                void Execute(TFunction<void()> Callback);
            };
            class FConfirmedType
            {
            public:
                static void Sort();
            };
            void UConsumer::Execute(TFunction<void()> Callback)
            {
                TFunction<void()> LocalCallback = Callback;
                Callback();
                LocalCallback();
                MemberCallback();
                Algo::Sort(Values);
                FConfirmedType::Sort();
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Execute",
        )
        self.assertEqual(
            result["matches"][0]["external_symbols"],
            [
                {
                    "kind": "type",
                    "spelling": "TFunction<void()>",
                    "evidence": {"unit": "cpp", "line": 11},
                },
                {
                    "kind": "unknown",
                    "spelling": "Algo::Sort(Values)",
                    "evidence": {"unit": "cpp", "line": 17},
                },
                {
                    "kind": "type",
                    "spelling": "FConfirmedType",
                    "evidence": {"unit": "cpp", "line": 18},
                },
                {
                    "kind": "member_call",
                    "spelling": "FConfirmedType::Sort()",
                    "owner_type": "FConfirmedType",
                    "evidence": {"unit": "cpp", "line": 18},
                },
            ],
        )

    def test_function_bare_calls_require_local_callable_facts(self) -> None:
        write_text(self.fixture.header_file, "#pragma once")
        write_text(
            self.fixture.source_file,
            """
            void DeclaredFree();
            class UChild
            {
            public:
                void Run();
                void LocalMethod();
            };
            void UChild::Run()
            {
                DeclaredFree();
                LocalMethod();
                Refresh();
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Run",
        )
        self.assertEqual(
            result["matches"][0]["external_symbols"],
            [
                {
                    "kind": "free_function",
                    "spelling": "DeclaredFree",
                    "evidence": {"unit": "cpp", "line": 10},
                },
                {
                    "kind": "member_call",
                    "spelling": "UChild->LocalMethod()",
                    "owner_type": "UChild",
                    "evidence": {"unit": "cpp", "line": 11},
                },
                {
                    "kind": "unknown",
                    "spelling": "Refresh()",
                    "evidence": {"unit": "cpp", "line": 12},
                },
            ],
        )

    def test_function_preserves_qualified_global_variable_spelling(self) -> None:
        write_text(self.fixture.header_file, "#pragma once")
        write_text(
            self.fixture.source_file,
            """
            namespace Gameplay
            {
                extern bool GEnabled;
            }
            class FObject
            {
            public:
                static bool GEnabled;
            };
            void CheckGlobals(FObject* Object)
            {
                FObject ObjectValue;
                if (Gameplay::GEnabled) {}
                if (ObjectValue.GEnabled) {}
                if (Object->GEnabled) {}
                if (FObject::GEnabled) {}
                if (GPlainEnabled) {}
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "CheckGlobals",
        )
        symbols = result["matches"][0]["external_symbols"]
        self.assertEqual(
            [
                item
                for item in symbols
                if item["kind"] == "global_variable"
            ],
            [
                {
                    "kind": "global_variable",
                    "spelling": "Gameplay::GEnabled",
                    "evidence": {"unit": "cpp", "line": 13},
                },
                {
                    "kind": "global_variable",
                    "spelling": "GPlainEnabled",
                    "evidence": {"unit": "cpp", "line": 17},
                },
            ],
        )
        self.assertEqual(
            {
                item["spelling"]
                for item in symbols
                if item["kind"] == "unknown"
            },
            {
                "ObjectValue.GEnabled",
                "Object->GEnabled",
                "FObject::GEnabled",
            },
        )

    def test_function_requires_qualified_namespace_global_evidence(self) -> None:
        write_text(self.fixture.header_file, "#pragma once")
        write_text(
            self.fixture.source_file,
            """
            namespace A
            {
                extern int Value;
            }

            namespace B
            {
                void Run()
                {
                    B::Value;
                    A::Value;
                    B::GHeuristic;
                }
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Run",
        )
        self.assertEqual(
            result["matches"][0]["external_symbols"],
            [
                {
                    "kind": "unknown",
                    "spelling": "B::Value",
                    "evidence": {"unit": "cpp", "line": 10},
                },
                {
                    "kind": "global_variable",
                    "spelling": "A::Value",
                    "evidence": {"unit": "cpp", "line": 11},
                },
                {
                    "kind": "global_variable",
                    "spelling": "B::GHeuristic",
                    "evidence": {"unit": "cpp", "line": 12},
                },
            ],
        )

    def test_function_uses_namespace_facts_for_calls_and_addresses(self) -> None:
        write_text(self.fixture.header_file, "#pragma once")
        write_text(
            self.fixture.source_file,
            """
            namespace Gameplay
            {
                void Create();
                void Handle();
            }
            class FHandler
            {
            public:
                static void Handle();
            };
            void TestNamespaceReferences()
            {
                Gameplay::Create();
                Unknown::Create();
                auto Callback = &Gameplay::Handle;
                auto Member = &FHandler::Handle;
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "TestNamespaceReferences",
        )
        self.assertEqual(
            result["matches"][0]["external_symbols"],
            [
                {
                    "kind": "free_function",
                    "spelling": "Gameplay::Create",
                    "evidence": {"unit": "cpp", "line": 13},
                },
                {
                    "kind": "unknown",
                    "spelling": "Unknown::Create()",
                    "evidence": {"unit": "cpp", "line": 14},
                },
                {
                    "kind": "function_address",
                    "spelling": "Gameplay::Handle",
                    "evidence": {"unit": "cpp", "line": 15},
                },
                {
                    "kind": "function_address",
                    "spelling": "FHandler::Handle",
                    "owner_type": "FHandler",
                    "evidence": {"unit": "cpp", "line": 16},
                },
                {
                    "kind": "type",
                    "spelling": "FHandler",
                    "evidence": {"unit": "cpp", "line": 16},
                },
            ],
        )

    def test_function_resolves_member_address_in_current_namespace(self) -> None:
        write_text(self.fixture.header_file, "#pragma once")
        write_text(
            self.fixture.source_file,
            """
            namespace A
            {
                class FHandler
                {
                public:
                    static void Handle();
                };
                void Test()
                {
                    auto P = &FHandler::Handle;
                }
            }
            """,
        )
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Test",
        )
        self.assertEqual(
            result["matches"][0]["external_symbols"],
            [
                {
                    "kind": "function_address",
                    "spelling": "FHandler::Handle",
                    "owner_type": "FHandler",
                    "evidence": {"unit": "cpp", "line": 10},
                },
                {
                    "kind": "type",
                    "spelling": "FHandler",
                    "evidence": {"unit": "cpp", "line": 10},
                },
            ],
        )

    def test_same_name_overloads_have_stable_unique_ids(self) -> None:
        write_text(
            self.fixture.header_file,
            """
            #pragma once
            class USampleObject
            {
            public:
                void Execute(UObject* Context) const;
                void Execute(int32 Count);
            };
            """,
        )
        write_text(
            self.fixture.source_file,
            """
            #include "SampleFeature.h"
            void USampleObject::Execute(UObject* Context) const {}
            void USampleObject::Execute(int32 Count) {}
            """,
        )
        first = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Execute",
        )
        second = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "Execute",
        )
        first_ids = [item["function_id"] for item in first["matches"]]
        second_ids = [item["function_id"] for item in second["matches"]]
        self.assertEqual(first["match_count"], 2)
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(len(first_ids), len(set(first_ids)))

    def test_missing_function_is_structured_scan_error(self) -> None:
        result = self.source_result(
            "ue_inspect_cxx_function.py",
            "--function",
            "DoesNotExist",
            expected_code=1,
        )
        self.assertEqual(result["match_count"], 0)
        self.assertEqual(result["validation"]["status"], "error")
        self.assertIn(
            "function-not-found",
            {problem["code"] for problem in result["validation"]["problems"]},
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
