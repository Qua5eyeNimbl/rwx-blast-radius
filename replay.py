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
import time.

Digests are computed by walking object attributes directly, never by calling
methods of the (possibly patched) sqlglot objects.
"""

from __future__ import annotations

import enum
import hashlib
import pickle
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


class _StateDigest(_Digest):
    """Digest of what a module's import produced: its globals, and for the
    classes it defines, their bases and attributes.  A function is its name
    and default values (its body is covered by line coverage, not here)."""

    def __init__(self, module_name):
        super().__init__()
        self.module_name = module_name

    def _func(self, f):
        parts = ["fn", getattr(f, "__module__", ""), getattr(f, "__qualname__", "?")]
        parts.append(self.of(getattr(f, "__defaults__", None)))
        parts.append(self.of(getattr(f, "__kwdefaults__", None)))
        return "\x1f".join(parts)

    def of(self, obj):
        if isinstance(obj, types.FunctionType):
            return self._func(obj)
        if isinstance(obj, (staticmethod, classmethod)):
            return type(obj).__name__ + ":" + self.of(obj.__func__)
        if isinstance(obj, property):
            return "property:" + ",".join(self.of(f) for f in (obj.fget, obj.fset, obj.fdel))
        if isinstance(obj, type) and obj.__module__ == self.module_name:
            k = id(obj)
            d = self.memo.get(k)
            if d is not None:
                return d
            if k in self.active:
                return f"cycle:{obj.__qualname__}"
            self.active.add(k)
            parts = ["class", obj.__qualname__, type(obj).__qualname__]
            parts += [f"{b.__module__}.{b.__qualname__}" for b in obj.__bases__]
            for name, v in obj.__dict__.items():
                if name not in _CLASS_SKIP:
                    parts.append(name + "=" + self.of(v))
            self.active.discard(k)
            d = hashlib.blake2b("\x1f".join(parts).encode("utf-8", "surrogatepass"), digest_size=16).hexdigest()
            self.memo[k] = d
            return d
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


def import_states(names) -> dict:
    """Import the modules in this fixed order and digest each one's state.
    A module whose import raises maps to "raised:<Exception>"."""
    import importlib
    import sys

    out = {}
    for m in names:
        try:
            importlib.import_module(m)
        except BaseException as e:  # noqa: BLE001
            out[m] = f"raised:{type(e).__name__}"
    for m in names:
        if m in out:
            continue
        mod = sys.modules.get(m)
        if mod is None:
            out[m] = "missing"
            continue
        g = {k: v for k, v in vars(mod).items() if k not in ("__builtins__", "__cached__", "__file__",
                                                                "__loader__", "__spec__", "__doc__", "__path__")}
        out[m] = _StateDigest(m).of(g)
    return out


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
    with open(out, "w") as fh:
        json.dump(compute_all(), fh)
