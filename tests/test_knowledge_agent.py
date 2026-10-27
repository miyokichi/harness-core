import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from seed_harness import knowledge
from seed_harness.agent import decide, learn


class KnowledgeAgentTests(unittest.TestCase):
    def test_missing_reuse_outside_conflict_and_hypothesis(self):
        with tempfile.TemporaryDirectory() as temp:
            req = {'database': str(Path(temp) / 'knowledge.db'), 'scope': 'measurements:sourceA', 'key': 'unit'}
            state = {'request': {'knowledge': [req]}, 'answers': []}
            self.assertEqual(decide(state, {}, {})['action'], 'ask')
            answer = {'knowledge': {'scope': req['scope'], 'key': 'unit', 'value': 'cm'}}
            state = learn(state, answer)
            self.assertEqual(knowledge.assess(**req)['status'], 'pass')
            with patch('seed_harness.agent.complete', return_value={'action': 'finish', 'result': 60, 'evidence': 'verified'}):
                self.assertEqual(decide(state, {}, {})['action'], 'finish')
            outside = dict(req, scope='measurements:sourceB')
            self.assertEqual(knowledge.assess(**outside)['status'], 'unknown')
            with self.assertRaises(ValueError):
                learn(state, {'knowledge': dict(answer['knowledge'], value='mm')})
            self.assertEqual(knowledge.lookup(**req)['record']['value'], 'cm')
            knowledge.remember(**outside, value='mm', source={'kind': 'hypothesis', 'reference': 'model'})
            self.assertEqual(knowledge.assess(**outside)['status'], 'unknown')
            exception = dict(req, scope='exception')
            knowledge.remember(**exception, value='cm', source={'kind': 'human', 'reference': 'answer'}, exceptions=['special case'])
            self.assertEqual(knowledge.assess(**exception)['status'], 'unknown')
