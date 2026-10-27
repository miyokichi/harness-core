"""Candidate generation, independent tests and immutable version publication.

Generated Python runs in a timed subprocess, NOT a security sandbox. Use only
under the control of the local user. No automatic dependency installation.
"""
import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid

from .engine import Engine
from .llm import complete
from .registry import Registry, check, validate_flow
from .store import Store
from .values import dumps


def generate(request, kind, config):
    if kind not in {'workflow', 'tool'}:
        raise ValueError('kind must be workflow or tool')
    schema = {'type': 'object'} if kind == 'workflow' else {
        'type': 'object', 'properties': {'code': {'type': 'string'}}, 'required': ['code'], 'additionalProperties': False}
    instruction = ('Return a schema_version=1 Workflow with call/branch/wait/return nodes. Use only supplied tools.'
                   if kind == 'workflow' else 'Return JSON with code defining run(**keyword_arguments). Use standard library only. No tests or package installation.')
    return complete(config, [{'role': 'system', 'content': instruction},
                             {'role': 'user', 'content': dumps(request)}], schema)


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write(path, value):
    with Path(path).open('x', encoding='utf-8') as target:
        target.write(dumps(value))


def _digest(directory):
    root = Path(directory)
    data = (root / 'candidate.json').read_bytes()
    if (root / 'generated.py').exists():
        data += (root / 'generated.py').read_bytes()
    return hashlib.sha256(data).hexdigest()


