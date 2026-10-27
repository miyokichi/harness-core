import tempfile
import unittest
from pathlib import Path

from seed_harness.extensions import stage, test_candidate


class ExtensionLimitTests(unittest.TestCase):
    def test_dependency_rejection_and_required_independent_cases(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                stage({'code': 'import third_party\ndef run(): return 1'}, temp, 'bad.v1', 'tool', {})
            staged = stage({'code': 'def run(): return 1'}, temp, 'one.v1', 'tool', {})
            with self.assertRaises(ValueError):
                test_candidate(staged, [{'input': {}, 'expected': 1}])
            self.assertFalse((Path(temp) / 'versions').exists())

    def test_generated_code_timeout_does_not_publish(self):
        with tempfile.TemporaryDirectory() as temp:
            staged = stage({'code': 'def run():\n    while True: pass\n'}, temp, 'hang.v1', 'tool', {})
            cases = [{'category': category, 'input': {}, 'expected': 1} for category in ('normal', 'invalid', 'boundary')]
            with self.assertRaises(ValueError):
                test_candidate(staged, cases)
            self.assertFalse((Path(temp) / 'versions').exists())
