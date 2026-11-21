"""In-container verification of candidate tests (allowed by the track rules:
"running sqlglot's tests while you decide is allowed and charged here").

For a commit whose static candidate set is cheap, a forked child applies the
patch *in memory* to the pinned sqlglot tree shipped in the image (fetched at
build time, verified against index/source.json.gz), imports the patched code
through a meta-path finder and runs the candidate tests with unittest.

Only tests the child saw PASS (or skip) are dropped from the output.  Anything
else -- failure, error, fixture error, import error, crash, timeout, memory
limit, a test that started a process (which would import the unpatched tree)
or opened a patched file as data -- keeps the test, so the verifier can only
remove tests that were actually observed to pass on the patched code.
"""

from __future__ import annotations

import os
import select
import sys
import time

SQ = os.environ.get("RWX_SQ", "/app/sq")
CHILD_RSS = int(os.environ.get("RWX_CHILD_RSS", str(1536 << 20)))  # kill a child above this
_PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


def _rss(pid) -> int:
    try:
        with open(f"/proc/{pid}/statm") as fh:
            return int(fh.read().split()[1]) * _PAGE
    except (OSError, ValueError, IndexError):
        return 0


def available() -> bool:
    return hasattr(os, "fork") and os.path.isfile(os.path.join(SQ, "sqlglot", "__init__.py")) \
        and os.environ.get("RWX_VERIFY", "1") != "0"


def module_name(rel: str) -> str:
    mod = rel[:-3].replace("/", ".")
    return mod[: -len(".__init__")] if mod.endswith(".__init__") else mod


def patched_sources(files, apply_hunks, data_ok=()) -> dict | None:
    """{rel: new_text} when every file of the patch is a modified .py file of
    the pinned tree (or a text file in `data_ok`) that the patch applies to;
    otherwise None (not eligible).  Opening any of them in the child taints."""
    out = {}
    for fd in files:
        if fd.binary or fd.old is None or fd.new is None or fd.old != fd.new:
            return None
        rel = fd.old
        if rel in data_ok:
            pass
        elif not rel.endswith(".py") or not (rel.startswith("sqlglot/") or rel.startswith("tests/")):
            return None
        path = os.path.join(SQ, rel)
        try:
            with open(path, encoding="utf-8", newline="") as fh:
                base = fh.read()
            out[rel] = apply_hunks(base, fd.hunks)
        except (OSError, ValueError, UnicodeDecodeError):
            return None
    return out or None


# ===================================================================== child
REPLAY_EXPECTED = os.environ.get("RWX_REPLAY_EXPECTED",
                                 os.path.join(os.path.dirname(os.path.abspath(__file__)), "replay_expected.json"))
STATE_EXPECTED = os.environ.get("RWX_STATE_EXPECTED",
                                os.path.join(os.path.dirname(os.path.abspath(__file__)), "state_expected.json"))


