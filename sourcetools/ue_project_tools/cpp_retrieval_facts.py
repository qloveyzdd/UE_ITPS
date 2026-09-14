"""Syntax evidence for retrieval, without interpreting API behavior or data flow."""
from .cpp_expression_facts import execution_scope
from .cpp_source_text import source_fragment


def call_contexts(node, source):
    result = []
    child, parent = node, node.parent
    while parent is not None and parent.type not in {'lambda_expression', 'function_definition'}:
        if parent.type == 'argument_list' and parent.parent.type == 'call_expression':
            args = [arg for arg in parent.named_children if arg.type != 'comment']
            if child in args:
                outer = parent.parent
                result.append({'callee': source_fragment(outer.child_by_field_name('function'), source),
                               'argument': args.index(child),
                               'location': {'line': outer.start_point.row + 1, 'column': outer.start_point.column + 1}})
        child, parent = parent, parent.parent
    return result


def statement(node, source):
    kind = {'field_initializer': 'initialization', 'init_declarator': 'initialization',
            'assignment_expression': 'assignment', 'update_expression': 'update',
            'return_statement': 'return'}.get(node.type)
    target = value = None
    selected = node
    if node.type == 'field_initializer':
        children = [c for c in node.named_children if c.type != 'comment']
        if len(children) >= 2:
            target, value = children[0], children[-1]
    elif node.type == 'init_declarator':
        target, value = node.child_by_field_name('declarator'), node.child_by_field_name('value')
    elif node.type == 'assignment_expression':
        target, value = node.child_by_field_name('left'), node.child_by_field_name('right')
    elif node.type == 'update_expression':
        target = node.child_by_field_name('argument')
    elif node.type == 'return_statement':
        value = next((c for c in node.named_children if c.type != 'comment'), None)
    elif node.type in {'if_statement', 'while_statement', 'do_statement', 'for_statement', 'switch_statement', 'conditional_expression'}:
        selected = node.child_by_field_name('condition')
        if selected is not None:
            kind, value = 'condition', selected
    if kind is None:
        return None
    result = {'kind': kind, 'expression': source_fragment(selected, source),
              'location': {'line': selected.start_point.row + 1, 'column': selected.start_point.column + 1},
              'execution_scope': execution_scope(node, source)}
    if target is not None:
        result['target'] = source_fragment(target, source)
    if value is not None:
        result['value'] = source_fragment(value, source)
    return result
