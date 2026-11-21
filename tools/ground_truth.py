"""Ground truth for a patch: apply it to a scratch copy of the pinned sqlglot
checkout and run the complete test suite.  Used for the local holdout only.

  python tools/ground_truth.py SQLGLOT_ROOT TESTS_JSON OUT_JSON PATCH...

Writes {patch_name: {"failing": [numbers], "status": "...", "seconds": s}}.
A failing subtest counts as a failure of its numbered parent test.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

COLLECTOR = """
import os
_f = set()
def pytest_runtest_logreport(report):
    if report.failed:
        _f.add(report.nodeid)
def pytest_collectreport(report):
    if report.failed:
        _f.add(report.nodeid)
def pytest_sessionfinish(session, exitstatus):
    with open(os.path.join(str(session.config.rootpath), "gt_failed.txt"), "w") as fh:
        fh.write("\\n".join(sorted(_f)))
"""

NODE = re.compile(r"(tests/[^\s\[:]+\.py(?:::[^\s\[:]+)*)")


def run(root, tests_json, patch_path, workers=2, timeout=900):
    tests = json.load(open(tests_json, encoding="utf-8"))
    num = {t["id"]: t["number"] for t in tests["tests"]}
    tmp = tempfile.mkdtemp(prefix="gt_")
    try:
        shutil.rmtree(tmp)
        shutil.copytree(root, tmp, ignore=shutil.ignore_patterns("__pycache__", ".git", "*.so", "build"))
        with open(os.path.join(tmp, "gt_collector.py"), "w") as fh:
            fh.write(COLLECTOR)
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        ap = subprocess.run(["git", "apply", "--whitespace=nowarn", os.path.abspath(patch_path)],
                            cwd=tmp, capture_output=True, text=True)
        if ap.returncode != 0:
            return {"status": "apply-failed", "error": ap.stderr[-500:], "failing": []}
        env = dict(os.environ, SKIP_INTEGRATION="0", PYTHONDONTWRITEBYTECODE="1")
        env.pop("PYTHONPATH", None)
        t0 = time.time()
        cmd = [sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider", "-p", "gt_collector", "-rfE",
               "--no-header", "-o", "console_output_style=classic"]
        if workers > 1:
            cmd += ["-n", str(workers)]
        try:
            pr = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True, env=env, timeout=timeout)
            outtxt = pr.stdout + pr.stderr
            status = f"exit{pr.returncode}"
        except subprocess.TimeoutExpired as e:
            outtxt = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
            status = "timeout"
        failing = set()
        unknown = set()
        rep = os.path.join(tmp, "gt_failed.txt")
        reported = open(rep).read().split("\n") if os.path.exists(rep) else []
        for nid in filter(None, reported):
            nid = nid.split("[", 1)[0] if "[" in nid.rsplit("::", 1)[-1] else nid
            if nid in num:
                failing.add(num[nid])
            elif "::" not in nid:
                hits = [t["number"] for t in tests["tests"] if t["file"] == nid]
                failing.update(hits)
                if not hits:
                    unknown.add(nid)
            else:
                unknown.add(nid)
        if os.path.exists(rep):
            outtxt = ""  # authoritative report written by the collector plugin
        for line in outtxt.splitlines():
            line = line.strip()
            if not line.startswith(("FAILED", "ERROR", "SUBFAIL")):
                continue
            m = NODE.search(line)
            if not m:
                unknown.add(line[:80])
                continue
            nid = m.group(1)
            if nid in num:
                failing.add(num[nid])
            elif "::" not in nid:
                # collection error of a whole module: every test in that file fails
                hits = [t["number"] for t in tests["tests"] if t["file"] == nid]
                failing.update(hits)
                if not hits:
                    unknown.add(nid)
            else:
                unknown.add(nid)
        if status == "exit2" or "errors during collection" in outtxt or "INTERNALERROR" in outtxt:
            status += "+collection"
        return {"status": status, "failing": sorted(failing), "unknown": sorted(unknown),
                "seconds": round(time.time() - t0, 1), "tail": outtxt[-1500:] if not failing and status != "exit0" else ""}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv):
    root, tests_json, out_json, *patches = argv
    res = json.load(open(out_json)) if os.path.exists(out_json) else {}
    for p in patches:
        name = os.path.basename(p).rsplit(".", 1)[0]
        if name in res:
            continue
        r = run(root, tests_json, p, workers=int(os.environ.get("GT_WORKERS", "1")),
                timeout=int(os.environ.get("GT_TIMEOUT", "900")))
        res[name] = r
        print(name, r["status"], len(r["failing"]), r.get("seconds"), file=sys.stderr, flush=True)
        with open(out_json + ".tmp", "w") as fh:
            json.dump(res, fh)
        os.replace(out_json + ".tmp", out_json)


if __name__ == "__main__":
    main(sys.argv[1:])
