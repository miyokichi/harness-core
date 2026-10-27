"""Actual CSV -> independent venv A -> independent venv B -> verification."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import venv

from seed_harness import Engine, Registry, Store


def prepare(directory):
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    specs = {}
    for label, entry in [('A', 'read_csv'), ('B', 'aggregate')]:
        env = root / ('venv' + label)
        venv.EnvBuilder(with_pip=False).create(env)
        python = env / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
        specs[entry] = {'kind': 'subprocess', 'python': str(python),
                        'cwd': str(Path(__file__).resolve().parents[1] / 'seed_harness'),
                        'entry': 'csv_tools:' + entry, 'timeout': 10,
                        'description': entry, 'input_schema': {'type': 'object'}}
    specs['verify'] = {'kind': 'python', 'entry': 'seed_harness.csv_tools:verify_csv'}
    (root / '測定データ.csv').write_text('value\n1\n2\n3\n', encoding='utf-8')
    ref = lambda p: {'$ref': p}
    flow = {'schema_version': 1, 'id': 'csv.v1', 'entry': 'read', 'nodes': {
        'read': {'kind': 'call', 'tool': 'read_csv', 'input': {'input_path': str(root / '測定データ.csv')}, 'next': 'ask'},
        'ask': {'kind': 'wait', 'question': '入力値の単位はmmですか、cmですか？',
                'answer_schema': {'type': 'object', 'properties': {'unit': {'enum': ['mm', 'cm']}}, 'required': ['unit'], 'additionalProperties': False}, 'next': 'aggregate'},
        'aggregate': {'kind': 'call', 'tool': 'aggregate', 'input': {'data': ref('steps.read'), 'unit': ref('steps.ask.unit'), 'output_path': str(root / '集計結果.json')}, 'next': 'verify'},
        'verify': {'kind': 'call', 'tool': 'verify', 'input': {'result': ref('steps.aggregate'), 'expected_total': 60, 'expected_count': 3}, 'next': 'finish'},
        'finish': {'kind': 'return', 'value': ref('steps.verify')}}}
    return root, specs, flow


def main():
    with tempfile.TemporaryDirectory() as temp:
        root, specs, flow = prepare(temp)
        store = Store(root / 'runs.sqlite3')
        engine = Engine(Registry(specs), store)
        run = engine.drive(engine.start(flow, {})['id'])
        assert run['status'] == 'waiting', run
        # Answer and continue in genuinely separate CLI processes.
        answer = root / '回答.json'
        answer.write_text('{"unit":"cm"}', encoding='utf-8')
        command = [sys.executable, '-m', 'seed_harness.cli', '--db', store.path]
        subprocess.run(command + ['resume', run['id'], '--pending-id', run['pending']['id'], '--answer', str(answer)], check=True, capture_output=True)
        subprocess.run(command + ['run', run['id']], check=True, capture_output=True)
        run = store.load(run['id'])
        assert run['status'] == 'completed' and run['result']['status'] == 'pass', run
        assert len([e for e in store.events(run['id']) if e['event'].get('tool') == 'read_csv']) == 1
        print(json.dumps(json.loads((root / '集計結果.json').read_text(encoding='utf-8')), ensure_ascii=False))
        print('PASS: 実CSV、2つのvenv、別CLIから回答・再開、60 mm / 3件')


if __name__ == '__main__':
    main()
