"""Generate independent holdout patches from the pinned sqlglot source.

Mutations are drawn uniformly over source lines with a fixed seed; nothing is
derived from the sample patches or their answers.

  python tools/make_mutants.py SQLGLOT_ROOT OUT_DIR COUNT SEED
"""
from __future__ import annotations

import ast
import difflib
import os
import random
import re
import sys

CODE_OPS = [
    (r" == ", " != "), (r" != ", " == "), (r" < ", " <= "), (r" <= ", " < "),
    (r" > ", " >= "), (r" >= ", " > "), (r" and ", " or "), (r" or ", " and "),
    (r"\bnot ", ""), (r" is None", " is not None"), (r" is not None", " is None"),
    (r" in ", " not in "), (r"\bTrue\b", "False"), (r"\bFalse\b", "True"),
    (r" \+ 1\b", " - 1"), (r" - 1\b", " + 1"),
]


def _int_mut(line, rng):
    ms = list(re.finditer(r"(?<![\w.])(\d+)(?![\w.])", line))
    if not ms:
        return None
    m = rng.choice(ms)
    v = int(m.group(1))
    return line[: m.start()] + str(v + rng.choice([1, -1] if v > 0 else [1])) + line[m.end():]


def _str_mut(line, rng):
    ms = list(re.finditer(r'"([A-Za-z_ ]{3,})"', line))
    if not ms:
        return None
    m = rng.choice(ms)
    s = m.group(1)
    new = s[:-1] if rng.random() < 0.5 else s + "X"
    return line[: m.start()] + '"' + new + '"' + line[m.end():]


COMMENTS = ["# Cheap check first", "# Kept for backwards compatibility", "# TODO: revisit",
            "# Mirrors the reference implementation", "# Intentionally not cached",
            "# Keep in sync with the generator", "# Fast path"]


def py_files(root):
    out = []
    for dp, dn, fn in os.walk(os.path.join(root, "sqlglot")):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for f in fn:
            if f.endswith(".py") and f != "_version.py":
                out.append(os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/"))
    return sorted(out)


def fixture_files(root):
    out = []
    for dp, dn, fn in os.walk(os.path.join(root, "tests", "fixtures")):
        for f in fn:
            if f.endswith(".sql"):
                out.append(os.path.relpath(os.path.join(dp, f), root).replace(os.sep, "/"))
    return sorted(out)


def mutate_code(root, rel, rng, kind):
    src = open(os.path.join(root, rel), encoding="utf-8").read()
    if not src.endswith("\n"):
        return None
    lines = src.split("\n")
    base_dump = ast.dump(ast.parse(src))
    cand = [i for i, l in enumerate(lines) if l.strip() and not l.strip().startswith(("#", '"""', "'''", "import ", "from "))]
    rng.shuffle(cand)
    for i in cand[:200]:
        line = lines[i]
        if kind == "comment":
            indent = re.match(r"\s*", lines[i]).group(0)
            new_lines = lines[:i] + [indent + rng.choice(COMMENTS)] + lines[i:]
        elif kind == "delete":
            st = line.strip()
            if not re.match(r"^(self\.\w+\(|\w+\.append\(|\w+ = |return )", st) or st.endswith(("(", "[", "{", ",", "\\")):
                continue
            if lines[i - 1].rstrip().endswith((":",)) and (i + 1 >= len(lines) or len(re.match(r"\s*", lines[i + 1]).group(0)) < len(re.match(r"\s*", line).group(0))):
                continue
            new_lines = lines[:i] + lines[i + 1:]
        else:
            r = rng.random()
            new = None
            if r < 0.65:
                ops = [(a, b) for a, b in CODE_OPS if re.search(a, line)]
                if ops:
                    a, b = rng.choice(ops)
                    ms = list(re.finditer(a, line))
                    m = rng.choice(ms)
                    new = line[: m.start()] + b + line[m.end():]
            elif r < 0.85:
                new = _int_mut(line, rng)
            else:
                new = _str_mut(line, rng)
            if not new or new == line:
                continue
            new_lines = lines[:i] + [new] + lines[i + 1:]
        new_src = "\n".join(new_lines)
        try:
            d = ast.dump(ast.parse(new_src))
        except SyntaxError:
            continue
        if kind != "comment" and d == base_dump:
            continue
        return src, new_src
    return None


def mutate_fixture(root, rel, rng):
    src = open(os.path.join(root, rel), encoding="utf-8").read()
    if not src.endswith("\n"):
        return None
    lines = src.split("\n")
    cand = [i for i, l in enumerate(lines) if l.strip() and not l.startswith("--")]
    if not cand:
        return None
    i = rng.choice(cand)
    line = lines[i]
    words = [m.start() for m in re.finditer(r"\s", line)] or [len(line)]
    p = rng.choice(words)
    tok = rng.choice([" 42", " x", " 0", "1 ", " NULL", "a"])
    new = line[:p] + tok + line[p:]
    return src, "\n".join(lines[:i] + [new] + lines[i + 1:])


def to_patch(rel, a, b):
    al, bl = a.split("\n"), b.split("\n")
    # both end with "" after final newline: drop it for difflib
    diff = list(difflib.unified_diff(al[:-1], bl[:-1], f"a/{rel}", f"b/{rel}", lineterm="", n=3))
    if not diff:
        return ""
    return f"diff --git a/{rel} b/{rel}\nindex 1111111..2222222 100644\n" + "\n".join(diff) + "\n"


def main(argv):
    root, out_dir, count, seed = argv[0], argv[1], int(argv[2]), int(argv[3])
    rng = random.Random(seed)
    os.makedirs(out_dir, exist_ok=True)
    pys = py_files(root)
    weights = [sum(1 for l in open(os.path.join(root, f), encoding="utf-8") if l.strip()) for f in pys]
    fixtures = fixture_files(root)
    made = 0
    while made < count:
        r = rng.random()
        kinds = (["code"] if r < 0.5 else ["delete"] if r < 0.58 else ["comment"] if r < 0.68
                 else ["fixture"] if r < 0.85 else rng.sample(["code", "comment", "fixture", "code"], 2))
        parts, used = [], set()
        for k in kinds:
            for _ in range(20):
                if k == "fixture":
                    rel = rng.choice(fixtures)
                    res = mutate_fixture(root, rel, rng)
                else:
                    rel = rng.choices(pys, weights)[0]
                    res = mutate_code(root, rel, rng, k)
                if res and rel not in used:
                    used.add(rel)
                    parts.append(to_patch(rel, *res))
                    break
        if len(parts) != len(kinds) or not all(parts):
            continue
        made += 1
        name = f"h{seed}_{made:03d}_{'+'.join(kinds)}"
        with open(os.path.join(out_dir, name + ".patch"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("".join(parts))
    print(made, "mutants", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
