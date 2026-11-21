"""Exact replay of the data-independent part of sqlglot's TPC benchmark tests.

`test_execute_tpcds` (21.5 s) parses every TPC-DS query, ships it to a worker
process (pickle), and for the 57 queries marked `execute` runs
`sqlglot.executor.execute()` -- which optimizes and plans the query and then
interprets the plan over the TPC-DS tables -- comparing the result with DuckDB
running sqlglot's DuckDB transpilation of the same query.

Splitting that test in two:
  * phase 1 (replayed here, ~2 s): `parse_one`, the pickle round trip, and
    `execute()` up to the call of `PythonExecutor.execute(plan)`, plus the
    DuckDB transpile strings;
  * phase 2 (everything else: data loading, plan interpretation, code
    generation, result shipping, comparisons).
If phase 1 yields structurally identical results on the patched tree, and no
changed statement is executed by phase 2 on the pinned tree (checked by the
selector against `index/replay_cov.json`, which is built from the pinned
commit), phase 2 starts from identical inputs and runs identical code, so the
test's outcome equals its pinned outcome (pass).  The selector only uses this
when every change is a statement inside a function body that does not run at
import time, or a class/module-level binding (or signature) whose every
reference runs after import -- those references then play the role of the
changed lines, and `state_check` proves that the patched imports changed no
other module or class attribute (`flat_state`, pinned at build time) -- or a
TPC fixture that the class setup loads for the test without using it
(`fixture_loads`).  Since v7 a changed line or a reference that runs while
importing is also accepted, under the same state check (with no names allowed
for function lines): the import may run patched code, but must leave every
other module and class attribute as pinned.  Files the test never reads
(other test modules, non-TPC fixtures) are ignored; opening one taints.

Digests are computed by walking object attributes directly, never by calling
methods of the (possibly patched) sqlglot objects.
"""

from __future__ import annotations

import enum
import functools
import hashlib
import logging
import pickle
import re
import types

PROXIES = {
    "tests/test_executor.py::TestExecutor::test_execute_tpcds": "tpcds_execute",
    "tests/test_executor.py::TestExecutor::test_execute_tpch": "tpch_execute",
    "tests/test_executor.py::TestExecutor::test_optimized_tpch": "tpch_optimized",
}

_SKIP = frozenset(("parent", "_hash", "dependents", "__weakref__"))
_ATOMS = (type(None), bool, int, float, complex, str, bytes)


class _Digest:
    """Merkle digest of an object graph: shared objects hash once, so the
    result never depends on traversal or set iteration order."""

    def __init__(self):
        self.memo = {}
        self.active = set()

    def of(self, obj) -> str:
        t = type(obj)
        if t in _ATOMS:
            return f"{t.__name__}:{obj!r}"
        if isinstance(obj, enum.Enum):
            return f"enum:{t.__module__}.{t.__qualname__}.{obj.name}"
        if isinstance(obj, (type, types.FunctionType, types.BuiltinFunctionType, types.MethodType,
                            types.ModuleType)):
            return f"ref:{getattr(obj, '__module__', '')}.{getattr(obj, '__qualname__', getattr(obj, '__name__', '?'))}"
        k = id(obj)
        d = self.memo.get(k)
        if d is not None:
            return d
        if k in self.active:
            return f"cycle:{t.__qualname__}"
        self.active.add(k)
        parts = [f"{t.__module__}.{t.__qualname__}"]
        if isinstance(obj, (list, tuple)):
            parts += [self.of(x) for x in obj]
        elif isinstance(obj, dict):
            parts += [self.of(a) + "=" + self.of(b) for a, b in obj.items()]
        elif isinstance(obj, (set, frozenset)):
            parts += sorted(self.of(x) for x in obj)
        else:
            names = []
            if hasattr(obj, "__dict__"):
                names.extend(vars(obj))
            for klass in t.__mro__:
                sl = klass.__dict__.get("__slots__", ())
                for s in (sl,) if isinstance(sl, str) else sl:
                    if s not in names:
                        names.append(s)
            for name in sorted(set(names) - _SKIP):
                try:
                    v = object.__getattribute__(obj, name)
                except AttributeError:
                    continue
                parts.append(name + "=" + self.of(v))
            # parent pointers / dependents are back references: record only
            # that they are consistent with the containing structure
            try:
                p = object.__getattribute__(obj, "parent")
                parts.append("parent=" + (f"{type(p).__qualname__}" if p is not None else "None"))
            except AttributeError:
                pass
            try:
                deps = object.__getattribute__(obj, "dependents")
                parts.append("dependents=" + ",".join(sorted(self.of(object.__getattribute__(x, "name"))
                                                            for x in deps)))
            except AttributeError:
                pass
            except Exception:
                parts.append("dependents=?")
        self.active.discard(k)
        d = hashlib.blake2b("\x1f".join(parts).encode("utf-8", "surrogatepass"), digest_size=16).hexdigest()
        self.memo[k] = d
        return d


