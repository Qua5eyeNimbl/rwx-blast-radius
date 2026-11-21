"""Unit checks for structural behaviour; no lookup of sample answers."""

import json
import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from selector import (  # noqa: E402
    MAX_WORKERS,
    Selector,
    apply_hunks,
    diff_module,
    parse_patch,
    schedule,
)

TESTS = json.loads((ROOT / "sample" / "tests.json").read_text())["tests"]


def mkpatch(path, old_start, old_lines, new_lines, ctx_before=(), ctx_after=()):
    body = [" " + c for c in ctx_before] + ["-" + l for l in old_lines] + ["+" + l for l in new_lines] + [" " + c for c in ctx_after]
    ol = len(ctx_before) + len(old_lines) + len(ctx_after)
    nl = len(ctx_before) + len(new_lines) + len(ctx_after)
    return (f"diff --git a/{path} b/{path}\nindex 1..2 100644\n--- a/{path}\n+++ b/{path}\n"
            f"@@ -{old_start},{ol} +{old_start},{nl} @@\n" + "\n".join(body) + "\n")


class TestPatchParsing(unittest.TestCase):
    def test_paths_and_hunks(self):
        p = mkpatch("a.py", 2, ["x = 1"], ["x = 2"], ["# c"], ["y = 3"])
        (fd,) = parse_patch(p)
        self.assertEqual((fd.old, fd.new), ("a.py", "a.py"))
        self.assertEqual(len(fd.hunks), 1)
        self.assertEqual(apply_hunks("a\n# c\nx = 1\ny = 3\n", fd.hunks), "a\n# c\nx = 2\ny = 3\n")

    def test_new_and_deleted_files(self):
        new = "diff --git a/n.sql b/n.sql\nnew file mode 100644\n--- /dev/null\n+++ b/n.sql\n@@ -0,0 +1 @@\n+SELECT 1;\n"
        (fd,) = parse_patch(new)
        self.assertIsNone(fd.old)
        self.assertEqual(fd.new, "n.sql")
        dele = "diff --git a/d.sql b/d.sql\ndeleted file mode 100644\n--- a/d.sql\n+++ /dev/null\n@@ -1 +0,0 @@\n-SELECT 1;\n"
        (fd,) = parse_patch(dele)
        self.assertEqual(fd.old, "d.sql")
        self.assertIsNone(fd.new)

    def test_rename_and_no_newline_marker(self):
        p = ("diff --git a/x.sql b/y.sql\nsimilarity index 90%\nrename from x.sql\nrename to y.sql\n"
             "--- a/x.sql\n+++ b/y.sql\n@@ -1 +1 @@\n-a\n\\ No newline at end of file\n+b\n\\ No newline at end of file\n")
        (fd,) = parse_patch(p)
        self.assertEqual((fd.old, fd.new), ("x.sql", "y.sql"))

    def test_context_mismatch_raises(self):
        (fd,) = parse_patch(mkpatch("a.py", 1, ["x = 1"], ["x = 2"]))
        with self.assertRaises(ValueError):
            apply_hunks("x = 9\n", fd.hunks)

    def test_garbage_raises(self):
        with self.assertRaises(ValueError):
            parse_patch("unrecognized patch content")


