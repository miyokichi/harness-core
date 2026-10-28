"""Public smoke-test business function and independent completion verifier."""


def seven():
    return 7


def verify(state, result):
    checks = [result == 7, 7 in state['observations'],
              any(answer.get('approved') is True for answer in state['answers'])]
    return {'status': 'pass' if all(checks) else 'fail',
            'checks': ['result seven', 'tool observation seven', 'explicit human approval']}


def verify_seven(state, result):
    return {'status': 'pass' if result == 7 and 7 in state['observations'] else 'fail',
            'checks': ['result seven', 'tool observation seven']}