def stage(candidate, root, name, kind, dependencies, input_schema=None, output_schema=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*', name):
        raise ValueError('explicit safe version name required')
    if kind not in {'workflow', 'tool'}:
        raise ValueError('unknown candidate kind')
    dependencies = Registry(dependencies).snapshot()
    if name in dependencies:
        raise ValueError('candidate version already registered')
    if kind == 'workflow':
        validate_flow(candidate)
        for node in candidate['nodes'].values():
            if node['kind'] != 'call':
                continue
            if isinstance(node['tool'], str):
                if node['tool'] not in dependencies:
                    raise ValueError('unregistered tool in candidate')
            else:
                # Agent loops use the validated decision's dynamic tool selection.
                # Other arbitrary dynamic call sites cannot be checked statically.
                decision = candidate['nodes'].get('decide', {})
                trusted = dependencies.get(decision.get('tool', ''), {})
                public = decision.get('input', {}).get('tools', {})
                if (node['tool'] != {'$ref': 'steps.decide.tool'}
                        or node.get('input') != {'$ref': 'steps.decide.arguments'}
                        or trusted.get('entry') != 'seed_harness.agent:decide'
                        or trusted.get('kind') != 'python'
                        or not isinstance(public, dict)
                        or any(k.startswith('agent.') or k not in dependencies or dependencies[k] != v for k, v in public.items())):
                    raise ValueError('dynamic candidate calls require the trusted public-tool decision gate')
        spec = {'kind': 'workflow', 'workflow': candidate}
    else:
        code = candidate['code']
        tree = ast.parse(code)
        for node in ast.walk(tree):
            modules = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                       else [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
            if any(module.split('.')[0] not in sys.stdlib_module_names or module == 'seed_harness' for module in modules):
                raise ValueError('only standard library imports are supported')
        if not any(isinstance(n, ast.FunctionDef) and n.name == 'run' for n in tree.body):
            raise ValueError('generated tool must define run')
        spec = {'kind': 'subprocess', 'python': sys.executable, 'entry': 'generated:run', 'timeout': 5}
    # Never replace a candidate or previously published source file.
    directory = Path(root).resolve() / 'candidates' / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    if kind == 'tool':
        (directory / 'generated.py').write_text(code, encoding='utf-8')
        spec['cwd'] = str(directory)
    spec.update(input_schema=input_schema or {}, output_schema=output_schema or {})
    Registry({name: spec})
    _write(directory / 'candidate.json', {'name': name, 'kind': kind, 'spec': spec, 'dependencies': dependencies})
    return {'directory': str(directory), 'root': str(Path(root).resolve()), 'digest': _digest(directory)}


def test_candidate(staged, cases):
    directory = Path(staged['directory'])
    if _digest(directory) != staged['digest']:
        raise ValueError('candidate changed before testing')
    manifest = _read(directory / 'candidate.json')
    if not cases:
        raise ValueError('caller-supplied acceptance tests required')
    if manifest['kind'] == 'tool' and not {'normal', 'invalid', 'boundary'} <= {c.get('category') for c in cases}:
        raise ValueError('tool tests require independent normal, invalid and boundary cases')
    registry = Registry(manifest['dependencies'])
    registry.register(manifest['name'], manifest['spec'])
    store = Store(directory / 'tests.sqlite3')
    engine = Engine(registry, store)
    run_ids = []
    for case in cases:
        flow = {'schema_version': 1, 'entry': 'call', 'nodes': {
            'call': {'kind': 'call', 'tool': manifest['name'], 'input': case['input'], 'next': 'finish'},
            'finish': {'kind': 'return', 'value': {'$ref': 'steps.call'}}}}
        run = engine.drive(engine.start(flow, {}, max_steps=100)['id'])
        run_ids.append(run['id'])
        if case.get('reject', False):
            passed = run['status'] == 'failed'
        else:
            passed = run['status'] == 'completed' and run['result'] == case['expected']
        if not passed:
            raise ValueError('candidate failed independent acceptance case: ' + case.get('category', 'normal'))
    if _digest(directory) != staged['digest']:
        raise ValueError('candidate changed during testing')
    proof = dict(staged, status='pass', run_ids=run_ids, cases=cases)
    _write(directory / 'tested.json', proof)
    return proof


def publish(tested):
    directory = Path(tested['directory'])
    proof = _read(directory / 'tested.json')
    if proof != tested or proof['status'] != 'pass' or _digest(directory) != proof['digest']:
        raise ValueError('publication requires unchanged tested candidate')
    manifest = _read(directory / 'candidate.json')
    catalog = Path(tested['root']) / 'versions'
    catalog.mkdir(parents=True, exist_ok=True)
    target = catalog / (manifest['name'] + '.json')
    _write(target, {'manifest': manifest, 'directory': str(directory), 'digest': tested['digest']})
    return {'name': manifest['name'], 'version_path': str(target), 'status': 'pass'}


def load_version(path):
    value = _read(path)
    if _digest(value['directory']) != value['digest']:
        raise ValueError('published source has changed')
    manifest = value['manifest']
    registry = Registry(manifest['dependencies'])
    registry.register(manifest['name'], manifest['spec'])
    return registry


def pipeline(kind):
    """Same ordinary Workflow for business flows, tools, and agent-loop versions."""
    registry = Registry({f'extension.{name}': {'kind': 'python', 'entry': 'seed_harness.extensions:' + name}
                         for name in ('generate', 'stage', 'test_candidate', 'publish')})
    ref = lambda p: {'$ref': p}
    flow = {'schema_version': 1, 'id': kind + '-creation.v1', 'entry': 'generate', 'nodes': {
        'generate': {'kind': 'call', 'tool': 'extension.generate', 'input': {
            'request': ref('input.request'), 'kind': kind, 'config': ref('input.config')}, 'next': 'stage'},
        'stage': {'kind': 'call', 'tool': 'extension.stage', 'input': {
            'candidate': ref('steps.generate'), 'root': ref('input.root'), 'name': ref('input.name'), 'kind': kind,
            'dependencies': ref('input.dependencies'), 'input_schema': ref('input.input_schema'), 'output_schema': ref('input.output_schema')}, 'next': 'test'},
        'test': {'kind': 'call', 'tool': 'extension.test_candidate', 'input': {'staged': ref('steps.stage'), 'cases': ref('input.cases')}, 'next': 'publish'},
        'publish': {'kind': 'call', 'tool': 'extension.publish', 'input': {'tested': ref('steps.test')}, 'next': 'finish'},
        'finish': {'kind': 'return', 'value': ref('steps.publish')}}}
    return registry, flow
