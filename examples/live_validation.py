"""Opt-in integration checks against the configured real LLM (no mocks).

Writes real CSV/output/candidate files under runs/. The approval and unit answers
are explicit integration-test fixtures, not approvals for external operations.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

from seed_harness import Engine, Registry, Store
from seed_harness.agent import build
from seed_harness.extensions import pipeline, load_version
from seed_harness.llm import settings
from examples.csv_demo import prepare


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def invoke_cli(db, arguments):
    completed = subprocess.run([sys.executable, '-m', 'seed_harness.cli', '--db', str(db)] + arguments,
                               check=True, capture_output=True, text=True, encoding='utf-8', timeout=300)
    return json.loads(completed.stdout)


def require(run, status):
    if run['status'] != status:
        raise RuntimeError(f"expected {status}, got {run['status']}: {run.get('error')}")


def run_checks(config_path, root, selected=None):
    config = settings(config_path)
    db = root / 'state.sqlite3'
    store = Store(db)
    report = {'base_url': config['base_url'], 'model': config['model'], 'checks': {}}

    def record(name, function):
        if selected and name not in selected:
            return
        print('START ' + name, flush=True)
        try:
            report['checks'][name] = {'status': 'pass', **function()}
        except Exception as exc:
            report['checks'][name] = {'status': 'fail', 'error': str(exc)}
        write(root / 'report.json', report)
        print(json.dumps({name: report['checks'][name]}, ensure_ascii=False), flush=True)

    def smoke():
        run = invoke_cli(db, ['job',
            'Call seven exactly once. Then ask the human for approval. After approved=true, finish with integer result 7. Do not ask again after approval.',
            '--config', str(config_path), '--registry', 'examples/llm-registry.json',
            '--completion', 'Observed seven tool result 7 and an explicit approved=true answer',
            '--verifier', 'examples.llm_tools:verify', '--json'])
        require(run, 'waiting')
        pending = run['pending']
        answer = root / 'approval.json'
        write(answer, {'approved': True})
        run = invoke_cli(db, ['resume', run['id'], '--pending-id', pending['id'], '--answer', str(answer), '--drive'])
        require(run, 'completed')
        events = store.events(run['id'])
        calls = [e for e in events if e['event'].get('tool') == 'seven']
        if len(calls) != 1 or run['result']['verification']['status'] != 'pass':
            raise RuntimeError('unexpected tool replay or verification failure')
        return {'run_id': run['id'], 'question': pending['question'], 'result': run['result'], 'tool_calls': len(calls)}

    record('cli_execute_ask_finish', smoke)

    def csv():
        csv_root, dependencies, flow = prepare(root / 'csv')
        flow['nodes']['finish']['value'] = {'$ref': 'steps.aggregate'}
        public = {'csv.pipeline': {'kind': 'workflow', 'workflow': flow,
                  'description': 'Read the prepared Japanese CSV in venv A, ask the human for its unit, aggregate in venv B and return the output file result.',
                  'input_schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}, 'output_schema': {'type': 'object'}}}
        registry, loop = build(config, public, 'seed_harness.csv_tools:verify_job')
        for name, spec in dependencies.items():
            registry.register(name, spec)
        engine = Engine(registry, store)
        run = engine.drive(engine.start(loop, {
            'goal': 'Execute csv.pipeline exactly once, then finish with its returned result object unchanged.',
            'completion': 'Output file has total=60, unit=mm, count=3 and distinct reader/aggregate venv prefixes. Ask about the input unit; never guess.'})['id'])
        require(run, 'waiting')
        question = run['pending']['question']
        engine.resume(run['id'], {'unit': 'cm'}, pending_id=run['pending']['id'])
        run = engine.drive(run['id'])
        require(run, 'completed')
        result = run['result']
        if result['verification']['status'] != 'pass':
            raise RuntimeError('CSV acceptance failed')
        return {'run_id': run['id'], 'question': question, 'result': result}

    record('csv_two_venvs', csv)

    def creation(kind):
        registry, flow = pipeline(kind)
        engine = Engine(registry, store)
        dependencies = json.loads(Path('examples/llm-registry.json').read_text(encoding='utf-8')) if kind == 'workflow' else {}
        cases = json.loads(Path('examples/seven-workflow-cases.json' if kind == 'workflow' else 'examples/sum-cases.json').read_text(encoding='utf-8'))
        input_schema = {} if kind == 'workflow' else json.loads(Path('examples/sum-input-schema.json').read_text(encoding='utf-8'))
        goal = ('Create a schema_version=1 Workflow calling seven once with input {} then returning its result. Use the chosen call node ID in the return reference.' if kind == 'workflow'
                else 'Create run(values) returning the sum of a list of finite numeric values. Empty list returns 0. Reject non-lists and invalid values. Standard library only.')
        run = engine.drive(engine.start(flow, {'request': {'goal': goal, 'tools': dependencies,
                   'input_schema': input_schema, 'output_schema': {'type': 'number'}},
                   'config': config, 'root': str(root / 'extensions'), 'name': kind + '.live.v1', 'dependencies': dependencies,
                   'input_schema': input_schema, 'output_schema': {'type': 'number'}, 'cases': cases})['id'])
        require(run, 'completed')
        adopted = load_version(run['result']['version_path'])
        parent = {'schema_version': 1, 'entry': 'call', 'nodes': {
            'call': {'kind': 'call', 'tool': kind + '.live.v1', 'input': {} if kind == 'workflow' else {'values': [4, 5]}, 'next': 'finish'},
            'finish': {'kind': 'return', 'value': {'$ref': 'steps.call'}}}}
        next_engine = Engine(adopted, store)
        next_run = next_engine.drive(next_engine.start(parent, {})['id'])
        require(next_run, 'completed')
        if next_run['result'] != (7 if kind == 'workflow' else 9):
            raise RuntimeError('published version failed independent new run')
        return {'run_id': run['id'], 'published': run['result'], 'next_run_id': next_run['id'], 'result': next_run['result']}

    record('workflow_generation', lambda: creation('workflow'))
    record('tool_generation', lambda: creation('tool'))

    def loop_creation():
        public = json.loads(Path('examples/llm-registry.json').read_text(encoding='utf-8'))
        dependencies, base = build(config, public, 'examples.llm_tools:verify_seven')
        registry, flow = pipeline('workflow')
        engine = Engine(registry, store)
        goal = 'Call seven exactly once, then finish with integer result 7 and evidence exactly the string observed seven. No approval or question is needed.'
        expected = {'result': 7, 'evidence': 'observed seven',
                    'verification': {'status': 'pass', 'checks': ['result seven', 'tool observation seven']}}
        run = engine.drive(engine.start(flow, {'request': {
            'goal': 'Modify base_workflow by adding a check_observation node after observe, before decide. '
                    'The new node calls agent.verify with state={"$ref":"vars.agent"}, '
                    'decision={"result":{"$ref":"steps.execute"},"evidence":"post-tool validation"}, '
                    'verifier="examples.llm_tools:verify_seven", and next="decide". '
                    'Change observe.next to check_observation. Preserve every other node and input unchanged, including tools_json as a JSON string. '
                    'Return the changed/new nodes for the adapter to assemble the full Workflow. Set id=agent-loop.live.v2.',
            'base_workflow': base, 'tools': dependencies.snapshot()},
            'config': config, 'root': str(root / 'extensions'), 'name': 'agent-loop.live.v2',
            'dependencies': dependencies.snapshot(), 'input_schema': {}, 'output_schema': {},
            'cases': [{'category': 'normal', 'input': {'goal': goal, 'completion': 'observed seven and evidence exactly observed seven'}, 'expected': expected}]})['id'])
        require(run, 'completed')
        adopted = load_version(run['result']['version_path'])
        parent = {'schema_version': 1, 'entry': 'loop', 'nodes': {
            'loop': {'kind': 'call', 'tool': 'agent-loop.live.v2', 'input': {'goal': goal, 'completion': 'result 7, evidence observed seven'}, 'next': 'finish'},
            'finish': {'kind': 'return', 'value': {'$ref': 'steps.loop'}}}}
        next_engine = Engine(adopted, store)
        next_run = next_engine.drive(next_engine.start(parent, {})['id'])
        require(next_run, 'completed')
        events = store.events(next_run['id'])
        verifications = [e for e in events if e['event'].get('tool') == 'agent.verify']
        if next_run['result'] != expected or len(verifications) != 2:
            raise RuntimeError('generated loop did not perform both required verifications')
        return {'run_id': run['id'], 'published': run['result'], 'next_run_id': next_run['id'],
                'verification_calls': len(verifications), 'result': next_run['result']}

    record('agent_loop_generation', loop_creation)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='harness.json')
    parser.add_argument('--output')
    parser.add_argument('--checks', nargs='+', choices=['cli_execute_ask_finish', 'csv_two_venvs', 'workflow_generation', 'tool_generation', 'agent_loop_generation'])
    args = parser.parse_args()
    root = Path(args.output or ('runs/live-' + uuid.uuid4().hex)).resolve()
    root.mkdir(parents=True, exist_ok=False)
    report = run_checks(Path(args.config).resolve(), root, args.checks)
    print('Report: ' + str(root / 'report.json'), flush=True)
    if any(c['status'] != 'pass' for c in report['checks'].values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
