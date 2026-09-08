from pathlib import Path
import tempfile
import unittest

from tests.support import create_fixture, run_cli, write_text


class DelegateAnalysisTests(unittest.TestCase):
    def scan(self, header, body):
        with tempfile.TemporaryDirectory() as directory:
            fixture = create_fixture(Path(directory))
            write_text(fixture.header, header)
            write_text(fixture.source, body)
            completed, result = run_cli(
                "sourcetools/ue_inspect_cxx_function.py", "--source", fixture.source,
                fixture.header, "--function", "FWorker::Run",
            )
            self.assertEqual(completed.returncode, 0, result)
            return result["matches"][0]

    def test_function_local_declaration_and_local_callback_keep_lexical_scope(self):
        match = self.scan("""
            class FWorker { void Run(); };
        """, """
            void FWorker::Run() {
                DECLARE_DELEGATE(FDone);
                struct Local { static void Ready() {} };
                FDone Done = FDone::CreateStatic(&Local::Ready);
                Done.Execute();
            }
        """)
        operations = match["delegate_operations"]
        self.assertEqual([o["operation"] for o in operations], ["create", "execute"])
        self.assertTrue(all(o["resolution"]["status"] == "identified" for o in operations))
        self.assertEqual(operations[0]["delegate_type"]["qualified_name"], "FWorker::Run::FDone")
        self.assertEqual(operations[0]["callback"]["qualified_name"], "FWorker::Run::Local::Ready")

    def test_native_lifecycle_and_payload_address(self):
        match = self.scan("""
            DECLARE_DELEGATE(FDone);
            DECLARE_MULTICAST_DELEGATE(FChanged);
            class FWorker { FDone Done; FChanged Changed; void Run(); void Ready(); };
        """, """
            void FWorker::Run() {
                FDone Local = FDone::CreateUObject(this, &FWorker::Ready);
                Done.BindUObject(this, &FWorker::Ready, &Payload);
                FDelegateHandle Handle = Changed.Add(Local);
                Done.ExecuteIfBound();
                Changed.Broadcast();
                Changed.Remove(Handle);
                Changed.RemoveAll(this);
                Changed.Clear();
                Done.Unbind();
                Done.IsBound();
            }
        """)
        ops = match["delegate_operations"]
        self.assertEqual([o["operation"] for o in ops],
                         ["create", "bind", "add", "execute", "broadcast", "remove",
                          "remove", "clear", "unbind", "query"])
        self.assertTrue(all(o["resolution"]["status"] == "identified" for o in ops))
        self.assertEqual(ops[0]["result"]["expression"], "Local")
        self.assertEqual(ops[2]["result"]["expression"], "Handle")
        self.assertEqual(ops[2]["callback"]["kind"], "delegate_value")
        self.assertEqual(ops[1]["arguments"][-1]["role"], "payload")
        self.assertNotIn("event", ops[0])
        self.assertFalse(any(s["kind"] == "callback_target" and s["spelling"] == "Payload"
                             for s in match["external_symbols"]))

    def test_parameters_and_lambda_have_no_fabricated_owner(self):
        match = self.scan("""
            DECLARE_DELEGATE(FDone);
            class FWorker { void Run(FDone Callback); };
        """, """
            void FWorker::Run(FDone Callback) {
                auto Local = FDone::CreateWeakLambda(this, [Callback]() { Callback.Execute(); });
                Callback.ExecuteIfBound();
            }
        """)
        ops = match["delegate_operations"]
        self.assertEqual([o["operation"] for o in ops], ["create", "execute", "execute"])
        self.assertEqual(ops[0]["callback"]["kind"], "lambda")
        self.assertEqual(ops[1]["execution_scope"]["kind"], "lambda")
        self.assertEqual(ops[2]["subject"]["kind"], "parameter")
        self.assertIsNone(ops[2]["subject"]["qualified_name"])

    def test_dynamic_operations_and_non_delegate_lookalikes(self):
        match = self.scan("""
            DECLARE_DYNAMIC_DELEGATE(FSingle);
            DECLARE_DYNAMIC_MULTICAST_DELEGATE(FMulti);
            struct FPlain { void Broadcast(); };
            class FWorker { FSingle Done; FMulti Changed; FPlain Plain; void Run(); void Ready(); };
        """, """
            void FWorker::Run() {
                Done.BindDynamic(this, &FWorker::Ready);
                Changed.AddUniqueDynamic(this, &FWorker::Ready);
                Changed.RemoveDynamic(this, &FWorker::Ready);
                Plain.Broadcast();
                TArray<int> Values; Values.Add(1); Values.Remove(1); Values.Clear();
                Missing.Execute();
            }
        """)
        ops = match["delegate_operations"]
        self.assertEqual([o["operation"] for o in ops], ["bind", "add", "remove", "execute"])
        self.assertEqual(ops[0]["delegate_type"]["dispatch"], "dynamic")
        self.assertEqual(ops[-1]["resolution"]["status"], "candidate")

    def test_scoped_alias_and_returned_delegate(self):
        match = self.scan("""
            namespace Events { DECLARE_MULTICAST_DELEGATE(FChanged); }
            namespace Other { struct FChanged {}; }
            using FSignal = Events::FChanged;
            class FWorker { FSignal Changed; FSignal& GetChanged(); void Run(); };
        """, """
            void FWorker::Run() {
                GetChanged().Broadcast();
                Other::FChanged Plain; Plain.Broadcast();
                { Other::FChanged Changed; Changed.Broadcast(); }
                Changed.Broadcast();
            }
        """)
        ops = match["delegate_operations"]
        self.assertEqual(len(ops), 2)
        self.assertEqual(ops[0]["subject"]["kind"], "return_value")
        self.assertEqual(ops[0]["delegate_type"]["qualified_name"], "Events::FChanged")
        self.assertEqual(ops[1]["subject"]["qualified_name"], "FWorker::Changed")

    def test_binding_forms_and_direct_nested_creation(self):
        forms = [
            ("Static", "FWorker::StaticReady", "function"),
            ("Raw", "this, &FWorker::Ready", "member_function"),
            ("SP", "Shared, &FWorker::Ready", "member_function"),
            ("ThreadSafeSP", "Shared, &FWorker::Ready", "member_function"),
            ("UObject", "this, &FWorker::Ready", "member_function"),
            ("UFunction", 'this, FName("Ready")', "reflection_name"),
            ("Lambda", "[]() {}", "lambda"),
            ("SPLambda", "Shared, []() {}", "lambda"),
            ("WeakLambda", "this, []() {}", "lambda"),
        ]
        body = "void FWorker::Run() {\n" + "\n".join(
            f"FDone::Create{suffix}({args}); Done.Bind{suffix}({args}); Changed.Add{suffix}({args});"
            for suffix, args, _ in forms
        ) + "\n Changed.Add(FDone::CreateUObject(this, &FWorker::Ready)); }"
        match = self.scan("""
            DECLARE_DELEGATE(FDone);
            DECLARE_MULTICAST_DELEGATE(FChanged);
            class FWorker { FDone Done; FChanged Changed; void Run(); void Ready(); static void StaticReady(); };
        """, body)
        ops = match["delegate_operations"]
        self.assertEqual(len(ops), 29)
        self.assertTrue(all(o["resolution"]["status"] == "identified" for o in ops))
        self.assertEqual([o["operation"] for o in ops[:27]], ["create", "bind", "add"] * 9)
        self.assertEqual([o["callback"]["kind"] for o in ops[:27:3]],
                         [kind for _, _, kind in forms])
        self.assertEqual(ops[-2]["callback"]["source_operation"], ops[-1]["operation_id"])

    def test_direct_templates_typedefs_events_and_thread_safe_declarations(self):
        match = self.scan("""
            DECLARE_EVENT(FWorker, FEvent);
            DECLARE_TS_MULTICAST_DELEGATE(FTSChanged);
            DECLARE_DELEGATE_RetVal(int, FValue);
            typedef FValue FValueAlias;
            class FWorker { FEvent Event; FTSChanged ThreadEvent; void Run(); };
        """, """
            void FWorker::Run() {
                TDelegate<void()> Single;
                TMulticastDelegate<void()> Multi;
                Single.ExecuteIfBound(); Multi.Broadcast();
                TDelegate<void()>::CreateLambda([]() {});
                Event.Broadcast(); ThreadEvent.Broadcast();
                FValueAlias Value; Value.Execute();
            }
        """)
        ops = match["delegate_operations"]
        self.assertEqual(len(ops), 6)
        self.assertTrue(all(o["resolution"]["status"] == "identified" for o in ops))
        self.assertEqual(ops[3]["delegate_type"]["policy"], "event")
        self.assertEqual(ops[4]["delegate_type"]["policy"], "thread_safe")
        self.assertEqual(ops[5]["delegate_type"]["qualified_name"], "FValue")

    def test_wrong_cardinality_and_non_callable_payload_do_not_become_callbacks(self):
        match = self.scan("""
            DECLARE_DELEGATE(FDone);
            DECLARE_MULTICAST_DELEGATE(FChanged);
            class FWorker { FDone Done; FChanged Changed; void Run(); void Ready(); };
        """, """
            void FWorker::Run() {
                Done.Broadcast();
                Changed.AddUnique(FDone());
                Changed.Add(&FWorker::Ready);
                Done.BindLambda([]() { auto Address = &FWorker::Ready; });
            }
        """)
        ops = match["delegate_operations"]
        self.assertEqual([o["resolution"]["status"] for o in ops],
                         ["candidate", "candidate", "candidate", "identified"])
        self.assertFalse(any(s["kind"] == "callback_target" for s in match["external_symbols"]))

    def test_chained_temporary_operations_have_distinct_ids(self):
        match = self.scan("""
            DECLARE_DELEGATE(FDone);
            class FWorker { void Run(); };
        """, """
            void FWorker::Run() { FDone::CreateLambda([]() {}).ExecuteIfBound(); }
        """)
        operations = match["delegate_operations"]
        self.assertEqual({o["operation"] for o in operations}, {"create", "execute"})
        self.assertEqual(len({o["operation_id"] for o in operations}), 2)
        execute = next(o for o in operations if o["operation"] == "execute")
        self.assertEqual(execute["subject"]["kind"], "temporary")
        self.assertEqual(execute["resolution"]["status"], "identified")
