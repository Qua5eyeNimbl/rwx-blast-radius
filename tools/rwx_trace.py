"""pytest plugin used ONLY in the offline index build (never in the judge image).

Runs under `coverage run` against the pinned, unmodified sqlglot checkout and
records, per test node id:
  * coverage dynamic contexts:  <nodeid>|setup / |run / |teardown
  * import-time execution:      import|<module>   (nested imports stack)
  * test-module collection:     collect|<path>
  * files opened / globbed / listed (fixtures and other data files)
  * sqlglot classes instantiated (Dialect/Tokenizer/Parser/Generator/Expr MRO)

ProcessPoolExecutor is replaced by an in-process executor that pickles the
call and the result, so work the test suite normally ships to spawned workers
is measured in the context of the test that submitted it.
"""
from __future__ import annotations

import concurrent.futures
import importlib.abc
import importlib.machinery
import json
import os
import pickle
import sys

import coverage

ROOT = os.path.abspath(os.environ.get("RWX_SQLGLOT_ROOT", os.getcwd()))
OUT = os.environ.get("RWX_TRACE_OUT", "trace.json")

_cov = coverage.Coverage.current()
_stack = [""]
_current_test = [None]
_records: dict[str, dict[str, set]] = {}


def _switch(ctx: str) -> None:
    if _cov is not None:
        _cov.switch_context(ctx)


def _push(ctx: str) -> None:
    _stack.append(ctx)
    _switch(ctx)


def _pop() -> None:
    _stack.pop()
    _switch(_stack[-1])


def _rec(kind: str, value: str) -> None:
    key = _stack[-1] if _stack[-1] else "<none>"
    _records.setdefault(key, {}).setdefault(kind, set()).add(value)


# ---------------------------------------------------------------- imports
class _ImportTagger(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if not (name == "sqlglot" or name.startswith("sqlglot.") or name == "tests" or name.startswith("tests.")):
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is None or spec.loader is None or not hasattr(spec.loader, "exec_module"):
            return spec
        orig = spec.loader.exec_module

        def exec_module(module, _orig=orig, _name=name):
            parent = _stack[-1]
            _push(f"import|{_name}")
            _rec("importer", parent)
            try:
                _orig(module)
            finally:
                _pop()

        spec.loader.exec_module = exec_module
        return spec


sys.meta_path.insert(0, _ImportTagger())

# Record every import *request* (also of already-cached modules): if a module
# raises at import, every requester fails, not only the first importer.
import builtins  # noqa: E402
import importlib  # noqa: E402

_orig_import = builtins.__import__


def _resolve(name, globals_, level):
    if level and globals_:
        pkg = globals_.get("__package__") or ""
        parts = pkg.split(".")
        base = ".".join(parts[: len(parts) - level + 1]) if level <= len(parts) else ""
        return f"{base}.{name}" if name else base
    return name


def _tracked(n):
    return n == "sqlglot" or n.startswith(("sqlglot.", "tests"))


def _import(name, globals=None, locals=None, fromlist=(), level=0):
    mod = _orig_import(name, globals, locals, fromlist, level)
    try:
        full = _resolve(name, globals, level)
        if _tracked(full):
            _rec("req", full)
            for f in fromlist or ():
                sub = f"{full}.{f}"
                if sub in sys.modules:
                    _rec("req", sub)
    except Exception:
        pass
    return mod


builtins.__import__ = _import
_orig_import_module = importlib.import_module


def _import_module(name, package=None):
    mod = _orig_import_module(name, package)
    try:
        if _tracked(mod.__name__):
            _rec("req", mod.__name__)
    except Exception:
        pass
    return mod


importlib.import_module = _import_module


# ---------------------------------------------------------------- file reads
def _audit(event, args):
    if event == "open":
        p = args[0]
        if isinstance(p, int):
            return
        try:
            p = os.fsdecode(p)
        except Exception:
            return
    elif event in ("os.listdir", "os.scandir", "glob.glob"):
        p = args[0]
        if p is None or isinstance(p, int):
            return
        try:
            p = os.fsdecode(p)
        except Exception:
            return
    else:
        return
    ap = os.path.abspath(p)
    if not ap.startswith(ROOT + os.sep):
        return
    rel = os.path.relpath(ap, ROOT)
    if rel.endswith((".pyc",)) or "__pycache__" in rel or rel.startswith((".git", ".pytest_cache")):
        return
    _rec("read", rel.replace(os.sep, "/"))


sys.addaudithook(_audit)


# ---------------------------------------------------------------- executor
class _InlineExecutor(concurrent.futures.Executor):
    def __init__(self, max_workers=None, mp_context=None, initializer=None, initargs=(), **k):
        if initializer is not None:
            init, args = pickle.loads(pickle.dumps((initializer, initargs)))
            init(*args)

    def submit(self, fn, /, *args, **kwargs):
        fut = concurrent.futures.Future()
        try:
            fn2, args2, kwargs2 = pickle.loads(pickle.dumps((fn, args, kwargs)))
            res = fn2(*args2, **kwargs2)
            fut.set_result(pickle.loads(pickle.dumps(res)))
        except BaseException as e:  # noqa: BLE001
            fut.set_exception(e)
        return fut

    def shutdown(self, wait=True, *, cancel_futures=False):
        pass


concurrent.futures.ProcessPoolExecutor = _InlineExecutor


# ---------------------------------------------------------------- classes
def _wrap_init(cls):
    orig = cls.__init__

    def __init__(self, *a, **k):
        _rec("cls", f"{type(self).__module__}:{type(self).__qualname__}")
        return orig(self, *a, **k)

    __init__.__wrapped__ = orig
    cls.__init__ = __init__


def _install_class_tracing():
    from sqlglot import generator, parser, tokens
    from sqlglot.dialects import dialect
    from sqlglot.expressions import core

    for c in (dialect.Dialect, tokens.Tokenizer, parser.Parser, generator.Generator, core.Expr):
        _wrap_init(c)
    orig = dialect.Dialect.get_or_raise.__func__

    def get_or_raise(cls, *a, **k):
        r = orig(cls, *a, **k)
        _rec("cls", f"{type(r).__module__}:{type(r).__qualname__}")
        return r

    dialect.Dialect.get_or_raise = classmethod(get_or_raise)


# ---------------------------------------------------------------- pytest hooks
import pytest  # noqa: E402


def pytest_configure(config):
    _install_class_tracing()


@pytest.hookimpl(hookwrapper=True)
def pytest_make_collect_report(collector):
    path = getattr(collector, "path", None)
    tag = None
    if isinstance(collector, pytest.Module) and path is not None:
        tag = "collect|" + os.path.relpath(str(path), ROOT).replace(os.sep, "/")
        _push(tag)
    try:
        yield
    finally:
        if tag:
            _pop()


def _phase(item, phase):
    _push(f"{item.nodeid}|{phase}")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    _phase(item, "setup")
    try:
        yield
    finally:
        _pop()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    _phase(item, "run")
    try:
        yield
    finally:
        _pop()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):
    _phase(item, "teardown")
    try:
        yield
    finally:
        _pop()


def pytest_sessionfinish(session, exitstatus):
    out = {k: {kk: sorted(vv) for kk, vv in v.items()} for k, v in _records.items()}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
