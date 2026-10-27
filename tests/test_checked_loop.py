import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seed_harness import Engine, Store
from seed_harness.agent import build


def wrong():
    return 8


class CheckedLoopTests(unittest.TestCase):
    def test_failed_post_tool_validation_stops_before_next_decision(self):
        with tempfile.TemporaryDirectory() as temp:
            public = {'wrong': {'kind': 'python', 'entry': 'tests.test_checked_loop:wrong'}}
            registry, flow = build({}, public, 'tests.test_agent:accept', checked=True)
            engine = Engine(registry, Store(Path(temp) / 'runs.db'))
            old = engine.start(flow, {'goal': 'seven'})
            with patch('seed_harness.agent.complete', return_value={'action': 'execute', 'tool': 'wrong', 'arguments': {}}) as model:
                run = engine.drive(old['id'])
            self.assertEqual(run['status'], 'failed')
            self.assertEqual(run['error']['node'], 'check_observation')
            self.assertEqual(model.call_count, 1)
            self.assertEqual(old['tools'], engine.store.load(old['id'])['tools'])
