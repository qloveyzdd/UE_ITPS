from pathlib import Path
import sys
import tempfile
import unittest

from tests.support import ROOT, create_fixture, write_text, run_cli

sys.path.insert(0, str(ROOT / 'sourcetools'))


class RetrievalContextTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.fixture = create_fixture(Path(directory.name))
        write_text(self.fixture.header, '''
            struct FWorker { TArray<int> Pending; TMap<int,int> Dirty; bool Enabled;
                FWorker(); void Run(); };
        ''')

    def inspect(self, text, name='FWorker::Run', *options):
        write_text(self.fixture.source, text)
        completed, result = run_cli('sourcetools/ue_inspect_cxx_function.py', '--source',
                                   self.fixture.source, self.fixture.header, '--function', name,
                                   '--view', 'behavior', '--include-syntax-flow', *options)
        self.assertEqual(completed.returncode, 0, result)
        return result['matches'][0]

    def test_state_writes_expand_even_when_result_is_discarded(self):
        match = self.inspect('''void FWorker::Run() {
            Pending.AddUnique(1); Pending.Reset(); Dirty.Add(1,2); Dirty.Remove(1);
            Pending.Reserve(10);
        }''')
        groups = match['symbol_groups']
        for method in ('AddUnique', 'Reset', 'Add', 'Remove'):
            self.assertTrue(any(g['spelling'].endswith('->' + method + '()') and g.get('display', 'expand') == 'expand' for g in groups))
        reserve = next(g for g in groups if g['spelling'].endswith('->Reserve()'))
        self.assertEqual(reserve['display'], 'fold')

    def test_log_arguments_group_by_source_occurrence_and_focus_can_extract(self):
        text = '''void FWorker::Run() {
            UE_LOG(LogTemp, Log, TEXT("%s %s"), *First.GetName(), *Second.GetName());
            UE_LOG(LogTemp, Log, TEXT("%s"), *First.GetName());
            First.GetName();
        }'''
        match = self.inspect(text)
        self.assertEqual([sum(g['count'] for g in log['symbol_groups']) for log in match['log_groups']], [2, 1])
        self.assertEqual(sum(g['count'] for g in match['symbol_groups'] if 'GetName' in g['spelling']), 1)
        self.assertTrue(all(log['display'] == 'fold' for log in match['log_groups']))
        focused = self.inspect(text, 'FWorker::Run', '--focus', 'First.GetName')
        self.assertEqual(sum(g['count'] for g in focused['symbol_groups'] if 'First.GetName' in g['spelling']), 3)

    def test_log_conditions_writes_and_lambda_bodies_are_not_suppressed(self):
        match = self.inspect('''void FWorker::Run() {
            UE_CLOG(ShouldLog(), LogTemp, Log, TEXT("%d"), Dirty.Remove(1));
            UE_LOG(LogTemp, Log, TEXT("%d"), [&] { SideEffect(); return Pending.Num(); }());
        }''')
        groups = match['symbol_groups']
        for part in ('ShouldLog', 'Remove', 'SideEffect', 'Num'):
            self.assertTrue(any(part in g['spelling'] and g.get('display', 'expand') == 'expand' for g in groups), part)
        num = next(g for g in groups if '->Num()' in g['spelling'])
        self.assertEqual(num['execution_scope']['kind'], 'lambda')

    def test_non_call_evidence_keeps_constructor_defaults_and_state_transitions(self):
        constructor = self.inspect('FWorker::FWorker() : Enabled(false) {}', 'FWorker::FWorker')
        self.assertEqual(constructor['syntax_flow']['calls'], [])
        self.assertEqual(constructor['statement_summary']['initialization'], 1)
        init = constructor['syntax_flow']['statements'][0]
        self.assertEqual((init['target'], init['value']), ('Enabled', '(false)'))
        match = self.inspect('''void FWorker::Run() {
            int Count = 0;
            if (Enabled) { Count += 2; }
            auto Callback = [&] { ++Count; return Count; };
        }''')
        statements = match['syntax_flow']['statements']
        self.assertTrue({'initialization', 'assignment', 'update', 'condition', 'return'} <= {s['kind'] for s in statements})
        returned = next(s for s in statements if s['kind'] == 'return')
        self.assertEqual(returned['execution_scope']['kind'], 'lambda')
        self.assertEqual(returned['value'], 'Count')
