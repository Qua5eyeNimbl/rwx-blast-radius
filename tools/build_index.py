"""Offline index builder.  Inputs come ONLY from the pinned, unmodified sqlglot
checkout (eb11aec4be8cb2122afe713a4816662c3f0fb2fa):

  * coverage.py data files from `tools/trace_suite.sh` (per-test contexts)
  * trace JSON written by `tools/rwx_trace.py` (file reads, class usage, imports)
  * the pinned source tree itself

No sample patch, answer label or edit kind is read here.

Usage:
  python tools/build_index.py SQLGLOT_ROOT TESTS_JSON OUT_DIR COVDATA... -- TRACE_JSON...
"""
from __future__ import annotations

import gzip
import importlib
import json
import os
import sys
from collections import defaultdict


def main(argv):
    root, tests_json, out_dir = argv[:3]
    rest = argv[3:]
    sep = rest.index("--")
    cov_files, trace_files = rest[:sep], rest[sep + 1:]
    root = os.path.abspath(root)

    from coverage import CoverageData

    tests = json.load(open(tests_json, encoding="utf-8"))
    ids = [t["id"] for t in tests["tests"]] + list(tests.get("skipped", []))
    tix = {tid: i for i, tid in enumerate(ids)}
    by_class = defaultdict(set)
    by_file = defaultdict(set)
    for tid, i in tix.items():
        by_class[tid.rsplit("::", 1)[0]].add(i)
        by_file[tid.split("::", 1)[0]].add(i)

    def ctx_tests(ctx):
        """Map a coverage/trace context to (kind, tests, import_module)."""
        if not ctx or ctx == "<none>":
            return "global", set(), None
        if ctx.startswith("import|"):
            return "import", set(), ctx[7:]
        if ctx.startswith("collect|"):
            return "collect", set(by_file.get(ctx[8:], ())), None
        nid, _, phase = ctx.rpartition("|")
        if nid not in tix:
            return "unknown", set(), None
        if phase in ("setup", "teardown"):
            # class/module scoped fixtures run inside the first/last test's
            # setup/teardown; every sibling depends on them.
            sib = by_class.get(nid.rsplit("::", 1)[0]) if "::" in nid else None
            return "test", set(sib or {tix[nid]}), None
        return "test", {tix[nid]}, None

    ctx_cache = {}

    def resolve(ctx):
        r = ctx_cache.get(ctx)
        if r is None:
            r = ctx_cache[ctx] = ctx_tests(ctx)
        return r

    # ---------------------------------------------------------- interning
    sets, set_ids = [], {}

    def sid(s):
        key = tuple(sorted(s))
        i = set_ids.get(key)
        if i is None:
            i = set_ids[key] = len(sets)
            sets.append(list(key))
        return i

    mods, mod_ids = [], {}

    def mid(ms):
        key = tuple(sorted(ms))
        i = mod_ids.get(key)
        if i is None:
            i = mod_ids[key] = len(mods)
            mods.append(list(key))
        return i

    # ---------------------------------------------------------- coverage
    lines = defaultdict(lambda: defaultdict(lambda: [set(), set(), False]))
    for cf in cov_files:
        cd = CoverageData(cf)
        cd.read()
        for f in cd.measured_files():
            rel = os.path.relpath(f, root).replace(os.sep, "/")
            if rel.startswith(".."):
                continue
            for ln, ctxs in cd.contexts_by_lineno(f).items():
                ent = lines[rel][ln]
                for c in ctxs:
                    kind, ts, imod = resolve(c)
                    if kind in ("test", "collect"):
                        ent[0] |= ts
                    if kind == "collect":
                        ent[2] = True
                    if imod:
                        ent[1].add(imod)
                    if kind in ("global", "unknown"):
                        ent[2] = True

    # ---------------------------------------------------------- traces
    reads = defaultdict(set)
    req_graph = defaultdict(set)   # module -> modules it requests while importing
    req_tests = defaultdict(set)   # requested module -> tests whose context requested it
    cls_tests = defaultdict(set)
    importers = defaultdict(set)
    collect_imports = defaultdict(set)  # module -> test files whose collection imported it
    for tf in trace_files:
        tr = json.load(open(tf, encoding="utf-8"))
        for ctx, rec in tr.items():
            kind, ts, imod = resolve(ctx)
            for p in rec.get("read", ()):
                if kind in ("test", "collect"):
                    reads[p] |= ts
                elif kind == "import":
                    reads[p].add(("import", imod))
            for m in rec.get("req", ()):
                if kind == "import":
                    req_graph[imod].add(m)
                elif kind in ("test", "collect"):
                    req_tests[m] |= ts
            for c in rec.get("cls", ()):
                if kind in ("test", "collect"):
                    cls_tests[c] |= ts
            if kind == "import":
                for par in rec.get("importer", ()):
                    pk, pts, pmod = resolve(par)
                    if pmod:
                        importers[imod].add(pmod)
                    if pk == "collect":
                        collect_imports[imod].add(par[8:])

    # closure(Y): every module whose import runs when Y is requested
    def parents(m):
        parts = m.split(".")
        return {".".join(parts[:i]) for i in range(1, len(parts))}

    closure_cache = {}

    def closure(y):
        if y in closure_cache:
            return closure_cache[y]
        seen, stack = set(), [y]
        while stack:
            z = stack.pop()
            if z in seen:
                continue
            seen.add(z)
            stack.extend(req_graph.get(z, ()))
            stack.extend(parents(z))
        closure_cache[y] = seen
        return seen

    requirers = defaultdict(set)
    for y, ts in req_tests.items():
        for m in closure(y):
            requirers[m] |= ts

    # resolve "read during import of M" lazily at runtime via mod users; keep
    # only plain test sets here and a list of modules per path.
    reads_out = {}
    reads_mods = {}
    for p, s in reads.items():
        plain = {x for x in s if not isinstance(x, tuple)}
        ms = {x[1] for x in s if isinstance(x, tuple)}
        reads_out[p] = sid(plain)
        if ms:
            reads_mods[p] = mid(ms)

    # class MRO expansion: a test using class C uses every sqlglot base of C
    sys.path.insert(0, root)
    cls_users = defaultdict(set)
    for c, ts in cls_tests.items():
        modname, qual = c.split(":", 1)
        try:
            obj = importlib.import_module(modname)
            for part in qual.split("."):
                obj = getattr(obj, part)
            mro = obj.__mro__
        except Exception:
            cls_users[c] |= ts
            continue
        for k in mro:
            m = getattr(k, "__module__", "") or ""
            if m.startswith("sqlglot"):
                cls_users[f"{m}:{k.__qualname__}"] |= ts

    lines_out = {}
    file_runtime = {}
    for rel, m in lines.items():
        lo = {}
        allts = set()
        for ln, (ts, ims, glob) in m.items():
            lo[str(ln)] = [sid(ts), mid(ims)]
            allts |= ts
        lines_out[rel] = lo
        file_runtime[rel] = sid(allts)

    # sources of every python file in the pinned tree (for AST comparison)
    sources = {}
    for base in ("sqlglot", "tests"):
        for dp, dn, fn in os.walk(os.path.join(root, base)):
            dn[:] = [d for d in dn if d != "__pycache__" and not (base == "tests" and d == "fixtures")]
            for f in fn:
                if f.endswith(".py"):
                    p = os.path.join(dp, f)
                    rel = os.path.relpath(p, root).replace(os.sep, "/")
                    sources[rel] = open(p, encoding="utf-8").read()

    index = {
        "sqlglot_sha": "eb11aec4be8cb2122afe713a4816662c3f0fb2fa",
        "tests": ids,
        "sets": sets,
        "mods": mods,
        "lines": lines_out,
        "file_runtime": file_runtime,
        "reads": reads_out,
        "reads_mods": reads_mods,
        "cls_users": {c: sid(s) for c, s in cls_users.items()},
        "importers": {m: sorted(v) for m, v in importers.items()},
        "collect_imports": {m: sorted(v) for m, v in collect_imports.items()},
        "requirers": {m: sid(v) for m, v in requirers.items()},
    }
    os.makedirs(out_dir, exist_ok=True)
    with gzip.open(os.path.join(out_dir, "index.json.gz"), "wt", encoding="utf-8", compresslevel=9) as fh:
        json.dump(index, fh, separators=(",", ":"))
    with gzip.open(os.path.join(out_dir, "source.json.gz"), "wt", encoding="utf-8", compresslevel=9) as fh:
        json.dump(sources, fh, separators=(",", ":"))
    print(f"sets={len(sets)} mods={len(mods)} files={len(lines_out)} reads={len(reads_out)} "
          f"classes={len(cls_users)} sources={len(sources)}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
