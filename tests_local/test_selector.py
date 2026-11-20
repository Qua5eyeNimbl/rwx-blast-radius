"""Unit checks for structural behavior; no lookup of sample answers."""

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from selector import Selector, parse_changed_paths, schedule

ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS = json.loads((ROOT / 'sample' / 'tests.json').read_text())['tests']


class TestSelector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selector = Selector(TESTS)

    def test_paths(self):
        text = 'diff --git a/a.py b/b.py\n--- a/a.py\n+++ b/b.py\n@@ -1 +1 @@\n-a\n+b\n'
        self.assertEqual(parse_changed_paths(text), {'a.py', 'b.py'})

    def test_fixture_resolves_test(self):
        selection = self.selector.fixture_tests('tests/fixtures/optimizer/pushdown_predicates.sql')
        ids = {self.selector.by_number[n]['id'] for n in selection}
        self.assertIn('tests/test_optimizer.py::TestOptimizer::test_pushdown_predicates', ids)

    def test_unrecognized_changes_fail_safe(self):
        self.assertEqual(self.selector.for_patch('unrecognized patch content'), self.selector.all_ids)

    def test_worker_layout(self):
        ids = {1, 2, 3, 4, 5}
        workers = schedule(ids, self.selector.by_number)
        flat = [n for worker in workers for n in worker]
        self.assertEqual(set(flat), ids)
        self.assertEqual(len(flat), len(ids))
        self.assertLessEqual(len(workers), 8)

    def test_all_sample_patches_select_valid_numbers(self):
        for patch in (ROOT / 'sample' / 'commits').glob('*.patch'):
            with self.subTest(patch=patch.name):
                selection = self.selector.for_patch(patch.read_text())
                workers = schedule(selection, self.selector.by_number)
                self.assertTrue(all(n in self.selector.all_ids for w in workers for n in w))


if __name__ == '__main__':
    unittest.main()