class TestAstDiff(unittest.TestCase):
    BASE = "class A:\n    K = 1\n\n    def f(self, x):\n        if x:\n            return 1\n        return 2\n"

    def test_comment_only_is_no_change(self):
        new = self.BASE.replace("        if x:\n", "        # note\n        if x:\n")
        self.assertEqual(diff_module(self.BASE, new), [])

    def test_function_statement_change(self):
        new = self.BASE.replace("return 1", "return 3")
        (ch,) = diff_module(self.BASE, new)
        self.assertEqual((ch.kind, ch.unit), ("function", "A.f"))
        self.assertEqual(ch.lines, [(6, 6)])

    def test_condition_change_maps_to_header(self):
        new = self.BASE.replace("if x:", "if not x:")
        (ch,) = diff_module(self.BASE, new)
        self.assertEqual((ch.kind, ch.detail, ch.lines), ("function", "header", [(5, 5)]))

    def test_class_constant_change(self):
        (ch,) = diff_module(self.BASE, self.BASE.replace("K = 1", "K = 2"))
        self.assertEqual((ch.kind, ch.unit), ("class", "A"))

    def test_default_argument_change(self):
        base = "def f(a=1):\n    return a\n"
        (ch,) = diff_module(base, "def f(a=2):\n    return a\n")
        self.assertEqual(ch.kind, "defaults")

    def test_lambda_in_dict(self):
        base = "class P:\n    F = {\n        'A': lambda a: g(a, 0),\n    }\n"
        (ch,) = diff_module(base, base.replace("g(a, 0)", "g(a, 1)"))
        self.assertEqual((ch.kind, ch.detail), ("function", "lambda"))

    def test_is_none_equivalence(self):
        base = "def f(x):\n    if x is None:\n        return 1\n"
        self.assertEqual(diff_module(base, base.replace("is None", "== None")), [])
        self.assertNotEqual(diff_module(base, base.replace("is None", "is not None")), [])

    def test_syntax_error_raises(self):
        with self.assertRaises(SyntaxError):
            diff_module(self.BASE, self.BASE.replace("return 2", "return 2)"))


class TestSelector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selector = Selector(TESTS)

    def ids(self, nums):
        return {self.selector.by_number[n]["id"] for n in nums}

    def test_unrecognized_changes_fail_safe(self):
        self.assertEqual(self.selector.for_patch("unrecognized patch content"), self.selector.all_ids)

    def test_fixture_selects_its_reader(self):
        p = mkpatch("tests/fixtures/optimizer/pushdown_predicates.sql", 1, ["SELECT 1;"], ["SELECT 2;"])
        ids = self.ids(self.selector.for_patch(p))
        self.assertIn("tests/test_optimizer.py::TestOptimizer::test_pushdown_predicates", ids)

    def test_unknown_python_base_is_broad(self):
        p = mkpatch("sqlglot/not_a_module.py", 1, ["x = 1"], ["x = 2"])
        self.assertTrue(self.selector.for_patch(p))

    def test_class_constant_seen_by_import_time_instances(self):
        # DuckDBGenerator parses SQL templates in its class body, so a Join
        # built at import time breaks every importer of the duckdb generator
        # (all of tests/dialects via test_dialect.py) when Join's required
        # args change.  Generated holdout patch h11_021; label from the suite.
        p = """diff --git a/sqlglot/expressions/query.py b/sqlglot/expressions/query.py
index 1111111..2222222 100644
--- a/sqlglot/expressions/query.py
+++ b/sqlglot/expressions/query.py
@@ -701,7 +701,7 @@
         "method": False,
         "global_": False,
         "hint": False,
-        "match_condition": False,
+        "match_condition": True,
         "nearest": False,
         "directed": False,
         "expressions": False,
"""
        sel = self.selector.for_patch(p)
        for f in ("tests/dialects/test_mysql.py", "tests/dialects/test_dialect.py"):
            self.assertLessEqual(self.selector.by_file[f], sel, f)

    def _holdout(self, name):
        return (ROOT / "benchmarks" / "holdout" / "commits" / f"{name}.patch").read_text()

    def test_trace_cache_is_fresh(self):
        import gzip

        from selector import INDEX_DIR, trace_code_hash

        with gzip.open(INDEX_DIR / "trace_cache.json.gz", "rt", encoding="utf-8") as fh:
            blob = json.load(fh)
        self.assertEqual(blob["code"], trace_code_hash(), "rebuild: python tools/build_trace_cache.py")
        for name in ("NUMERIC_ESCAPES", "VAR_LIKE", "DASH_COMMENT_REQUIRES_BOUNDARY", "TYPE_MAPPING"):
            for ks in (False, True):
                for er in (False, True):
                    live = self.selector._trace_uses_live({name}, keys_stable=ks, every_ref=er)
                    cached = blob["uses"][f"{name}|{int(ks)}{int(er)}"][0]
                    self.assertEqual(None if live is None else sorted(map(list, live)), cached, name)
        for name in ("flatten", "func", "quote_identifier"):
            self.assertEqual(self.selector._call_sites_live(name), blob["uses"]["call:" + name][0], name)

    def test_removed_attribute_passed_at_import_breaks_importers(self):
        # Deleting the base Tokenizer flag makes Tokenizer() raise while some
        # modules import; every dialect test fails at collection (labelled
        # holdout h11_007).  The pass-through line must count as a use.
        sel = self.selector.for_patch(self._holdout("h11_007_delete"))
        self.assertLessEqual(self.selector.by_file["tests/dialects/test_duckdb.py"], sel)

    def test_constant_read_through_class_name_is_not_narrowed_to_class_users(self):
        # temporal.py reads TimeUnit.VAR_LIKE directly; DuckDB's DATE_TRUNC
        # test fails when it is removed though it builds no TimeUnit
        # (generated patch, label from the pinned suite).
        p = mkpatch("sqlglot/expressions/core.py", 2074,
                    ["    VAR_LIKE: t.ClassVar[tuple[Type[Expr], ...]] = (Column, Literal, Var)"], [],
                    [""], [""])
        ids = self.ids(self.selector.for_patch(p))
        self.assertIn("tests/dialects/test_duckdb.py::TestDuckDB::test_date_trunc", ids)

    def test_docstring_edit_selects_nothing(self):
        src = self.selector.index.sources()["sqlglot/expressions/string.py"]
        first = src.split("\n", 1)[0]
        self.assertTrue(first.startswith('"""'))
        p = mkpatch("sqlglot/expressions/string.py", 1, [first], [first.replace('"""', '"""Note: ', 1)])
        self.assertEqual(self.selector.for_patch(p), set())

    def test_dict_value_edit_ignores_membership_tests(self):
        # Dialect's metaclass only asks `"x" in NUMERIC_ESCAPES` at import;
        # a value edit is seen where escapes are decoded, by Snowflake users.
        lines = self.selector.index.sources()["sqlglot/dialects/snowflake.py"].split("\n")
        k = next(i for i, ln in enumerate(lines) if "NUMERIC_ESCAPES = {" in ln)
        p = mkpatch("sqlglot/dialects/snowflake.py", k, [lines[k]], [lines[k].replace('"u": (16', '"u": (17')],
                    [lines[k - 1]], [lines[k + 1]])
        sel = self.selector.for_patch(p)
        self.assertTrue(0 < len(sel) < 50, len(sel))

    def test_selected_numbers_are_valid(self):
        for patch in sorted((ROOT / "sample" / "commits").glob("*.patch")):
            with self.subTest(patch=patch.name):
                selection = self.selector.for_patch(patch.read_text(encoding="utf-8"))
                self.assertTrue(selection <= self.selector.all_ids)


