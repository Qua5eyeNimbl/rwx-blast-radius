"""Precompute Selector._trace_uses for every class/module-level constant name
of the pinned source (index/source.json.gz).  The trace reads only pinned
sources, so the cached answers equal the live ones; the cache stores a hash
of the tracing code and the selector ignores it when that code changes.

  python tools/build_trace_cache.py            # writes index/trace_cache.json.gz
"""
from __future__ import annotations

import ast
import gzip
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["RWX_NO_TRACE_CACHE"] = "1"
spec = importlib.util.spec_from_file_location("selector", os.path.join(HERE, "selector.py"))
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def main():
    tests = json.load(open(os.path.join(HERE, "sample", "tests.json")))["tests"]
    sel = S.Selector(tests)
    names = set()
    for f, text in sel.index.sources().items():
        for n in ast.walk(ast.parse(text)):
            if isinstance(n, (ast.Module, ast.ClassDef)):
                for st in n.body:
                    if isinstance(st, ast.Assign):
                        names.update(t.id for t in st.targets if isinstance(t, ast.Name))
                    elif isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                        names.add(st.target.id)
    uses = {}
    for nm in sorted(names):
        for ks in (False, True):
            for er in (False, True):
                u = sel._trace_uses_live({nm}, keys_stable=ks, every_ref=er)
                uses[f"{nm}|{int(ks)}{int(er)}"] = [None if u is None else sorted(u), sel._static_ref]
    funcs = set()
    for f, text in sel.index.sources().items():
        for n in ast.walk(ast.parse(text)):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and (n.args.defaults or any(n.args.kw_defaults)):
                funcs.add(n.name)
    for nm in sorted(funcs):
        uses["call:" + nm] = [sel._call_sites_live(nm)]
    out = os.path.join(HERE, "index", "trace_cache.json.gz")
    with gzip.open(out, "wt", encoding="utf-8", compresslevel=9) as fh:
        json.dump({"code": S.trace_code_hash(), "uses": uses}, fh, separators=(",", ":"), sort_keys=True)
    print(f"{len(names)} names, {len(funcs)} functions -> {out} ({os.path.getsize(out)} bytes)", file=sys.stderr)


if __name__ == "__main__":
    main()