def _digest(obj) -> str:
    return _Digest().of(obj)


# ------------------------------------------------------------ module state
_CLASS_SKIP = frozenset(("__dict__", "__weakref__", "__doc__", "__module__", "__qualname__",
                         "__firstlineno__", "__static_attributes__"))
_MOD_SKIP = frozenset(("__builtins__", "__cached__", "__file__", "__loader__", "__spec__", "__doc__",
                       "__path__"))


class _StateDigest(_Digest):
    """Digest of state an import produced.  Classes are referred to by name
    (each class attribute is its own entry of `flat_state`); a function is
    its name, signature, defaults and closure contents (its body is covered
    by line coverage, not here)."""

    def _func(self, f):
        c = f.__code__
        n = c.co_argcount + c.co_kwonlyargcount + bool(c.co_flags & 4) + bool(c.co_flags & 8)
        parts = ["fn", getattr(f, "__module__", "") or "", f.__qualname__, str(c.co_posonlyargcount),
                 str(c.co_argcount), str(c.co_kwonlyargcount), str(c.co_flags & 0x0F),
                 ",".join(c.co_varnames[:n])]
        parts.append(self.of(f.__defaults__))
        parts.append(self.of(f.__kwdefaults__))
        cells = []
        for cell in f.__closure__ or ():
            try:
                cells.append(self.of(cell.cell_contents))
            except ValueError:
                cells.append("empty")
        parts.append(",".join(cells))
        wrapped = f.__dict__.get("__wrapped__")
        if wrapped is not None:
            parts.append("wrapped=" + self.of(wrapped))
        return "\x1f".join(parts)

    def _memo(self, obj, make):
        k = id(obj)
        d = self.memo.get(k)
        if d is not None:
            return d
        if k in self.active:
            return f"cycle:{type(obj).__qualname__}"
        self.active.add(k)
        try:
            parts = make()
        finally:
            self.active.discard(k)
        d = hashlib.blake2b("\x1f".join(parts).encode("utf-8", "surrogatepass"), digest_size=16).hexdigest()
        self.memo[k] = d
        return d

    def of(self, obj):
        t = type(obj)
        if t is dict and any(type(k) not in _ATOMS for k in obj):
            # dicts keyed by classes are often built by iterating a set of
            # classes, whose order is per process (id hashing): the pinned
            # run cannot depend on it, so digest them order-insensitively
            return self._memo(obj, lambda: ["dict~"] + sorted(self.of(a) + "=" + self.of(b)
                                                             for a, b in obj.items()))
        if (t is tuple or t is list) and obj and all(isinstance(x, type) for x in obj):
            # tuple({ClassA, ClassB, ...}) for isinstance checks: the same
            # per-process order as above
            return "classes~" + ",".join(sorted(self.of(x) for x in obj))
        if t is types.MappingProxyType:
            return "proxy:" + self.of(dict(obj))
        if isinstance(obj, types.FunctionType):
            return self._func(obj)
        if isinstance(obj, (staticmethod, classmethod)):
            return t.__name__ + ":" + self.of(obj.__func__)
        if isinstance(obj, property):
            return "property:" + ",".join(self.of(f) for f in (obj.fget, obj.fset, obj.fdel))
        if isinstance(obj, functools.partial):
            return self._memo(obj, lambda: ["partial", self.of(obj.func), self.of(obj.args),
                                            self.of(obj.keywords)])
        if isinstance(obj, re.Pattern):
            return f"re:{obj.pattern!r}:{obj.flags}"
        if isinstance(obj, logging.Logger):
            # its manager holds every logger of the process (other libraries')
            return f"logger:{obj.name}:{obj.level}:{obj.propagate}:{obj.disabled}"
        return super().of(obj)


def module_names(root) -> list:
    import os

    names = []
    for d, _, files in os.walk(os.path.join(root, "sqlglot")):
        for f in files:
            if f.endswith(".py"):
                rel = os.path.relpath(os.path.join(d, f), root).replace(os.sep, "/")
                m = rel[:-3].replace("/", ".")
                names.append(m[: -len(".__init__")] if m.endswith(".__init__") else m)
    return sorted(n for n in names if not n.endswith("__main__"))