class TestSchedule(unittest.TestCase):
    def test_worker_layout(self):
        lookup = {t["number"]: t for t in TESTS}
        for ids in ({1, 2, 3, 4, 5}, set(range(0, 1620, 3)), {1490, 1106, 1224, 5}):
            workers = schedule(ids, lookup)
            flat = [n for w in workers for n in w]
            self.assertEqual(sorted(flat), sorted(ids))
            self.assertLessEqual(len(workers), MAX_WORKERS)
            self.assertTrue(all(workers))

    def test_empty(self):
        self.assertEqual(schedule(set(), {}), [])


class TestContract(unittest.TestCase):
    def test_stdout_is_only_jsonl(self):
        env = dict(os.environ, RWX_DATA=str(ROOT / "sample"))
        env.pop("RWX_DEBUG", None)
        out = subprocess.run([sys.executable, str(ROOT / "selector.py")], env=env, capture_output=True, check=True).stdout
        self.assertFalse(out.startswith(b"\xef\xbb\xbf"))
        lines = out.decode("utf-8").split("\n")
        self.assertEqual(lines[-1], "")
        commits = sorted(p.stem for p in (ROOT / "sample" / "commits").glob("*.patch"))
        seen = []
        valid = {t["number"] for t in TESTS}
        for line in lines[:-1]:
            obj = json.loads(line)
            self.assertEqual(set(obj), {"commit", "workers"})
            nums = [n for w in obj["workers"] for n in w]
            self.assertTrue(all(type(n) is int and n in valid for n in nums))
            self.assertEqual(len(nums), len(set(nums)))
            self.assertLessEqual(len([w for w in obj["workers"] if w]), MAX_WORKERS)
            seen.append(obj["commit"])
        self.assertEqual(sorted(seen), commits)


if __name__ == "__main__":
    unittest.main()