def _child(tests, patched, wfd, replays=()):
    """Runs in the forked child. Writes 'P <n>' for each test seen passing,
    then 'D' when finished. Never returns."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        for var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            os.environ[var] = "1"
        os.environ["MALLOC_ARENA_MAX"] = "2"
        try:  # a runaway child must die before the container's memory limit is hit
            with open("/proc/self/oom_score_adj", "w") as fh:
                fh.write("1000")
        except OSError:
            pass
        os.chdir(SQ)
        sys.path.insert(0, SQ)
        os.environ.pop("PYTHONPATH", None)
        import builtins
        import importlib.machinery
        import importlib.util
        import io
        import linecache
        import unittest

        abs_patched = {}
        mods = {}
        for rel, text in patched.items():
            p = os.path.join(SQ, rel)
            abs_patched[os.path.realpath(p)] = rel
            if rel.endswith(".py"):
                mods[module_name(rel)] = (p, text)
                linecache.cache[p] = (len(text), None, text.splitlines(True), p)

        class Loader(importlib.machinery.SourceFileLoader):
            def __init__(self, fullname, path, text):
                super().__init__(fullname, path)
                self.text = text

            def get_source(self, fullname):
                return self.text

            def get_code(self, fullname):
                return compile(self.text, self.path, "exec", dont_inherit=True)

        class Finder:
            @staticmethod
            def find_spec(name, path=None, target=None):
                m = mods.get(name)
                if m is None:
                    return None
                p, text = m
                return importlib.util.spec_from_file_location(name, p, loader=Loader(name, p, text))

            @staticmethod
            def invalidate_caches():
                pass

        sys.meta_path.insert(0, Finder)

        # Process pools would start workers that import the UNPATCHED tree.
        # Run their work in-process instead, with the same pickle round trips.
        import concurrent.futures
        import concurrent.futures.process
        import pickle

        class InlineExecutor(concurrent.futures.Executor):
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

        concurrent.futures.ProcessPoolExecutor = InlineExecutor
        concurrent.futures.process.ProcessPoolExecutor = InlineExecutor

        state = {"cur": None, "tainted": set(), "module_taint": False, "sticky": False}

        def taint():
            # any process started from here runs unpatched code; everything
            # after it in the same test file may talk to that process
            state["sticky"] = True
            cur = state["cur"]
            if cur is None:
                state["module_taint"] = True
            else:
                state["tainted"].add(cur)

        real_open = builtins.open

        def guarded_open(file, *a, **k):
            try:
                if isinstance(file, (str, bytes, os.PathLike)):
                    rp = os.path.realpath(os.fsdecode(file))
                    if rp in abs_patched:
                        taint()
            except Exception:
                taint()
            return real_open(file, *a, **k)

        builtins.open = guarded_open
        io.open = guarded_open
        import subprocess
        real_popen_init = subprocess.Popen.__init__

        def popen_init(self, *a, **k):
            taint()
            return real_popen_init(self, *a, **k)

        subprocess.Popen.__init__ = popen_init
        import multiprocessing.process as mpp
        real_start = mpp.BaseProcess.start

        def mp_start(self, *a, **k):
            taint()
            return real_start(self, *a, **k)

        mpp.BaseProcess.start = mp_start
        real_system = os.system

        def guarded_system(*a, **k):
            taint()
            return real_system(*a, **k)

        os.system = guarded_system
        for name in ("execv", "execve", "execvp", "execvpe", "posix_spawn", "posix_spawnp", "fork"):
            if hasattr(os, name):
                real = getattr(os, name)

                def wrap(*a, _real=real, **k):
                    taint()
                    return _real(*a, **k)

                setattr(os, name, wrap)

        out = os.fdopen(wfd, "w", buffering=1)

        class Result(unittest.TestResult):
            def __init__(self):
                super().__init__()
                self.bad = set()
                self.ran = []

            def startTest(self, test):
                super().startTest(test)
                state["cur"] = test.id()

            def stopTest(self, test):
                super().stopTest(test)
                self.ran.append(test.id())
                if state["sticky"]:
                    state["tainted"].add(test.id())
                state["cur"] = None

            def addError(self, test, err):
                super().addError(test, err)
                self.bad.add(getattr(test, "id", lambda: "?")())
                if not isinstance(test, unittest.TestCase):
                    self.bad.add("*")  # class/module fixture error
                    self.fixture_err = f"{test}:{err[0].__name__}:{str(err[1])[:200]}"

            def addFailure(self, test, err):
                super().addFailure(test, err)
                self.bad.add(test.id())

            def addSubTest(self, test, subtest, err):
                super().addSubTest(test, subtest, err)
                if err is not None:
                    self.bad.add(test.id())

            def addUnexpectedSuccess(self, test):
                super().addUnexpectedSuccess(test)
                self.bad.add(test.id())

        state_ok = {}
        for num, kind, forced, secs, max_s, *more in replays:
            try:
                import json as _json
                import replay as _replay
                allowed = more[0] if more else None
                if allowed is not None:
                    # non-function changes: the patched imports may differ
                    # from the pinned ones only in the changed bindings
                    akey = tuple(sorted(allowed))
                    if akey not in state_ok:
                        with real_open(STATE_EXPECTED, encoding="utf-8") as fh:
                            state_ok[akey] = _replay.state_check(_json.load(fh), set(akey))
                    sok, skey = state_ok[akey]
                    if not sok:
                        out.write(f"K {num} state:{skey[:120]}\n")
                        continue
                fixtures = more[1] if len(more) > 1 else ()
                if fixtures and not all(_replay.fixture_loads(patched[rel]) for rel in fixtures):
                    # a fixture only the class setup loads: it must still load
                    out.write(f"K {num} fixture-load\n")
                    continue
                with real_open(REPLAY_EXPECTED, encoding="utf-8") as fh:
                    expected = _json.load(fh)[kind]
                ok, why = _replay.check(kind, expected, forced, secs, max_s)
                if ok and not state["module_taint"] and not state["sticky"]:
                    out.write(f"P {num}\n")
                else:
                    out.write(f"K {num} replay:{why}\n")
            except BaseException as e:
                out.write(f"K {num} replay:{type(e).__name__}\n")

        # group by file, keeping catalog order
        by_file: dict[str, list] = {}
        for t in tests:
            by_file.setdefault(t["file"], []).append(t)
        for rel, ts in by_file.items():
            try:
                mod = importlib.import_module(module_name(rel))
            except BaseException as e:
                out.write(f"K {rel} import:{type(e).__name__}\n")
                continue  # import error: every test of the file fails -> keep all
            if state["module_taint"]:
                out.write(f"K {rel} module-taint\n")
                continue
            suite = unittest.TestSuite()
            want = {}
            classes: dict[str, unittest.TestSuite] = {}
            ok = True
            for t in ts:
                _, cls_name, meth = t["id"].split("::")
                cls = getattr(mod, cls_name, None)
                if cls is None or not hasattr(cls, meth):
                    ok = False
                    break
                if cls_name not in classes:
                    classes[cls_name] = unittest.TestSuite()
                    suite.addTest(classes[cls_name])
                case = cls(meth)
                classes[cls_name].addTest(case)
                want[case.id()] = t["number"]
            if not ok:
                continue
            res = Result()
            try:
                suite.run(res)
            except BaseException as e:
                out.write(f"K {rel} run:{type(e).__name__}\n")
                continue
            if "*" in res.bad or state["module_taint"] or res.shouldStop:
                why = getattr(res, "fixture_err", "").replace("\n", " ")
                out.write(f"K {rel} fixture-error {why}\n")
                continue
            for tid in res.ran:
                if tid in want and tid not in res.bad and tid not in state["tainted"]:
                    out.write(f"P {want[tid]}\n")
                elif tid in want:
                    why = "tainted" if tid in state["tainted"] else "failed"
                    out.write(f"K {want[tid]} {why}\n")
        out.write("D\n")
        out.flush()
    except BaseException as e:
        try:
            os.write(wfd, f"K child-exc {type(e).__name__}:{str(e)[:200]}\n".replace("\r", " ").encode())
        except Exception:
            pass
    finally:
        os._exit(0)


# ===================================================================== parent
def run_jobs(jobs, parallel=2, deadline=None):
    """jobs: list of (key, tests:list[dict], patched:dict, budget_s).
    Returns {key: set(test numbers observed passing)}; missing key = nothing known."""
    passed: dict = {}
    kept: dict = {}
    cpu: dict = {}
    pending = list(jobs)
    live = {}  # fd -> (key, pid, t_end, buf)
    sys.stdout.flush()
    sys.stderr.flush()
    while pending or live:
        now = time.monotonic()
        while pending and len(live) < parallel and (deadline is None or now < deadline):
            key, tests, patched, budget, *rest = pending.pop(0)
            replays = rest[0] if rest else ()
            r, w = os.pipe()
            try:
                pid = os.fork()
            except OSError:
                os.close(r)
                os.close(w)
                pending.clear()
                break
            if pid == 0:
                os.close(r)
                _child(tests, patched, w, replays)
            os.close(w)
            t_end = now + budget
            if deadline is not None:
                t_end = min(t_end, deadline + 5)
            live[r] = [key, pid, t_end, b""]
        if deadline is not None and now >= deadline:
            pending.clear()
        if not live:
            break
        timeout = max(0.0, min(v[2] for v in live.values()) - time.monotonic())
        ready, _, _ = select.select(list(live), [], [], min(timeout, 0.25))
        for fd in ready:
            chunk = os.read(fd, 65536)
            if chunk:
                live[fd][3] += chunk
                continue
            key, pid, _, buf = live.pop(fd)
            os.close(fd)
            ru = os.wait4(pid, 0)[2]
            cpu[key] = ru.ru_utime + ru.ru_stime
            lines = buf.decode("ascii", "replace").split("\n")
            passed[key] = {int(x[2:]) for x in lines if x.startswith("P ")}
            kept[key] = [x[2:] for x in lines if x.startswith("K ")] + ([] if "D" in lines else ["child-died"])
        now = time.monotonic()
        over = [fd for fd, v in live.items() if now >= v[2] or _rss(v[1]) > CHILD_RSS]
        for fd in over:
            key, pid, t_end, buf = live.pop(fd)
            why = "timeout" if now >= t_end else "memory"
            try:
                os.kill(pid, 9)
            except OSError:
                pass
            try:
                os.waitpid(pid, 0)
            except OSError:
                pass
            os.close(fd)
            # partial results: tests confirmed passing before the timeout
            lines = buf.decode("ascii", "replace").split("\n")
            passed[key] = {int(x[2:]) for x in lines if x.startswith("P ")}
            kept[key] = [x[2:] for x in lines if x.startswith("K ")] + [why]
    run_jobs.kept = kept
    run_jobs.cpu = cpu
    return passed