def _flat_class(D, m, cls, out, seen):
    if id(cls) in seen:
        return
    seen.add(id(cls))
    q = cls.__qualname__
    out[f"{m}:{q}"] = "class:" + ",".join(f"{b.__module__}.{b.__qualname__}" for b in (type(cls),) + cls.__bases__)
    for k, v in cls.__dict__.items():
        if k in _CLASS_SKIP:
            continue
        if isinstance(v, type) and v.__module__ == m and v.__qualname__ == f"{q}.{k}":
            _flat_class(D, m, v, out, seen)
        elif k == "__annotations__" and type(v) is dict:
            _flat_annotations(D, f"{m}:{q}", v, out)
        else:
            out[f"{m}:{q}.{k}"] = D.of(v)


def _flat_annotations(D, prefix, ann, out):
    """One entry per annotated name, so that (re)binding NAME: T = ... only
    changes an entry bound to NAME."""
    for k, v in ann.items():
        out[f"{prefix}.__annotations__#.{k}"] = D.of(v)


def flat_state(root) -> dict:
    """Import every sqlglot module in a fixed order and digest what the
    imports produced: one entry per module global and per class attribute
    ("module:Qual.name").  A module whose import raises maps "module:!"."""
    import importlib
    import sys
    import unittest  # noqa: F401  sqlglot.expressions.core records whether it is loaded;
    #                  the tests always run with it, the pinned build must too

    names = module_names(root)
    out = {}
    for m in names:
        try:
            importlib.import_module(m)
        except BaseException as e:  # noqa: BLE001
            out[m + ":!"] = f"raised:{type(e).__name__}"
    D = _StateDigest()
    for m in names:
        mod = sys.modules.get(m)
        if mod is None:
            out.setdefault(m + ":!", "missing")
            continue
        seen = set()
        for k, v in vars(mod).items():
            if k in _MOD_SKIP:
                continue
            if isinstance(v, type) and v.__module__ == m and v.__qualname__ == k:
                _flat_class(D, m, v, out, seen)
            elif k == "__annotations__" and type(v) is dict:
                _flat_annotations(D, f"{m}:", v, out)
            else:
                out[f"{m}:{k}"] = D.of(v)
    return out


def state_name(key: str) -> str:
    """The binding name an entry of flat_state is stored under."""
    return key.rsplit(":", 1)[1].rsplit(".", 1)[-1]


def state_check(expected: dict, allowed) -> tuple:
    """(True, "") when the patched imports changed only entries bound to a
    name in `allowed`; else (False, the first other entry that differs)."""
    import os

    got = flat_state(os.getcwd())
    dump = os.environ.get("RWX_STATE_DUMP")  # validation only
    if dump:
        import json

        with open(f"{dump}.{os.getpid()}.json", "w") as fh:
            json.dump(got, fh)
    for k in sorted(set(expected) | set(got)):
        if expected.get(k) != got.get(k) and (k.endswith(":!") or state_name(k) not in allowed):
            return False, k
    return True, ""


def fixture_loads(text) -> bool:
    """Whether tests.helpers.load_sql_fixture_pairs would read this fixture
    text without raising (it opens with universal newlines)."""
    try:
        from tests.helpers import _extract_meta, _filter_comments

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        statements = _filter_comments(text).split(";")
        for i in range(0, len(statements), 2):
            if i + 1 < len(statements):
                _extract_meta(statements[i].strip())
        return True
    except Exception:  # noqa: BLE001
        return False


class _Captured(Exception):
    def __init__(self, plan):
        super().__init__("captured")
        self.plan = plan


class _OverBudget(Exception):
    pass


REEXEC_SETUP_S = 1.5  # class fixtures (TPC data) before any query can be re-executed


