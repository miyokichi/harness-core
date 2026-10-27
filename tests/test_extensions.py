import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seed_harness import Engine, Store
from seed_harness.agent import build
from seed_harness.extensions import load_version, pipeline, publish, stage, test_candidate
from seed_harness.registry import Registry


def seven():
    return 7


def acceptance():
    return {'result': 7, 'evidence': 'observed seven',
            'verification': {'status': 'pass', 'checks': ['expected seven']}}


class ExtensionTests(unittest.TestCase):
    def test_workflow_generation_test_publication_and_parent_call(self):
        with tempfile.TemporaryDirectory() as temp:
            deps = {'seven': {'kind': 'python', 'entry': 'tests.test_extensions:seven'}}
            candidate = {'schema_version': 1, 'entry': 'seven', 'nodes': {
                'seven': {'kind': 'call', 'tool': 'seven', 'next': 'finish'},
                'finish': {'kind': 'return', 'value': {'$ref': 'steps.seven'}}}}
            registry, flow = pipeline('workflow')
            store = Store(Path(temp) / 'runs.db')
            engine = Engine(registry, store)
            with patch('seed_harness.extensions.complete', return_value=candidate):
                run = engine.drive(engine.start(flow, {
                    'request': {'goal': 'Return seven using the seven tool', 'tools': deps},
                    'config': {}, 'root': temp, 'name': 'seven.flow.v1', 'dependencies': deps,
                    'input_schema': {}, 'output_schema': {'type': 'integer'},
                    'cases': [{'input': {}, 'expected': 7}]})['id'])
            self.assertEqual(run['status'], 'completed', run.get('error'))
            adopted = load_version(run['result']['version_path'])
            parent = {'schema_version': 1, 'entry': 'call', 'nodes': {
                'call': {'kind': 'call', 'tool': 'seven.flow.v1', 'next': 'finish'},
                'finish': {'kind': 'return', 'value': {'$ref': 'steps.call'}}}}
            parent_engine = Engine(adopted, store)
            self.assertEqual(parent_engine.drive(parent_engine.start(parent, {})['id'])['result'], 7)
            bad = dict(candidate, entry='missing')
            with self.assertRaises(ValueError):
                stage(bad, temp, 'bad', 'workflow', deps)
            bad = {'schema_version': 1, 'entry': 'bad', 'nodes': {'bad': {'kind': 'call', 'tool': 'unknown', 'next': 'bad'}}}
            with self.assertRaises(ValueError):
                stage(bad, temp, 'bad', 'workflow', deps)
            staged = stage(candidate, temp, 'wrong.v1', 'workflow', deps)
            with self.assertRaises(ValueError):
                test_candidate(staged, [{'input': {}, 'expected': 8}])
            with self.assertRaises(FileNotFoundError):
                publish(dict(staged, status='pass'))
            self.assertFalse((Path(temp) / 'versions' / 'wrong.v1.json').exists())

    def test_tool_generated_in_subprocess_rejection_version_and_tamper(self):
        code = 'def run(values):\n    if not isinstance(values, list):\n        raise ValueError("list required")\n    return sum(values)\n'
        cases = [{'category': 'normal', 'input': {'values': [1, 2, 3]}, 'expected': 6},
                 {'category': 'boundary', 'input': {'values': []}, 'expected': 0},
                 {'category': 'invalid', 'input': {'values': None}, 'reject': True}]
        with tempfile.TemporaryDirectory() as temp:
            registry, flow = pipeline('tool')
            engine = Engine(registry, Store(Path(temp) / 'runs.db'))
            request = {'request': 'Create a sum tool with explicit list validation', 'config': {},
                       'root': temp, 'name': 'sum.v1', 'dependencies': {}, 'input_schema': {}, 'output_schema': {}, 'cases': cases}
            with patch('seed_harness.extensions.complete', return_value={'code': code}):
                run = engine.drive(engine.start(flow, request)['id'])
            self.assertEqual(run['status'], 'completed', run.get('error'))
            registered = load_version(run['result']['version_path'])
            self.assertEqual(registered.specs['sum.v1']['kind'], 'subprocess')
            self.assertNotIn('generated', __import__('sys').modules)
            parent = {'schema_version': 1, 'entry': 'call', 'nodes': {
                'call': {'kind': 'call', 'tool': 'sum.v1', 'input': {'values': [4, 5]}, 'next': 'finish'},
                'finish': {'kind': 'return', 'value': {'$ref': 'steps.call'}}}}
            child_engine = Engine(registered, engine.store)
            self.assertEqual(child_engine.drive(child_engine.start(parent, {})['id'])['result'], 9)
            staged = stage({'code': 'def run(values):\n    return 100\n'}, temp, 'sum.bad', 'tool', {})
            with self.assertRaises(ValueError):
                test_candidate(staged, cases)
            self.assertFalse((Path(temp) / 'versions' / 'sum.bad.json').exists())
            staged = stage({'code': code}, temp, 'sum.v2', 'tool', {})
            proof = test_candidate(staged, cases)
            published = publish(proof)
            self.assertIn('sum.v1', load_version(run['result']['version_path']).specs)
            with self.assertRaises(FileExistsError):
                publish(proof)
            (Path(staged['directory']) / 'generated.py').write_text('def run(values): return 9', encoding='utf-8')
            with self.assertRaises(ValueError):
                load_version(published['version_path'])

    def test_two_agent_loops_same_kernel_and_additional_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            public = {'seven': {'kind': 'python', 'entry': 'tests.test_extensions:seven'}}
            decisions = [{'action': 'execute', 'tool': 'seven', 'arguments': {}},
                         {'action': 'finish', 'result': 7, 'evidence': 'observed seven'}]
            for checked in (False, True):
                deps, candidate = build({}, public, 'tests.test_agent:accept', checked)
                registry, creation = pipeline('workflow')
                store = Store(Path(temp) / ('creation' + str(checked) + '.db'))
                engine = Engine(registry, store)
                with patch('seed_harness.extensions.complete', return_value=candidate), patch('seed_harness.agent.complete', side_effect=decisions):
                    run = engine.drive(engine.start(creation, {
                        'request': 'Create an agent loop' + (' validating after every tool execution' if checked else ''),
                        'config': {}, 'root': temp, 'name': 'loop.v2' if checked else 'loop.v1',
                        'dependencies': deps.snapshot(), 'input_schema': {}, 'output_schema': {},
                        'cases': [{'input': {'goal': 'seven'}, 'expected': acceptance()}]})['id'])
                self.assertEqual(run['status'], 'completed', run.get('error'))
                registered = load_version(run['result']['version_path'])
                self.assertIn('loop.v2' if checked else 'loop.v1', registered.specs)
                import json
                published = json.loads(Path(run['result']['version_path']).read_text(encoding='utf-8'))
                proof = json.loads((Path(published['directory']) / 'tested.json').read_text(encoding='utf-8'))
                test_store = Store(Path(published['directory']) / 'tests.sqlite3')
                events = test_store.events(proof['run_ids'][0])
                checks = [e for e in events if e['event'].get('tool') == 'agent.verify']
                self.assertEqual(len(checks), 2 if checked else 1)
            self.assertTrue((Path(temp) / 'versions' / 'loop.v1.json').exists())
