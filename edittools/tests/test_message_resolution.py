from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ue_editor_tools.cxx_messages import scan_cxx_gameplay_messages
from ue_editor_tools.knowledge_graph import build_knowledge_graph


class MessageResolutionTests(unittest.TestCase):
    def scan(self, body):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / 'Sample.uproject'
            project.write_text('{}', encoding='utf-8')
            (root / 'Source').mkdir()
            (root / 'Source/Sample.cpp').write_text(body, encoding='utf-8')
            return scan_cxx_gameplay_messages(project)['operations']

    def test_straight_line_assignment_keeps_its_evidence(self):
        operation = self.scan('''
UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_Test, "Game.Test");
void UThing::Send() {
    FPayload Message;
    Message.Verb = TAG_Test;
    Message.Magnitude = 1;
    Router.BroadcastMessage(Message.Verb, Message);
}''')[0]
        self.assertEqual(operation['channel']['tag'], 'Game.Test')
        self.assertEqual(operation['channel']['resolution']['reason'], 'local_assignment')
        self.assertEqual(operation['channel']['resolution']['evidence'][0]['line'], 5)

    def test_branch_mutation_and_lambda_do_not_confirm_a_tag(self):
        for middle in ('if (Changed) Message.Verb = Other;',
                       'Mutate(Message);', 'Message = Other;',
                       'auto Deferred = [&] { Message.Verb = TAG_Test; };'):
            with self.subTest(middle=middle):
                operation = self.scan('''
UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_Test, "Game.Test");
void UThing::Send() {
    FPayload Message;
    Message.Verb = TAG_Test;
''' + middle + '''
    Router.BroadcastMessage(Message.Verb, Message);
}''')[0]
                self.assertIsNone(operation['channel']['tag'])
                self.assertIn('reason', operation['channel']['resolution'])

    def test_runtime_parameter_is_explicit(self):
        channel = self.scan('''void UThing::Forward(const FPayload& Message) {
    Router.BroadcastMessage(Message.Verb, Message);
}''')[0]['channel']
        self.assertEqual(channel['status'], 'dynamic')
        self.assertEqual(channel['resolution']['reason'], 'runtime_parameter')

    def test_runtime_channel_keeps_static_callers_for_follow_up(self):
        operations = self.scan('''
void Forward(const FPayload& Message) {
    Router.BroadcastMessage(Message.Verb, Message);
}
void Caller(const FPayload& Message) { Forward(Message); }
''')
        operation = operations[0]
        self.assertEqual(operation['channel']['resolution']['reason'], 'runtime_parameter')
        self.assertEqual(operation['runtime_callers'][0]['source'], 'Caller')

    def test_handle_keeps_registration_candidate_and_stable_identity(self):
        operations = self.scan('''
UE_DEFINE_GAMEPLAY_TAG_STATIC(TAG_Test, "Game.Test");
class UThing { FGameplayMessageListenerHandle Handle; };
void UThing::Start() { Handle = Router.RegisterListener(TAG_Test, this, &UThing::Receive); }
void UThing::Stop() { Router.UnregisterListener(Handle); }
''')
        registration, removal = operations
        self.assertEqual(removal['listener']['listener_id'], registration['listener']['listener_id'])
        self.assertEqual(removal['listener']['registration_candidates'][0]['channel']['tag'], 'Game.Test')
        graph, problems = build_knowledge_graph([('messages.json', {
            'schema_version': 'ue_scan_cxx_gameplay_messages', 'operations': operations})])
        self.assertFalse(problems)
        edge = next(r for r in graph['relations'] if r['kind'] == 'UNSUBSCRIBES_EVENT')
        target = next(n for n in graph['nodes'] if n['node_id'] == edge['target_id'])
        self.assertEqual(target['kind'], 'message_listener_handle')
        self.assertEqual(edge['certainty'], 'candidate')


if __name__ == '__main__':
    unittest.main()
