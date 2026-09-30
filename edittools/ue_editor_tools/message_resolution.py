"""Conservative local message value evidence; never infer runtime handle lifetime."""
from __future__ import annotations

import hashlib
import re

from ue_project_tools.cpp_frontend import _parser


def resolution(reason, evidence=()):
    next_steps = {
        'direct_tag': 'Tag is present in the call expression or native tag declaration.',
        'local_assignment': 'Observed straight-line local assignment; runtime delivery is not verified.',
        'runtime_parameter': 'Trace callers or capture the parameter in PIE to determine the runtime channel.',
        'runtime_assignment': 'Inspect the assignment source/configuration; no constant tag is proven.',
        'control_flow_or_mutation': 'Inspect branch, alias or mutation evidence before selecting a channel.',
        'expression_not_resolved': 'Inspect the expression declaration or capture its runtime value.',
        'listener_handle': 'Follow registration candidates; registration order and handle lifetime are not proven.',
    }
    return {'reason': reason, 'evidence': list(evidence), 'next_step': next_steps[reason]}


def identity(kind, *parts):
    return kind + ':' + hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:32]


def _walk(node):
    yield node
    for child in node.named_children:
        yield from _walk(child)


class AssignmentEvidence:
    def __init__(self, source):
        self.source = source
        self.tree = _parser().parse(source)
        self.calls = {n.start_byte: n for n in _walk(self.tree.root_node) if n.type == 'call_expression'}

    def text(self, node):
        return self.source[node.start_byte:node.end_byte].decode('utf-8') if node else ''

    def prior_assignment(self, call, target, path):
        """Only direct preceding siblings in the same block can supply a value."""
        node = self.calls.get(call['start_offset'])
        if node is None:
            return None, None
        child = node
        while child.parent and child.parent.type not in {'compound_statement', 'lambda_expression', 'function_definition'}:
            child = child.parent
        if not child.parent or child.parent.type != 'compound_statement':
            return None, None
        base = re.split(r'\.|->', target)[0]
        for sibling in reversed([n for n in child.parent.named_children if n.end_byte <= child.start_byte]):
            if sibling.type == 'comment':
                continue
            identifiers = {self.text(n) for n in _walk(sibling) if n.type in {'identifier', 'field_identifier'}}
            if base not in identifiers:
                continue
            children = [n for n in sibling.named_children if n.type != 'comment']
            assignment = children[0] if sibling.type == 'expression_statement' and len(children) == 1 else None
            evidence = {'path': path, 'line': sibling.start_point.row + 1, 'expression': self.text(sibling)}
            if assignment and assignment.type == 'assignment_expression':
                left = self.text(assignment.child_by_field_name('left')).strip()
                right = assignment.child_by_field_name('right')
                operator = self.text(assignment.child_by_field_name('operator'))
                if left == target and operator == '=':
                    return self.text(right).strip(), evidence
                # Setting another field does not overwrite the channel; reading or
                # passing the message on the RHS might do so and stops tracing.
                rhs_ids = {self.text(n) for n in _walk(right) if n.type == 'identifier'} if right else set()
                if left.startswith(base + '.') and left != target and base not in rhs_ids:
                    continue
            return None, evidence
        return None, None


def listener_fact(function, call, expression, types):
    owner = function['qualified_name'].rpartition('::')[0]
    name = expression.removeprefix('this->').removeprefix('this.').strip()
    binding = call.get('bindings', {}).get(name)
    owner_types = [t for t in types if t['qualified_name'] == owner and t.get('role') == 'definition']
    fields = [f for t in owner_types for f in t.get('fields', []) if f['name'] == name]
    is_member = not binding and len(fields) == 1
    key = owner + '::' + name if is_member else function['occurrence_id'] + '|' + name
    return {
        'listener_id': identity('listener', key), 'expression': expression,
        'owner': owner, 'scope': 'member' if is_member else 'function',
        'type': (fields[0].get('type_expression') if is_member else (binding or {}).get('type', {}).get('expression')),
        'registration_candidates': [],
    }