def _phase1(kind, expected=None, forced=(), secs=None, max_s=None):
    """Phase-1 results using whatever sqlglot is importable (pinned at build
    time, patched at runtime).  Returns {"plan": {i: d}, "duck": {i: d}} for
    the execute tests (i = query position, executed queries only) and
    {"pairs": [d, ...]} for tpch_optimized.  Exceptions propagate: the test
    would raise them too."""
    from sqlglot import find_tables, parse_one, transpile
    from tests.helpers import TPCDS_SCHEMA, TPCH_SCHEMA, load_sql_fixture_pairs

    if kind == "tpch_optimized":
        pairs = []
        for _, sql, optimized in load_sql_fixture_pairs("optimizer/tpc-h/tpc-h.sql"):
            pairs.append(_digest(transpile(sql, write="duckdb")[0]))
            pairs.append(_digest(transpile(optimized, write="duckdb")[0]))
        return {"pairs": pairs}
    if kind == "tpch_execute":
        name, schema = "tpc-h", TPCH_SCHEMA
    elif kind == "tpcds_execute":
        name, schema = "tpc-ds", TPCDS_SCHEMA
    else:
        raise ValueError(kind)
    from sqlglot import executor as ex_mod
    from sqlglot.executor import python as py_mod
    from sqlglot.executor.table import Table

    sqls = list(load_sql_fixture_pairs(f"optimizer/{name}/{name}.sql"))
    real = py_mod.PythonExecutor.execute

    def capture(self, plan, outer_scope=None):
        raise _Captured(plan)

    plans, duck = {}, {}
    redo = {str(i) for i in forced}
    secs = secs or {}

    def over():
        if max_s is None or not redo:
            return False
        return REEXEC_SETUP_S + sum(secs.get(i, 1.0) for i in redo) > max_s

    if expected is not None and over():
        raise _OverBudget
    py_mod.PythonExecutor.execute = capture
    try:
        # the test parses every query in the main process and ships it to a
        # worker (pickle); the worker executes the ones marked `execute`
        for i, (meta, sql, _) in enumerate(sqls):
            expression = parse_one(sql)
            _, (expression, meta2), _ = pickle.loads(pickle.dumps((None, (expression, meta), {})))
            if not meta2.get("execute"):
                continue
            tables = {t.name: Table(columns=list(schema[t.name])) for t in find_tables(expression)}
            try:
                ex_mod.execute(expression, schema=schema, tables=tables)
                plans[str(i)] = "no-plan"
            except _Captured as c:
                plans[str(i)] = _digest(c.plan)
            duck[str(i)] = _digest(transpile(sql, write="duckdb")[0])
            if expected is not None:
                k = str(i)
                if k not in expected["plan"]:
                    raise _OverBudget  # query set changed
                if plans[k] != expected["plan"][k] or duck[k] != expected["duck"][k]:
                    redo.add(k)
                    if over():
                        raise _OverBudget
    finally:
        py_mod.PythonExecutor.execute = real
    return {"plan": plans, "duck": duck}


def _reexecute(indices) -> bool:
    """Run the TPC-DS test's own code for the given query positions only:
    class fixtures, the worker function, the result round trip and the
    test's comparison against DuckDB.  True when all of them pass."""
    import pickle as _pickle

    from tests import test_executor as te
    from tests.helpers import TPCDS_SCHEMA
    from sqlglot import parse_one

    cls = te.TestExecutor
    cls.setUpClass()
    try:
        tc = cls("test_execute_tpcds")
        te.initializer(TPCDS_SCHEMA, cls.tpcds_tables)
        for i in sorted(indices):
            meta, sql, _ = cls.tpcds_sqls[i]
            fn, args, kwargs = _pickle.loads(_pickle.dumps((te.mp_execute, (parse_one(sql), meta), {})))
            table = _pickle.loads(_pickle.dumps(fn(*args, **kwargs)))
            if table is None:
                return False  # the pinned run executed it: something changed
            tc.subtestHelper(i, table, tpch=False)  # raises on a mismatch
        return True
    finally:
        try:
            cls.tearDownClass()
        except Exception:
            pass


def check(kind, expected, forced=(), secs=None, max_reexec_s=0.0):
    """True when the proxied test is proven to pass on the importable tree.
    `forced`: query positions whose pinned phase 2 executes changed lines
    (must be re-executed).  Raises nothing; any surprise means False."""
    try:
        got = _phase1(kind, expected if kind == "tpcds_execute" else None, forced, secs, max_reexec_s)
    except _OverBudget:
        return False, "over-budget"
    except Exception:
        return False, "phase1-raised"
    if kind == "tpch_execute":
        return True, "parsed"
    if kind == "tpch_optimized":
        return got == expected, "pairs"
    if got["plan"].keys() != expected["plan"].keys():
        return False, "query-set"
    redo = {int(i) for i in got["plan"] if got["plan"][i] != expected["plan"][i]
            or got["duck"][i] != expected["duck"][i]}
    redo |= {int(i) for i in forced if str(i) in got["plan"]}
    if not redo:
        return True, "identical"
    cost = REEXEC_SETUP_S + sum((secs or {}).get(str(i), 1.0) for i in redo)
    if cost > max_reexec_s:
        return False, f"redo:{len(redo)}:{cost:.1f}s"
    try:
        ok = _reexecute(redo)
    except Exception as e:
        return False, f"reexec-raised:{type(e).__name__}"
    return ok, f"reexec:{len(redo)}"


def compute_all() -> dict:
    return {kind: _phase1(kind) for kind in sorted(set(PROXIES.values()))}


if __name__ == "__main__":  # build step: pinned digests
    import json
    import os
    import sys

    root, out = sys.argv[1], sys.argv[2]
    os.chdir(root)
    sys.path.insert(0, root)
    if len(sys.argv) > 3:  # pinned per-attribute import state
        with open(sys.argv[3], "w") as fh:
            json.dump(flat_state(root), fh, separators=(",", ":"))
    with open(out, "w") as fh:
        json.dump(compute_all(), fh)
