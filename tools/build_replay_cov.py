"""Phase-2 coverage of the replay-proxied tests, from the PINNED tree only.

  python tools/build_replay_cov.py SQLGLOT_ROOT OUT_JSON

For each test in replay.PROXIES, runs it (with its class fixtures) in a fresh
process and records every sqlglot line executed while NOT inside one of the
calls the replay reproduces (parse_one / transpile in the test module,
optimize / Plan inside sqlglot.executor.execute).  Process pools run
in-process with pickle round trips, as in the verifier, so worker code is
recorded too.  Output: {test_id: {rel_path: [line, ...]}}.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

CHILD = r'''
import concurrent.futures, concurrent.futures.process, json, os, pickle, sys, unittest
root, test_id, out = sys.argv[1], sys.argv[2], sys.argv[3]
os.chdir(root); sys.path.insert(0, root)

STATE = {"n": 0, "cur": None}
SECS = {}
class InlineExecutor(concurrent.futures.Executor):
    def __init__(self, max_workers=None, mp_context=None, initializer=None, initargs=(), **k):
        if initializer is not None:
            init, args = pickle.loads(pickle.dumps((initializer, initargs)))
            init(*args)
    def submit(self, fn, /, *args, **kwargs):
        fut = concurrent.futures.Future()
        q = STATE["n"]
        STATE["n"] += 1
        STATE["cur"] = q
        sys.monitoring.restart_events()
        import time
        t0 = time.process_time()
        try:
            fn2, a2, k2 = pickle.loads(pickle.dumps((fn, args, kwargs)))
            fut.set_result(pickle.loads(pickle.dumps(fn2(*a2, **k2))))
        except BaseException as e:
            fut.set_exception(e)
        SECS[q] = round(time.process_time() - t0, 4)
        STATE["cur"] = None
        sys.monitoring.restart_events()
        return fut
    def shutdown(self, wait=True, *, cancel_futures=False):
        pass
concurrent.futures.ProcessPoolExecutor = InlineExecutor
concurrent.futures.process.ProcessPoolExecutor = InlineExecutor

import importlib
rel, cls_name, meth = test_id.split("::")
mod = importlib.import_module(rel[:-3].replace("/", "."))
import sqlglot.executor as ex
depth = [0]
def wrap(f):
    def w(*a, **k):
        depth[0] += 1
        try:
            return f(*a, **k)
        finally:
            depth[0] -= 1
    return w
for name in ("parse_one", "transpile"):
    if hasattr(mod, name):
        setattr(mod, name, wrap(getattr(mod, name)))
ex.optimize = wrap(ex.optimize)
ex.Plan = wrap(ex.Plan)

M = sys.monitoring
TOOL = 4
M.use_tool_id(TOOL, "rwx-replay-cov")
prefix = os.path.join(root, "sqlglot") + os.sep
lines = {}
per = {}
def on_line(code, line):
    if depth[0] == 0:
        f = code.co_filename
        if f.startswith(prefix):
            q = STATE["cur"]
            tgt = lines if q is None else per.setdefault(q, {})
            tgt.setdefault(os.path.relpath(f, root).replace(os.sep, "/"), set()).add(line)
        return M.DISABLE
M.register_callback(TOOL, M.events.LINE, on_line)
M.set_events(TOOL, M.events.LINE)
res = unittest.TestResult()
unittest.TestSuite([unittest.TestSuite([getattr(mod, cls_name)(meth)])]).run(res)
M.set_events(TOOL, 0)
assert not res.errors and not res.failures, (res.errors, res.failures)
assert depth[0] == 0
json.dump({"shared": {k: sorted(v) for k, v in lines.items()},
           "per": {str(q): {k: sorted(v) for k, v in d.items()} for q, d in per.items()},
           "secs": {str(q): t for q, t in SECS.items()}}, open(out, "w"))
'''


def main(root, out_json):
    sys.path.insert(0, REPO)
    import replay
    result = {}
    for test_id in sorted(replay.PROXIES):
        tmp = out_json + ".part"
        env = dict(os.environ, SKIP_INTEGRATION="0", PYTHONDONTWRITEBYTECODE="1")
        subprocess.run([sys.executable, "-c", CHILD, root, test_id, tmp], check=True, env=env)
        with open(tmp) as fh:
            result[test_id] = json.load(fh)
        os.remove(tmp)
        r = result[test_id]
        n = sum(len(v) for v in r["shared"].values())
        print(test_id, n, "shared phase-2 lines,", len(r["per"]), "submissions,",
              round(sum(r["secs"].values()), 2), "s in workers", file=sys.stderr)
    with open(out_json, "w") as fh:
        json.dump(result, fh, separators=(",", ":"))


if __name__ == "__main__":
    main(*sys.argv[1:])
