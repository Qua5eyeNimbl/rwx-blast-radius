"""Unit checks for the replay helpers that need no sqlglot tree."""

import ast
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import replay  # noqa: E402
from selector import Change, _bound_names, replay_ignorable  # noqa: E402


def _ch(old_src, new_src, kind="class"):
    a = ast.parse(old_src).body[0] if old_src else None
    b = ast.parse(new_src).body[0] if new_src else None
    ch = Change(kind, "C", [(1, 1)], "stmt", node=a)
    ch.new_node = b
    return ch


class TestBoundNames(unittest.TestCase):
    def test_plain_and_annotated_bindings(self):
        self.assertEqual(_bound_names(_ch("X = 1", "X = 2")), {"X"})
        self.assertEqual(_bound_names(_ch("X: bool = False", None)), {"X"})
        self.assertEqual(_bound_names(_ch(None, "Y = (1, 2)")), {"Y"})

    def test_unsupported_statements(self):
        self.assertIsNone(_bound_names(_ch("a.b = 1", "a.b = 2")))
        self.assertIsNone(_bound_names(_ch("x, y = 1, 2", "x, y = 2, 1")))
        self.assertIsNone(_bound_names(_ch("f(1)", "f(2)")))

    def test_dispatched_and_protocol_names_are_refused(self):
        self.assertIsNone(_bound_names(_ch("select_sql = other_sql", "select_sql = third_sql")))
        self.assertIsNone(_bound_names(_ch("__slots__ = ()", "__slots__ = ('a',)")))


class TestReplayScope(unittest.TestCase):
    def test_ignorable_files(self):
        self.assertTrue(replay_ignorable("tests/fixtures/optimizer/simplify.sql"))
        self.assertTrue(replay_ignorable("tests/test_optimizer.py"))
        self.assertFalse(replay_ignorable("tests/fixtures/optimizer/tpc-ds/tpc-ds.sql"))
        self.assertFalse(replay_ignorable("tests/fixtures/optimizer/tpc-h/customer.csv.gz"))
        self.assertFalse(replay_ignorable("tests/test_executor.py"))
        self.assertFalse(replay_ignorable("tests/helpers.py"))
        self.assertFalse(replay_ignorable("tests/__init__.py"))
        self.assertFalse(replay_ignorable("sqlglot/optimizer/simplify.py"))
        self.assertFalse(replay_ignorable("setup.py"))

    def test_inserted_statements_bind_their_names(self):
        ch = _ch(None, None, kind="module")
        ch.new_nodes = tuple(ast.parse("from a.b import c as d\nimport e.f\ndef g(): pass").body)
        self.assertEqual(_bound_names(ch), {"d", "e", "g"})
        ch.new_nodes = tuple(ast.parse("from a import *").body)
        self.assertIsNone(_bound_names(ch))
        ch.new_nodes = tuple(ast.parse("REG['x'] = 1").body)
        self.assertIsNone(_bound_names(ch))


class TestStateDigest(unittest.TestCase):
    def test_state_name(self):
        self.assertEqual(replay.state_name("sqlglot.generator:Generator.STAR_EXCEPT"), "STAR_EXCEPT")
        self.assertEqual(replay.state_name("sqlglot.x:NAME"), "NAME")
        self.assertEqual(replay.state_name("sqlglot.x:C.__annotations__#.FLAG"), "FLAG")

    def test_class_collections_ignore_order(self):
        A = type("A", (), {})
        B = type("B", (), {})
        d = replay._StateDigest()
        self.assertEqual(d.of((A, B)), replay._StateDigest().of((B, A)))
        self.assertEqual(d.of({A: 1, B: 2}), replay._StateDigest().of({B: 2, A: 1}))
        self.assertNotEqual(d.of({A: 1, B: 2}), replay._StateDigest().of({A: 2, B: 1}))

    def test_function_closure_and_signature_count(self):
        def make(v):
            def f(x, y=1):
                return v
            return f
        d = replay._StateDigest
        self.assertNotEqual(d().of(make(1)), d().of(make(2)))
        g = types.FunctionType(make(1).__code__, {}, "f", (2,), make(1).__closure__)
        self.assertNotEqual(d().of(make(1)), d().of(g))


if __name__ == "__main__":
    unittest.main()
