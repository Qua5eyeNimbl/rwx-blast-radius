"""Targeted holdout patches for v4's narrowing rules, from the pinned source only.

Candidates (all inside class bodies of sqlglot/*.py):
  dictval  - one literal inside a value of a dict-literal class attribute flipped
             (keys unchanged)
  delattr  - a one-line `NAME = <call-free value>` class attribute removed
  insattr  - a bool flag of a base class (Dialect/Tokenizer/Parser/Generator)
             overridden with the opposite value in a subclass that does not set it
  docstr   - a word inserted into a module/class/function docstring

Only candidates where the new selector and a reference selector disagree are
kept (the others say nothing about the new rules); a seeded sample is written.
Nothing comes from the sample patches or their answers.

  python tools/target_mutants.py NEW_SELECTOR.py REF_SELECTOR.py TESTS_JSON OUT_DIR PER_KIND SEED
"""
from __future__ import annotations

import ast
import difflib
import gzip
import importlib.util
import json
import os
import random
import sys


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def patch_text(rel, old, new):
    body = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        "a/" + rel, "b/" + rel, n=3))
    return f"diff --git a/{rel} b/{rel}\nindex 1111111..2222222 100644\n" + body


def classes(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef):
            yield n


def target_name(st):
    if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
        return st.targets[0].id
    if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name) and st.value is not None:
        return st.target.id
    return None


def flip_const(c, line):
    seg = line[c.col_offset:c.end_col_offset]
    v = c.value
    if isinstance(v, bool):
        rep = "False" if v else "True"
    elif isinstance(v, int):
        rep = str(v + 1)
    elif isinstance(v, str) and seg[:1] in "\"'" and len(v) > 0:
        rep = seg[0] + v + "q" + seg[0]
    else:
        return None
    return line[:c.col_offset] + rep + line[c.end_col_offset:]


BASES = {
    ("sqlglot/dialects/dialect.py", "Dialect"): "dialect",
    ("sqlglot/tokens.py", "Tokenizer"): "tokenizer",
    ("sqlglot/parser.py", "Parser"): "parser",
    ("sqlglot/generator.py", "Generator"): "generator",
}


def main():
    new_sel, ref_sel, tests_json, out_dir, per_kind, seed = sys.argv[1:7]
    per_kind, seed = int(per_kind), int(seed)
    here = os.path.dirname(os.path.abspath(new_sel))
    src = json.load(gzip.open(os.path.join(here, "index", "source.json.gz")))
    tests = json.load(open(tests_json))["tests"]
    N = load(new_sel, "sel_new").Selector(tests)
    R = load(ref_sel, "sel_ref").Selector(tests)

    base_flags = {}
    for (f, cname), role in BASES.items():
        for c in classes(ast.parse(src[f])):
            if c.name == cname:
                for st in c.body:
                    nm = target_name(st)
                    if nm and isinstance(st.value, ast.Constant) and isinstance(st.value.value, bool):
                        base_flags.setdefault(role, {})[nm] = st.value.value

    cands = {"dictval": [], "delattr": [], "insattr": [], "docstr": []}
    for rel, text in sorted(src.items()):
        if not rel.startswith("sqlglot/") or not rel.endswith(".py"):
            continue
        lines = text.split("\n")
        tree = ast.parse(text)
        for d in [tree] + [x for x in ast.walk(tree) if isinstance(x, (ast.ClassDef, ast.FunctionDef))]:
            st = d.body[0] if d.body else None
            if (isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str)
                    and st.value.value.strip()):
                ln = lines[st.lineno - 1]
                q = '"""' if '"""' in ln else None
                if q and ln.strip() != q:
                    new = lines[:]
                    new[st.lineno - 1] = ln.replace(q, q + "Note: ", 1)
                    cands["docstr"].append((rel, "\n".join(new), f"{getattr(d, 'name', '<module>')}@{st.lineno}"))
        for c in classes(tree):
            names = {target_name(st) for st in c.body}
            for st in c.body:
                nm = target_name(st)
                if nm is None:
                    continue
                if isinstance(st.value, ast.Dict):
                    for v in st.value.values:
                        for k in ast.walk(v):
                            if isinstance(k, ast.Constant) and k.lineno == k.end_lineno:
                                ln = lines[k.lineno - 1]
                                nl = flip_const(k, ln)
                                if nl and nl != ln:
                                    new = lines[:]
                                    new[k.lineno - 1] = nl
                                    cands["dictval"].append((rel, "\n".join(new), f"{c.name}.{nm}@{k.lineno}"))
                if st.lineno == st.end_lineno and not any(isinstance(x, ast.Call) for x in ast.walk(st.value)):
                    new = lines[:st.lineno - 1] + lines[st.lineno:]
                    cands["delattr"].append((rel, "\n".join(new), f"{c.name}.{nm}@{st.lineno}"))
            role = None
            if rel.startswith("sqlglot/dialects/") and c.name == "Tokenizer":
                role = "tokenizer"
            elif rel.startswith("sqlglot/parsers/") or (rel.startswith("sqlglot/dialects/") and c.name == "Parser"):
                role = "parser"
            elif rel.startswith("sqlglot/generators/") or (rel.startswith("sqlglot/dialects/") and c.name == "Generator"):
                role = "generator"
            elif rel.startswith("sqlglot/dialects/") and rel != "sqlglot/dialects/dialect.py" and c.col_offset == 0:
                role = "dialect"
            if role and c.body:
                first = c.body[0]
                if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and len(c.body) > 1:
                    first = c.body[1]
                indent = " " * first.col_offset
                for nm, val in sorted(base_flags.get(role, {}).items()):
                    if nm in names:
                        continue
                    ins = f"{indent}{nm} = {not val}"
                    at = first.lineno - 1
                    if getattr(first, "decorator_list", None):
                        at = first.decorator_list[0].lineno - 1
                    new = lines[:at] + [ins] + lines[at:]
                    cands["insattr"].append((rel, "\n".join(new), f"{c.name}+{nm}"))

    rng = random.Random(seed)
    os.makedirs(os.path.join(out_dir, "commits"), exist_ok=True)
    meta = {}
    only = os.environ.get("TM_KINDS")
    for kind, lst in cands.items():
        if only and kind not in only.split(","):
            continue
        rng.shuffle(lst)
        kept = 0
        tried = 0
        for rel, new, what in lst:
            if kept >= per_kind:
                break
            tried += 1
            p = patch_text(rel, src[rel], new)
            a, b = N.for_patch(p), R.for_patch(p)
            if a == b:
                continue
            cid = f"t{seed}_{kind}_{kept:03d}"
            with open(os.path.join(out_dir, "commits", cid + ".patch"), "w") as fh:
                fh.write(p)
            meta[cid] = {"what": f"{rel}:{what}", "new": len(a), "ref": len(b)}
            kept += 1
        print(kind, "candidates", len(lst), "tried", tried, "kept", kept, file=sys.stderr)
    json.dump(meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
